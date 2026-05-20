#!/usr/bin/env python3
"""Truth negotiator (deploy_111-C).

Verifies a claim against the corpus before Leo outputs it. Four-direction probe
+ adversarial challenger pass + execution-status aware citation rules.

Inputs:
  --claim "T-52540 was cancelled in 2021"
  --case  MWK-001       (optional scope)
  --user  jonathan      (asked_by, for audit)

Output:
  JSON with verdict ∈ {verified, uncertain, refuted, unsourced, uncitable_draft}
  plus citation_tag, evidence_doc_ids, evidence_quotes, challenger_disagrees.

Citation rules (execution_status):
  executed_notarized / executed_filed / government_issued → CITABLE
  executed_signed_only                                    → CITABLE (caveat)
  email_sent / email_received                             → CITABLE for fact-of-communication, NOT content
  draft_unsigned                                          → NEVER citable as fact (verdict: uncitable_draft)
  template / unknown                                      → not citable

Returns audit row id in `truth_negotiations` so callers can reference it.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
import psycopg2
import psycopg2.extras
from bilingual_search import expand, expand_high_precision, search_concepts_in_text, PAIRS

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

CITATION_TIER = {
    "executed_notarized":   ("V·N", "verified — notarized instrument"),
    "executed_filed":       ("V·F", "verified — filed pleading/order"),
    "government_issued":    ("V·G", "verified — government-issued"),
    "executed_signed_only": ("V·S", "verified — signed only (no notarization)"),
    "email_sent":           ("V·E", "verified — outbound email (communication fact)"),
    "email_received":       ("V·R", "verified — inbound email (communication fact)"),
    "draft_unsigned":       ("D",   "DRAFT — not legally executed"),
    "template":             ("?",   "template — no factual weight"),
    "unknown":              ("?",   "execution status unknown"),
}

# Minimum execution-statuses required for a claim to count as VERIFIED
CITABLE_AS_FACT = {"executed_notarized", "executed_filed", "government_issued", "executed_signed_only"}
CITABLE_FOR_COMMUNICATION = {"email_sent", "email_received"}


def claim_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def extract_atoms(claim):
    """Decompose into atomic factual sub-claims.

    Pragmatic heuristic: split on conjunctions/punctuation, then drop atoms that
    are pure qualifiers. For each atom, identify likely 'key terms' that anchor
    the lookup (TCT numbers, dates, named entities, dockets).
    """
    parts = re.split(r"\s*(?:;|\.\s|,\s+(?:and|but|while|whereas)\s+|\s+and\s+(?=(?:[A-Z]|TCT|the|on|at)))", claim)
    atoms = []
    for p in parts:
        p = p.strip().rstrip(".,;")
        if not p or len(p) < 5:
            continue
        anchors = []
        # TCT/OCT codes
        for m in re.finditer(r"\b(T(?:CT)?[\-\s]?\d{3,6}(?:[\-\s]\d{4,7})?|OCT[\-\s]?\d+)\b", p, re.IGNORECASE):
            anchors.append(("title", m.group(1).upper().replace(" ", "-")))
        # Docket (require "Civil Case" or "CV" prefix; with or without "No.")
        for m in re.finditer(r"(?:civil\s+case\s+(?:no\.?\s*)?|CV[\-\s]?)(\d{1,4}[\-\s]\d{3,5}(?:[\-\s]\d+)?)\b", p, re.IGNORECASE):
            anchors.append(("docket", m.group(1)))
        # CTN SL-NNNN-NNNN-NNNN (ARTA cases)
        for m in re.finditer(r"\bCTN\s+SL-\d{4}-\d{4}-\d{4}\b", p, re.IGNORECASE):
            anchors.append(("docket", m.group(0)))
        # Years
        for m in re.finditer(r"\b(19|20)\d{2}\b", p):
            anchors.append(("year", m.group(0)))
        # Capitalized multi-word names (rough)
        for m in re.finditer(r"\b([A-Z][a-zA-Z'\-]{2,}(?:\s+[A-Z][a-zA-Z'\-]{2,}){0,3})\b", p):
            name = m.group(1)
            if name not in ("The", "This", "That", "Civil", "Case"):
                anchors.append(("entity", name))
        atoms.append({"text": p, "anchors": anchors})
    return atoms or [{"text": claim, "anchors": []}]


def _expand_entity_anchors(cur, anchors):
    """Expand entity anchors through the entities table to catch name variants.

    Addresses fragmentation like 'Cesar M. de la Fuente' / 'Cesar N. dela Fuente' /
    'Cesar Dela Fuente' — same person, different recorded forms across docs.
    Pulls canonical_name + aliases of verified entity records that match the anchor.
    Bounded: top 3 verified entities per anchor (by mentions_count).

    Failure-safe: if entities table query errors, falls back to base anchors.
    """
    expanded = []
    seen = set()

    def _push(kind, v):
        if not v or len(v) < 3:
            return
        key = v.lower().strip()
        if key in seen:
            return
        seen.add(key)
        expanded.append((kind, v))

    for kind, val in anchors:
        _push(kind, val)
        if kind != "entity" or not val or len(val) < 3:
            continue
        try:
            cur.execute("""
                SELECT canonical_name, aliases
                  FROM entities
                 WHERE provenance_level = 'verified'
                   AND (canonical_name ILIKE %s OR %s = ANY(aliases))
                 ORDER BY mentions_count DESC NULLS LAST
                 LIMIT 3
            """, (f"%{val}%", val))
            for row in cur.fetchall():
                _push("entity", row["canonical_name"])
                for alias in (row.get("aliases") or []):
                    _push("entity", alias)
        except Exception:
            # Entities lookup failure must not block the probe.
            continue
    return expanded


def probe_evidence(cur, claim_text, anchors, case_file=None):
    """4-direction probe. Returns list of evidence dicts."""
    anchors = _expand_entity_anchors(cur, anchors)
    evidence = []
    seen_doc_ids = set()

    def _add(d, direction, quote=None):
        if d["id"] in seen_doc_ids: return
        seen_doc_ids.add(d["id"])
        evidence.append({
            "doc_id": d["id"],
            "smart_filename": d.get("smart_filename"),
            "classification": d.get("classification"),
            "execution_status": d.get("execution_status"),
            "direction": direction,
            "quote": quote,
        })

    # Direction A: entity-anchor grep
    for kind, val in anchors:
        if kind in ("title", "docket", "entity") and val and len(val) >= 3:
            cur.execute("""
                SELECT id, smart_filename, classification, execution_status,
                       LEFT(extracted_text, 25000) AS extracted_text
                  FROM documents
                 WHERE extracted_text ILIKE %s
                   AND (%s::text IS NULL OR case_file = %s)
                 ORDER BY id
                 LIMIT 25
            """, (f"%{val}%", case_file, case_file))
            for d in cur.fetchall():
                # extract a 250-char context window around first match
                txt = d["extracted_text"] or ""
                idx = txt.lower().find(val.lower())
                quote = txt[max(0, idx-120):idx+len(val)+150].strip() if idx >= 0 else None
                _add(d, f"anchor:{kind}={val}", quote)

    # Direction B: quoted-phrase grep — try a few key fragments of the claim
    fragments = []
    # Try the most specific 4-6 word window from the claim
    words = re.findall(r"[A-Za-z0-9\-\.]+", claim_text)
    if len(words) >= 4:
        for n in (6, 5, 4):
            for i in range(0, len(words)-n+1, 2):
                frag = " ".join(words[i:i+n])
                if len(frag) >= 15 and not all(w.lower() in {"the","a","an","of","and","is","was","to","in","on","by","for","with"} for w in words[i:i+n]):
                    fragments.append(frag)
                    if len(fragments) >= 4: break
            if fragments: break

    for frag in fragments[:4]:
        cur.execute("""
            SELECT id, smart_filename, classification, execution_status,
                   LEFT(extracted_text, 25000) AS extracted_text
              FROM documents
             WHERE extracted_text ILIKE %s
               AND (%s::text IS NULL OR case_file = %s)
             ORDER BY id LIMIT 5
        """, (f"%{frag}%", case_file, case_file))
        for d in cur.fetchall():
            txt = d["extracted_text"] or ""
            idx = txt.lower().find(frag.lower())
            quote = txt[max(0,idx-100):idx+len(frag)+150].strip() if idx >= 0 else None
            _add(d, f"phrase:{frag[:30]}", quote)

    # Direction E (NEW): bilingual concept probe — for any concept found in the claim,
    # search Filipino+English keywords together. Catches facts buried in Tagalog testimony.
    # Rank by COMBINED-HIT score: documents containing MORE concept synonyms get prioritized.
    concepts_in_claim = search_concepts_in_text(claim_text)
    # Also include direct keyword anchors so claims like "...is dead" expand correctly even if
    # search_concepts_in_text missed the bare word
    if not concepts_in_claim:
        # try splitting claim and expanding each meaningful token
        for tok in re.findall(r"\b[a-zA-Z]{4,}\b", claim_text)[:10]:
            from bilingual_search import concept_of
            c = concept_of(tok)
            if c in PAIRS:
                concepts_in_claim[c] = [tok]
    for concept, _ in list(concepts_in_claim.items())[:4]:
        broad = expand(concept)
        precise = expand_high_precision(concept)
        # Score docs by how many concept-related anchors AND claim entities they contain
        anchor_strings = [v for _, v in anchors if v]
        # Build patterns with precise terms first (so they get checked AND weighted higher)
        kw_patterns_precise = [f"%{k}%" for k in precise if len(k) >= 4]
        kw_patterns_broad = [f"%{k}%" for k in broad if len(k) >= 4 and f"%{k}%" not in kw_patterns_precise][:8]
        kw_patterns = kw_patterns_precise + kw_patterns_broad
        if not kw_patterns: continue
        # Score: precise hits worth 5×, broad hits worth 1× + affidavit-class bonus
        precise_score_clauses = " + ".join([f"((extracted_text ILIKE %s)::int * 5)" for _ in kw_patterns_precise]) or "0"
        broad_score_clauses = " + ".join([f"((extracted_text ILIKE %s)::int * 1)" for _ in kw_patterns_broad]) or "0"
        classification_boost = (
            " + (CASE classification "
            "  WHEN 'Affidavit' THEN 10 "
            "  WHEN 'Judicial Affidavit' THEN 12 "
            "  WHEN 'Complaint' THEN 8 "
            "  WHEN 'Reply' THEN 7 "
            "  WHEN 'Answer' THEN 7 "
            "  WHEN 'Order' THEN 9 "
            "  WHEN 'Motion' THEN 6 "
            "  WHEN 'Court Filing' THEN 6 "
            "  WHEN 'Demand Letter' THEN 4 "
            "  ELSE 0 END)"
        )
        score_clauses = f"({precise_score_clauses}) + ({broad_score_clauses}) {classification_boost}"
        # Each ILIKE placeholder needs one param; we have score_clauses + WHERE clause
        # both using the SAME patterns, so we provide kw_patterns twice (once per use).
        ent_params = []
        if anchor_strings:
            ent_check = " AND (" + " OR ".join(["extracted_text ILIKE %s" for _ in anchor_strings[:3]]) + ")"
            ent_params = [f"%{a}%" for a in anchor_strings[:3]]
        else:
            ent_check = ""
        sql = f"""
            SELECT id, smart_filename, classification, execution_status,
                   LEFT(extracted_text, 25000) AS extracted_text,
                   ({score_clauses}) AS hit_score
              FROM documents
             WHERE ({' OR '.join(['extracted_text ILIKE %s' for _ in kw_patterns])})
               {ent_check}
               AND (%s::text IS NULL OR case_file = %s)
             ORDER BY hit_score DESC, id LIMIT 15
        """
        # Params order: precise patterns × 5, broad patterns × 1, WHERE patterns, entity, case_file × 2
        score_params = list(kw_patterns_precise) + list(kw_patterns_broad)
        try:
            cur.execute(sql, score_params + list(kw_patterns) + ent_params + [case_file, case_file])
        except Exception as e:
            print(f"  ⚠ Direction E SQL error: {e}", file=sys.stderr)
            continue
        for d in cur.fetchall():
            txt = d["extracted_text"] or ""
            # find best matching keyword for the quote
            best_kw = None
            best_idx = -1
            for kw in (precise + broad)[:12]:
                if len(kw) < 4: continue
                idx = txt.lower().find(kw.lower())
                if idx >= 0:
                    best_kw = kw; best_idx = idx
                    break
            quote = txt[max(0, best_idx-100):best_idx+len(best_kw or "")+150].strip() if best_idx >= 0 else None
            _add(d, f"concept:{concept}={best_kw} (score={d.get('hit_score', 0)})", quote)

    # Direction C: title-graph cross-reference (only if any title anchor present)
    titles = [v for k, v in anchors if k == "title"]
    if titles:
        for t in titles:
            cur.execute("""
                SELECT 'title_chain' AS kind, tc.parent_title, tc.child_title,
                       tc.provenance_level, tc.source_doc_id
                  FROM title_chain tc
                 WHERE tc.parent_title ILIKE %s OR tc.child_title ILIKE %s
                 LIMIT 10
            """, (f"%{t}%", f"%{t}%"))
            for r in cur.fetchall():
                if r["source_doc_id"]:
                    cur.execute("""
                        SELECT id, smart_filename, classification, execution_status FROM documents WHERE id=%s
                    """, (r["source_doc_id"],))
                    d = cur.fetchone()
                    if d:
                        _add(d, f"graph:title_chain {r['parent_title']}→{r['child_title']} (prov={r['provenance_level']})", None)

    # Direction D: provenance check is implicit — we attach the doc's execution_status to each evidence
    return evidence


def call_challenger(claim_text, evidence_summaries):
    """Adversarial pass — try to DISPROVE the claim from the same evidence.

    Returns (disagrees: bool, reason: str). Uses Anthropic if ANTHROPIC_API_KEY set,
    otherwise returns a stub agreement.
    """
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return (False, "challenger_disabled (no ANTHROPIC_API_KEY)")
    try:
        import anthropic
        from llm_billing import anthropic_call
        client = anthropic.Anthropic(api_key=key)
        # Sonnet for verdict-gate work per cost-discipline rule #2 (Haiku reserved
        # for extraction/classification/routing; Sonnet for synthesis & verdicts).
        msg = anthropic_call(
            client,
            called_from="truth_negotiator",
            purpose="challenger",
            case_file="MWK-001",
            model="claude-sonnet-4-6",
            max_tokens=400,
            # deploy_217: temperature=0 for back-test stability + per-transferee
            # number reproducibility. Greedy decoding → identical input → identical
            # output. Yesterday-vs-today verdict drift on t4497-registered claim
            # traced to default temperature > 0 sampling.
            temperature=0,
            # Prompt caching: the system prompt is ~2K tokens of static instructions.
            # Use EXTENDED 1h TTL (was 5-min ephemeral). Truth-negotiator runs in
            # bursts throughout the day; 1h cache amortizes the write cost across
            # ~130 calls/day with ~1 write/h instead of 12+ writes/h. Net: ~30%
            # additional savings on top of the ~42% already realized at 5-min TTL.
            system=[{
                "type": "text",
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
                "text": (
                "You are a fact-checker for a Philippine property-law firm's RAG.\n"
                "You receive a CLAIM and EVIDENCE EXCERPTS that already passed retrieval.\n"
                "Your task: decide whether the EVIDENCE SUPPORTS the claim.\n\n"
                "═══════ PRIME DIRECTIVE ═══════\n"
                "Refute ONLY when evidence ACTIVELY CONTRADICTS the claim. Missing detail ≠ contradiction.\n"
                "Retrieval already vetted relevance — your job is to find genuine contradictions, not to demand exhaustive citations.\n\n"
                "═══════ WORKED EXAMPLES — match this reasoning ═══════\n\n"
                "EXAMPLE A — Stage claim (verified):\n"
                "  CLAIM: 'Civil Case 26-360 is at the pretrial pending stage'\n"
                "  EVIDENCE: doc#392 = Notice of Pre-trial Conference (executed_filed) for Civil Case 26-360.\n"
                "             Also docs#393–395 = filed motions/affidavits on the same case.\n"
                "  CORRECT: disagrees=FALSE. A filed Notice of Pre-trial Conference IS direct evidence the case is at pretrial.\n"
                "  Filed motions DURING pretrial do NOT move the case off pretrial — motions are normal at this stage.\n"
                "  WRONG REASONING (do not do this): 'pretrial supported but pending motions show case may have moved on'.\n\n"
                "EXAMPLE B — Date contradiction (refuted):\n"
                "  CLAIM: 'Cesar de la Fuente died before September 2019'\n"
                "  EVIDENCE: Affidavit says Cesar is dead. Deed of Sale dated September 2019 bears Cesar's signature.\n"
                "  CORRECT: disagrees=TRUE. The death is supported, but Cesar signing in Sept 2019 directly contradicts 'before Sept 2019'.\n"
                "  Scan ALL evidence for actions by the subject AT OR AFTER the threshold date — this is mandatory.\n\n"
                "EXAMPLE C — Compound claim with partial evidence (verified):\n"
                "  CLAIM: 'T-52540 was cancelled in 2021 via a Deed of Sale executed by Cesar in September 2019'\n"
                "  EVIDENCE: doc#409 = Deed of Sale signed by Cesar (mechanism + executor confirmed).\n"
                "             doc#408 = title history showing T-52540 cancellation.\n"
                "             Date 2021 and date Sept 2019 not directly quoted but consistent with chain.\n"
                "  CORRECT: disagrees=FALSE. No atom is contradicted. Some atoms supported, others neutral → SUPPORTED.\n"
                "  WRONG REASONING (do not do this): 'I cannot find a direct quote for each of the 5 atoms, so refuted'.\n\n"
                "═══════ DECISION ALGORITHM ═══════\n\n"
                "STEP 1 — Decompose claim into atoms (principal fact + qualifiers).\n\n"
                "STEP 2 — For each atom, classify:\n"
                "  • SUPPORTED — at least one quote affirms it.\n"
                "  • CONTRADICTED — at least one quote ACTIVELY conflicts with it (different date, different actor, denial).\n"
                "  • NEUTRAL — evidence doesn't address it directly.\n\n"
                "STEP 3 — MANDATORY DATE-CONTRADICTION CHECK:\n"
                "  For any claim with 'before/after/by/in [date]', actively scan ALL evidence for actions by the subject\n"
                "  inconsistent with that bound. A signed deed dated D refutes 'died before D'.\n\n"
                "STEP 4 — Aggregate:\n"
                "  • ANY atom CONTRADICTED → disagrees=TRUE.\n"
                "  • All atoms SUPPORTED or NEUTRAL (none contradicted) → disagrees=FALSE.\n"
                "  • No atoms addressed at all → disagrees=FALSE, note 'evidence neither confirms nor contradicts'.\n\n"
                "═══════ ANTI-PATTERNS — DO NOT DO ═══════\n"
                "  ✗ Refute because evidence is incomplete (missing dates, missing parties). Missing ≠ contradicted.\n"
                "  ✗ Refute a stage claim because other filings exist at that stage.\n"
                "  ✗ Refute a compound claim because you cannot find a quote for every atom.\n"
                "  ✗ Refute when your own reasoning says 'doc#X SUPPORTS the claim, BUT...'. If a doc supports it, that's a SUPPORT signal.\n\n"
                "═══════ EVIDENCE TYPE WEIGHTS ═══════\n"
                "  • Sworn affidavits (Judicial Affidavits) → strongest; treat as fact.\n"
                "  • Filed pleadings, Notices, Orders (executed_filed, government_issued) → strong; header/title carries weight.\n"
                "  • Drafts (draft_unsigned) → cannot support; absence still ≠ contradiction.\n"
                "  • Emails → prove communication occurred, not content truth.\n\n"
                "═══════ FILIPINO EVIDENCE IS VALID ═══════\n"
                "  • 'Patay na po' / 'namatay' / 'yumao' = died/dead — SUPPORTS death claim.\n"
                "  • 'Nilagdaan niya' / 'lumagda' = signed — SUPPORTS signature claim.\n"
                "  • 'Binawi' / 'pinawalang-bisa' = revoked/voided — SUPPORTS revocation claim.\n\n"
                "═══════ POSTHUMOUS LANGUAGE — CRITICAL ═══════\n"
                "Phrases like 'the late X', 'the deceased X', 'the decedent', 'X (now deceased)' SUPPORT death claims.\n"
                "When a document says 'Sometime on [date], the late X did [action]', the speaker is describing\n"
                "  what X (currently dead) did at that past date. The date is when X acted, NOT when X died.\n"
                "  This phrasing SUPPORTS 'X is dead' — never use it to refute a death claim.\n\n"
                "Output ONLY the JSON object. Do not wrap in markdown code fences. Do not add prose before or after.\n"
                "Respond with JSON: {\"disagrees\": bool, \"reason\": str (<=350 chars naming the supporting or refuting evidence by doc#)}"
            )
            }],
            messages=[{
                "role": "user",
                "content": f"CLAIM: {claim_text}\n\nEVIDENCE:\n" + "\n".join(
                    f"- doc#{e['doc_id']} [{e['execution_status'] or 'unknown'}] "
                    f"({e['classification']}) {e['smart_filename']}\n  quote: {e.get('quote') or '(no quote)'}"
                    for e in evidence_summaries[:15]
                ),
            }],
        )
        out = msg.content[0].text.strip()
        # Strip markdown code fences if the model wrapped output despite instructions.
        if out.startswith("```"):
            out = re.sub(r"^```(?:json)?\s*", "", out)
            out = re.sub(r"\s*```\s*$", "", out)
        # Use raw_decode to parse the first JSON object only, ignoring trailing prose.
        start = out.find("{")
        if start < 0:
            return (False, "challenger_no_json")
        try:
            j, _ = json.JSONDecoder().raw_decode(out[start:])
        except json.JSONDecodeError:
            # Fall back to greedy regex match in case of embedded text
            m = re.search(r"\{.*?\}", out[start:], re.DOTALL)
            if not m:
                return (False, "challenger_no_json")
            j = json.loads(m.group(0))
        return (bool(j.get("disagrees", False)), str(j.get("reason", ""))[:350])
    except Exception as e:
        return (False, f"challenger_error: {str(e)[:120]}")


def negotiate(claim_text, case_file=None, asked_by="cli", skip_challenger=False):
    t0 = time.time()
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    atoms = extract_atoms(claim_text)
    all_evidence = []
    for atom in atoms:
        ev = probe_evidence(cur, atom["text"], atom["anchors"], case_file=case_file)
        all_evidence.extend(ev)

    # Dedup by doc_id
    seen = set(); deduped = []
    for e in all_evidence:
        if e["doc_id"] in seen: continue
        seen.add(e["doc_id"]); deduped.append(e)

    # Final ranking — surface high-evidentiary-value docs (affidavits, pleadings, orders)
    # AND high-precision-quote hits to the top, so the challenger sees them
    CLASS_RANK = {
        "Judicial Affidavit": 12, "Court Filing": 11, "Affidavit": 11, "Complaint": 10,
        "Reply": 8, "Motion": 8, "Answer": 8, "Order": 9, "Resolution": 7,
        "Notice": 6, "Memorandum": 6, "Demand Letter": 5, "Deed": 4,
        "Special Power of Attorney": 4, "Power of Attorney": 4, "Letter": 3,
        "Correspondence": 3, "Title (TCT/OCT)": 2, "Tax Document": 1, "Email": 2,
    }
    # If claim mentions case-stage, boost Notice + Order classifications
    claim_lower = claim_text.lower()
    STAGE_BOOST = 0
    if any(kw in claim_lower for kw in ("stage", "pretrial", "pre-trial", "pre_trial", "complaint filed",
                                        "answer filed", "summons", "decision", "memoranda", "appeal")):
        STAGE_BOOST = 10  # heavy boost for Notice/Order
    DEED_BOOST = 5 if any(kw in claim_lower for kw in ("deed", "cancelled", "void", "executed by", "sale")) else 0
    EXEC_RANK = {
        "executed_filed": 6, "executed_notarized": 6, "government_issued": 4,
        "executed_signed_only": 3, "email_sent": 2, "email_received": 2,
        "draft_unsigned": 0, "template": 0, "unknown": 1, None: 1,
    }
    def _rank(e):
        cls_name = e.get("classification") or ""
        cls = CLASS_RANK.get(cls_name, 0)
        ex = EXEC_RANK.get(e.get("execution_status"), 1)
        precision = 5 if e.get("direction", "").startswith(("concept:", "anchor:", "phrase:")) and e.get("quote") else 0
        # Stage-boost: notice/order docs get extra ranking for stage claims
        sb = STAGE_BOOST if cls_name in ("Notice", "Order", "Resolution") else 0
        # Deed-boost: deed docs get extra ranking for cancellation/sale claims
        db = DEED_BOOST if cls_name in ("Deed", "Special Power of Attorney") else 0
        return -(cls + ex + precision + sb + db)
    deduped.sort(key=_rank)

    # Verdict logic
    if not deduped:
        verdict = "unsourced"
        citation_tag = None
        challenger_disagrees, challenger_reason = (False, "no evidence to challenge")
    else:
        fact_backers = [e for e in deduped if e["execution_status"] in CITABLE_AS_FACT]
        comm_backers = [e for e in deduped if e["execution_status"] in CITABLE_FOR_COMMUNICATION]
        drafts       = [e for e in deduped if e["execution_status"] == "draft_unsigned"]

        # Run challenger
        if skip_challenger:
            challenger_disagrees, challenger_reason = (False, "skipped")
        else:
            challenger_disagrees, challenger_reason = call_challenger(claim_text, deduped[:10])

        if drafts and not fact_backers and not comm_backers:
            verdict = "uncitable_draft"
            citation_tag = f"[D {drafts[0]['doc_id']}]"
        elif challenger_disagrees:
            verdict = "refuted"
            citation_tag = None
        elif len(fact_backers) >= 2:
            verdict = "verified"
            tier, _ = CITATION_TIER[fact_backers[0]["execution_status"]]
            citation_tag = f"[V·{tier.split('·')[1]} " + ",".join(str(e["doc_id"]) for e in fact_backers[:3]) + "]"
        elif len(fact_backers) == 1:
            verdict = "verified"
            e = fact_backers[0]
            tier, _ = CITATION_TIER[e["execution_status"]]
            citation_tag = f"[V·{tier.split('·')[1]} {e['doc_id']}]"
        elif comm_backers:
            verdict = "uncertain"
            citation_tag = f"[V·E {comm_backers[0]['doc_id']} — communication only]"
        else:
            verdict = "uncertain"
            citation_tag = f"[? {deduped[0]['doc_id']}]"

    duration_ms = int((time.time() - t0) * 1000)

    # Persist
    cur.execute("""
        INSERT INTO truth_negotiations
          (claim_text, claim_hash, atom_text, case_file, asked_by, verdict,
           evidence_doc_ids, evidence_quotes, challenger_disagrees, challenger_reason,
           citation_tag, execution_statuses, duration_ms)
        VALUES (%s,%s,%s,%s,%s,%s, %s,%s::jsonb,%s,%s, %s,%s::jsonb, %s)
        RETURNING id
    """, (
        claim_text, claim_hash(claim_text),
        " | ".join(a["text"] for a in atoms),
        case_file, asked_by, verdict,
        [e["doc_id"] for e in deduped[:30]],
        json.dumps([{"doc_id": e["doc_id"], "quote": e.get("quote")} for e in deduped[:10] if e.get("quote")]),
        challenger_disagrees, challenger_reason,
        citation_tag,
        json.dumps({str(e["doc_id"]): e.get("execution_status") for e in deduped[:30]}),
        duration_ms,
    ))
    neg_id = cur.fetchone()["id"]
    cur.close(); conn.close()

    return {
        "id": neg_id,
        "verdict": verdict,
        "citation_tag": citation_tag,
        "evidence_count": len(deduped),
        "fact_backers": [e["doc_id"] for e in deduped if e["execution_status"] in CITABLE_AS_FACT],
        "comm_backers": [e["doc_id"] for e in deduped if e["execution_status"] in CITABLE_FOR_COMMUNICATION],
        "drafts": [e["doc_id"] for e in deduped if e["execution_status"] == "draft_unsigned"],
        "challenger_disagrees": challenger_disagrees,
        "challenger_reason": challenger_reason,
        "atoms": [a["text"] for a in atoms],
        "duration_ms": duration_ms,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claim", required=True)
    ap.add_argument("--case", default=None)
    ap.add_argument("--user", default="cli")
    ap.add_argument("--skip-challenger", action="store_true")
    args = ap.parse_args()
    r = negotiate(args.claim, case_file=args.case, asked_by=args.user, skip_challenger=args.skip_challenger)
    print(json.dumps(r, indent=2, default=str))


if __name__ == "__main__":
    main()
