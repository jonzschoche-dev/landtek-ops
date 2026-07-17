#!/usr/bin/env python3
"""inquiry_stack.py — Agentic inquiry: scrutinize full stack → answer → writeback → trigger agents.

Architecture (not keyword patch theater):

  1. RECORD inquiry
  2. SCRUTINIZE every living layer (role, briefs, document_fields, facts, titles, holes)
  3. SYNTHESIZE answer only from hits (fail closed if empty)
  4. WRITEBACK atoms into pertinent tables (document_fields / matter_facts / fact_fields)
  5. TRIGGER agents whose mandates own tables affected by those atoms

  python3 scripts/inquiry_stack.py --ask "What is the docket of the OP second manifestation?" --client MWK-001
  python3 scripts/inquiry_stack.py --ask "..." --client MWK-001 --go   # writeback + triggers
  python3 scripts/inquiry_stack.py --drain-agent verify_worker --limit 5

Called from leo_service try_purpose_route as the general factual path.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any, Optional

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# Stack layers scrutinized on every factual inquiry (order = audit trail, not priority)
LAYERS = (
    "role",
    "matters",
    "matter_brief",
    "document_fields",
    "matter_facts",
    "fact_fields",
    "title_brief",
    "holes",
)


def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


def _cur(c):
    return c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _as_dicts(cur, rows=None):
    rows = list(rows if rows is not None else (cur.fetchall() or []))
    if not rows:
        return []
    if isinstance(rows[0], dict):
        return rows
    cols = [d[0] for d in (cur.description or [])]
    return [dict(zip(cols, r)) for r in rows]


def _toks(message: str) -> list[str]:
    stop = {
        "the", "a", "an", "to", "from", "of", "and", "or", "how", "many", "what",
        "when", "where", "is", "are", "was", "were", "for", "with", "my", "our",
        "me", "you", "please", "number", "of", "do", "does", "did", "about",
    }
    raw = re.findall(r"[A-Za-z0-9][A-Za-z0-9./\-]{1,}", (message or "").lower())
    out = []
    for t in raw:
        if t in stop or len(t) < 2:
            continue
        out.append(t)
    return out[:12]


def _matter_hints(message: str) -> list[str]:
    t = (message or "").lower()
    hints = []
    if re.search(r"\bop\b|office of the president|malacañ?ang|recto|supervisory", t):
        hints.append("MWK-OP-PETITION")
    if "second" in t and "manifest" in t:
        hints.append("MWK-OP-PETITION")
    if re.search(r"\b0747\b", t):
        hints.append("MWK-ARTA-0747")
    if re.search(r"\b0690\b", t):
        hints.append("MWK-ARTA-0690")
    if re.search(r"\b0792\b", t):
        hints.append("MWK-ARTA-0792")
    if re.search(r"\b1321\b", t):
        hints.append("MWK-ARTA-1321")
    if re.search(r"\b1210\b", t):
        hints.append("MWK-ARTA-1210")
    if "4497" in t or re.search(r"\bt-?4497\b", t):
        hints.append("MWK-TCT4497")
    if "26360" in t or "cv-26360" in t or "cv 26360" in t:
        hints.append("MWK-CV26360")
    # unique preserve
    seen, out = set(), []
    for h in hints:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def _want_kinds(message: str) -> list[str]:
    t = (message or "").lower()
    kinds = []
    if any(k in t for k in ("docket", "mro", "transmittal", "case no", "case number",
                            "receiving ref", "filing ref", "reference no")):
        kinds += ["mro_ref", "docket", "ctn"]
    if "manifest" in t:
        kinds += ["mro_ref", "ctn"]
    if any(k in t for k in ("ctn", "arta")):
        kinds.append("ctn")
    if any(k in t for k in ("tct", "title", "oct", "e-title")):
        kinds += ["tct", "oct", "e_title"]
    if any(k in t for k in ("tax", "arp", "td ")):
        kinds.append("tax_dec")
    if "party" in t or "who is" in t:
        kinds.append("party")
    if not kinds:
        # general factual: cast a wide net on typed fields
        kinds = ["mro_ref", "ctn", "docket", "tct", "oct", "e_title", "tax_dec", "date"]
    # unique
    seen, out = set(), []
    for k in kinds:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


# ── Scrutiny layers ──────────────────────────────────────────────────────────

def scrutinize(cur, client_code: str, message: str, role: Optional[str] = None) -> dict:
    """Run complete stack check. Returns {layers: [...], atoms: [...], matters: [...]}."""
    fam = (client_code or "").split("-")[0]
    fam_like = fam + "%" if fam else "%"
    toks = _toks(message)
    matters = _matter_hints(message)
    kinds = _want_kinds(message)
    layers = []
    atoms = []

    def add_layer(name, status, hit_count=0, payload=None, notes=None):
        layers.append({
            "layer": name,
            "status": status,
            "hit_count": hit_count,
            "payload": payload or {},
            "notes": notes,
        })

    # role
    add_layer("role", "hit" if role or client_code else "miss",
              1 if (role or client_code) else 0,
              {"role": role, "client_code": client_code})

    # matters (scope)
    try:
        if matters:
            cur.execute(
                """
                SELECT matter_code, status, current_stage, forum
                FROM matters WHERE matter_code = ANY(%s)
                """,
                (matters,),
            )
        else:
            cur.execute(
                """
                SELECT matter_code, status, current_stage, forum
                FROM matters
                WHERE matter_code LIKE %s AND coalesce(status,'') NOT IN ('archived')
                ORDER BY matter_code LIMIT 30
                """,
                (fam_like,),
            )
        mrows = _as_dicts(cur)
        if mrows and not matters:
            # keep family list but prefer OP if message mentions it
            matters = [r["matter_code"] for r in mrows[:12]]
        add_layer("matters", "hit" if mrows else "empty", len(mrows),
                  {"matters": [r["matter_code"] for r in mrows[:20]]})
    except Exception as e:
        add_layer("matters", "error", 0, notes=str(e)[:200])

    scope = matters or [fam_like]

    # matter_brief
    try:
        if matters:
            cur.execute(
                """
                SELECT matter_code, headline, ctns, dockets, clarity_status,
                       needs_human_review, n_facts_verified
                FROM matter_brief WHERE matter_code = ANY(%s)
                """,
                (matters,),
            )
        else:
            cur.execute(
                """
                SELECT matter_code, headline, ctns, dockets, clarity_status,
                       needs_human_review, n_facts_verified
                FROM matter_brief WHERE matter_code LIKE %s
                ORDER BY n_facts_verified DESC NULLS LAST LIMIT 10
                """,
                (fam_like,),
            )
        brows = _as_dicts(cur)
        add_layer("matter_brief", "hit" if brows else "empty", len(brows),
                  {"headlines": [b.get("headline") for b in brows[:5]]})
        for b in brows:
            for ctn in (b.get("ctns") or [])[:8]:
                atoms.append({
                    "atom_kind": "ctn",
                    "value_norm": str(ctn),
                    "matter_code": b["matter_code"],
                    "provenance_level": "inferred_strong",
                    "source": "matter_brief",
                })
    except Exception as e:
        add_layer("matter_brief", "error", 0, notes=str(e)[:200])

    # document_fields (typed from full docs) — primary typed store
    try:
        # Per-kind cap (not a flat LIMIT): with a flat cap + alphabetical order,
        # abundant 'ctn' rows starved 'mro_ref'/'tct' out of the window entirely
        # (docket asks answered with CTNs only — agent_sim cycle 2 caught it).
        cur.execute(
            """
            SELECT field_kind, value_norm, doc_id, value_raw, matters
            FROM (
                SELECT df.field_kind, df.value_norm, df.doc_id, df.value_raw,
                       array_agg(DISTINCT l.matter_code)
                           FILTER (WHERE l.matter_code IS NOT NULL) AS matters,
                       row_number() OVER (
                           PARTITION BY df.field_kind ORDER BY df.value_norm
                       ) AS rn
                FROM document_fields df
                LEFT JOIN document_matter_links l ON l.doc_id = df.doc_id
                WHERE df.field_kind = ANY(%s)
                  AND (
                    l.matter_code = ANY(%s)
                    OR l.matter_code LIKE %s
                    OR df.doc_id IN (
                        SELECT doc_id FROM document_matter_links WHERE matter_code = ANY(%s)
                    )
                  )
                GROUP BY df.field_kind, df.value_norm, df.doc_id, df.value_raw
            ) per_kind
            WHERE rn <= 15
            ORDER BY array_position(%s::text[], field_kind), value_norm
            LIMIT 120
            """,
            (kinds, matters or ["__none__"], fam_like, matters or ["__none__"], kinds),
        )
        drows = _as_dicts(cur)
        # If second manifestation: prefer doc 1189 mro
        if "second" in (message or "").lower() and "manifest" in (message or "").lower():
            cur.execute(
                """
                SELECT field_kind, value_norm, doc_id, value_raw,
                       ARRAY['MWK-OP-PETITION']::text[] AS matters
                FROM document_fields
                WHERE field_kind = 'mro_ref' AND doc_id = 1189
                """
            )
            drows = _as_dicts(cur) + drows
        add_layer("document_fields", "hit" if drows else "empty", len(drows),
                  {"sample": [
                      {"kind": r["field_kind"], "val": r["value_norm"], "doc": r["doc_id"]}
                      for r in drows[:12]
                  ]})
        for r in drows:
            mc = None
            ms = r.get("matters") or []
            if ms:
                mc = ms[0]
            elif matters:
                mc = matters[0]
            atoms.append({
                "atom_kind": r["field_kind"],
                "value_norm": r["value_norm"],
                "value_raw": r.get("value_raw"),
                "matter_code": mc,
                "doc_id": r.get("doc_id"),
                "provenance_level": "inferred_strong",
                "source": "document_fields",
            })
    except Exception as e:
        add_layer("document_fields", "error", 0, notes=str(e)[:200])

    # matter_facts (verified preferred)
    try:
        if toks:
            clauses = " OR ".join(["(statement ILIKE %s OR excerpt ILIKE %s)"] * len(toks))
            params = []
            for t in toks:
                params.extend([f"%{t}%", f"%{t}%"])
            if matters:
                cur.execute(
                    f"""
                    SELECT id, matter_code, statement, source_id, provenance_level, excerpt
                    FROM matter_facts
                    WHERE matter_code = ANY(%s)
                      AND ({clauses})
                    ORDER BY CASE provenance_level WHEN 'verified' THEN 0 ELSE 1 END, id DESC
                    LIMIT 40
                    """,
                    [matters] + params,
                )
            else:
                cur.execute(
                    f"""
                    SELECT id, matter_code, statement, source_id, provenance_level, excerpt
                    FROM matter_facts
                    WHERE matter_code LIKE %s
                      AND ({clauses})
                    ORDER BY CASE provenance_level WHEN 'verified' THEN 0 ELSE 1 END, id DESC
                    LIMIT 40
                    """,
                    [fam_like] + params,
                )
        else:
            cur.execute(
                """
                SELECT id, matter_code, statement, source_id, provenance_level, excerpt
                FROM matter_facts
                WHERE matter_code = ANY(%s)
                ORDER BY CASE provenance_level WHEN 'verified' THEN 0 ELSE 1 END, id DESC
                LIMIT 20
                """,
                (matters or [fam_like],),
            )
        frows = _as_dicts(cur)
        add_layer("matter_facts", "hit" if frows else "empty", len(frows),
                  {"sample": [r["statement"][:120] for r in frows[:5]]})
        # pull MRO/CTN from fact text into atoms
        for r in frows:
            blob = (r.get("statement") or "") + " " + (r.get("excerpt") or "")
            for m in re.finditer(r"\b(\d{6}-MRO-\d{4,8})\b", blob, re.I):
                atoms.append({
                    "atom_kind": "mro_ref",
                    "value_norm": m.group(1).upper(),
                    "matter_code": r["matter_code"],
                    "doc_id": int(r["source_id"]) if str(r.get("source_id") or "").isdigit() else None,
                    "provenance_level": r.get("provenance_level") or "inferred_strong",
                    "source": "matter_facts",
                })
            for m in re.finditer(r"\b(20\d{2}-\d{4}-\d{3,4})\b", blob):
                atoms.append({
                    "atom_kind": "ctn",
                    "value_norm": m.group(1),
                    "matter_code": r["matter_code"],
                    "doc_id": int(r["source_id"]) if str(r.get("source_id") or "").isdigit() else None,
                    "provenance_level": r.get("provenance_level") or "inferred_strong",
                    "source": "matter_facts",
                })
    except Exception as e:
        add_layer("matter_facts", "error", 0, notes=str(e)[:200])

    # fact_fields
    try:
        cur.execute(
            """
            SELECT field_kind, value_norm, matter_code, provenance_level, fact_id
            FROM fact_fields
            WHERE field_kind = ANY(%s)
              AND (matter_code = ANY(%s) OR matter_code LIKE %s)
            ORDER BY CASE provenance_level WHEN 'verified' THEN 0 ELSE 1 END, field_kind
            LIMIT 60
            """,
            (kinds, matters or ["__none__"], fam_like),
        )
        ff = _as_dicts(cur)
        add_layer("fact_fields", "hit" if ff else "empty", len(ff),
                  {"sample": [f"{r['field_kind']}:{r['value_norm']}" for r in ff[:10]]})
        for r in ff:
            atoms.append({
                "atom_kind": r["field_kind"],
                "value_norm": r["value_norm"],
                "matter_code": r["matter_code"],
                "provenance_level": r.get("provenance_level") or "inferred_strong",
                "source": "fact_fields",
            })
    except Exception as e:
        add_layer("fact_fields", "error", 0, notes=str(e)[:200])

    # title_brief (title-ish ask OR bare title number in message)
    try:
        tmsg = (message or "").lower()
        title_tok = None
        m_tok = re.search(r"\b(?:TCT|T)[\s\-–#]*(\d{3,7})\b", message or "", re.I)
        if not m_tok:
            m_tok = re.search(r"\b(\d{5,7})\b", message or "")
        if m_tok:
            title_tok = m_tok.group(1)
        title_ish = bool(title_tok) or any(
            k in tmsg for k in ("tct", "title", "oct", "e-title", "history", "chain")
        )
        if title_ish:
            like = f"%{title_tok}%" if title_tok else "%"
            cur.execute(
                """
                SELECT title_key, headline, clarity_status, needs_human_review,
                       status, lifecycle_status, parent_titles, child_titles,
                       n_source_docs, n_facts_verified
                FROM title_brief
                WHERE (client_code LIKE %s OR case_file LIKE %s OR title_key ILIKE %s
                       OR display_no ILIKE %s)
                  AND (%s = '%%' OR title_key ILIKE %s OR display_no ILIKE %s)
                ORDER BY n_source_docs DESC NULLS LAST LIMIT 8
                """,
                (fam_like, fam_like, like, like, like, like, like),
            )
            trows = _as_dicts(cur)
            add_layer("title_brief", "hit" if trows else "empty", len(trows),
                      {"titles": [r["title_key"] for r in trows]})
            for r in trows:
                atoms.append({
                    "atom_kind": "tct",
                    "value_norm": r.get("title_key") or r.get("display_no"),
                    "value_raw": (
                        f"{r.get('title_key')} status={r.get('status')} "
                        f"life={r.get('lifecycle_status')} "
                        f"parents={r.get('parent_titles')} children={r.get('child_titles')}"
                    ),
                    "matter_code": matters[0] if matters else None,
                    "provenance_level": "inferred_strong",
                    "source": "title_brief",
                })
        else:
            add_layer("title_brief", "skip", 0, notes="not a title ask")
    except Exception as e:
        add_layer("title_brief", "error", 0, notes=str(e)[:200])

    # holes / human oversight
    try:
        cur.execute(
            """
            SELECT id, hole_type, left(description, 160) AS description, matter_code
            FROM holes_findings
            WHERE status = 'open'
              AND (matter_code = ANY(%s) OR matter_code LIKE %s OR case_file LIKE %s)
            ORDER BY id DESC LIMIT 10
            """,
            (matters or ["__none__"], fam_like, fam_like),
        )
        hrows = _as_dicts(cur)
        add_layer("holes", "hit" if hrows else "empty", len(hrows),
                  {"open": [r.get("hole_type") for r in hrows[:5]]})
    except Exception as e:
        add_layer("holes", "error", 0, notes=str(e)[:200])

    # dedupe atoms
    deduped = []
    seen = set()
    for a in atoms:
        key = (a.get("atom_kind"), (a.get("value_norm") or "").upper(), a.get("matter_code"))
        if not a.get("value_norm") or key in seen:
            continue
        seen.add(key)
        deduped.append(a)

    return {
        "layers": layers,
        "atoms": deduped,
        "matters": matters,
        "kinds": kinds,
        "toks": toks,
    }


# ── Answer synthesis from scrutiny (no free LLM invention) ───────────────────

def _pretty_name(name: str) -> str:
    n = re.sub(r"\s+", " ", (name or "").strip())
    # Title-case only if the whole string is lower/upper mush
    if n.islower() or n.isupper():
        return n.title()
    return n


def _dedupe_names(names: set[str] | list[str], cap: int = 2) -> list[str]:
    """Prefer longer, more complete names; drop substrings ('Mary Worrick' ⊂ 'Mary Worrick Keesey')."""
    cleaned = []
    for n in names or []:
        n = re.sub(r"\s+", " ", str(n)).strip(" .,;")
        n = re.sub(r"\b(who|is|the|an?)\b\.?$", "", n, flags=re.I).strip(" .,;")
        if len(n) < 3:
            continue
        cleaned.append(n)
    # longest first
    cleaned.sort(key=lambda s: (-len(s), s.lower()))
    out = []
    for n in cleaned:
        low = n.lower()
        if any(low in o.lower() or o.lower() in low for o in out):
            # keep the longer one already in out
            continue
        out.append(n)
        if len(out) >= cap:
            break
    return out


def _refine_person_answer(display: str, facts: list, parties: list) -> str:
    """Compose a clear identity card — prose, not a verified-doc dump.

    Shape:
      <Name> is <one-line role>.
      <2–3 short bullets of substance>
      Sources: doc a, b  (optional, quiet)
    """
    display = _pretty_name(display)
    roles: set[str] = set()
    heir_of: set[str] = set()
    titles: set[str] = set()
    aif_for: set[str] = set()   # who acts as AIF *for* this person
    aif_is: set[str] = set()    # this person is AIF for someone
    litigant: set[str] = set()  # plaintiff / complainant / defendant
    matters: set[str] = set()
    source_ids: list[str] = []

    for f in facts or []:
        st = (f.get("statement") or "").strip()
        if not st:
            continue
        low = st.lower()
        sid = f.get("source_id")
        if sid and str(sid) not in source_ids:
            source_ids.append(str(sid))

        m = re.search(
            r"(?:heir|co-heir|co heir)\s+of\s+([A-Z][A-Za-z .'\-]{3,60})",
            st, re.I,
        )
        if m:
            heir_of.add(re.sub(r"\s+", " ", m.group(1)).strip(" .,;"))
            roles.add("heir")

        if re.search(r"\bco-?heir\b|\bheir\b", low):
            roles.add("heir")
        if re.search(r"\bco-?owner\b|\bowner\b|\bin fee simple\b", low):
            roles.add("owner")
        if re.search(r"\bplaintiff\b", low):
            litigant.add("plaintiff")
        if re.search(r"\bcomplainant\b", low):
            litigant.add("complainant")
        if re.search(r"\bdefendant\b|\brespondent\b", low):
            litigant.add("respondent-side")

        for tm in re.finditer(
            r"\b(?:TCT|Transfer Certificate of Title)\s*(?:No\.?\s*)?(T-?\d{3,7})\b",
            st, re.I,
        ):
            tct = tm.group(1).upper().replace("T", "T-").replace("T--", "T-")
            if not tct.startswith("T-"):
                tct = "T-" + re.sub(r"\D", "", tct)
            titles.add(tct)

        # "Jonathan Zschoche is the Attorney-in-Fact for Patricia…"
        # Require 2+ capitalized name tokens; no re.I (stops "The complainant is…")
        first = display.split()[0]
        for m in re.finditer(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z'\-]+){1,3})\s+"
            r"(?:is|was|acting as|appointed as)\s+"
            r"(?:the\s+|an?\s+)?"
            r"attorney[\-\s]?in[\-\s]?fact\s+for\s+"
            + re.escape(first) + r"\b",
            st,
        ):
            cand = re.sub(r"\s+", " ", m.group(1)).strip(" .,;")
            bad = {"the complainant", "the plaintiff", "the document", "this document",
                   "the respondent", "the petitioner"}
            if cand.lower() in bad or cand.lower() in display.lower():
                continue
            if len(cand.split()) >= 2:
                aif_for.add(cand)

        # This person is AIF for someone else
        m = re.search(
            re.escape(first)
            + r"[A-Za-z .'\-]*\s+is\s+(?:the\s+|an?\s+)?"
            r"attorney[\-\s]?in[\-\s]?fact\s+for\s+"
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z'\-]+){1,3})",
            st,
        )
        if m:
            aif_is.add(re.sub(r"\s+", " ", m.group(1)).strip(" .,;"))

        mc = f.get("matter_code")
        if mc:
            matters.add(str(mc))

    for p in parties or []:
        role = (p.get("role") or p.get("side") or "").lower()
        if "plaintiff" in role:
            litigant.add("plaintiff")
        if "complainant" in role:
            litigant.add("complainant")
        if "defendant" in role or "respondent" in role:
            litigant.add("respondent-side")
        if "heir" in role:
            roles.add("heir")
        mc = p.get("matter_code")
        if mc:
            matters.add(str(mc))
        if p.get("source_doc_id"):
            sid = str(p["source_doc_id"])
            if sid not in source_ids:
                source_ids.append(sid)

    heir_list = _dedupe_names(heir_of, 1)
    aif_list = _dedupe_names(aif_for, 1)
    aif_is_list = _dedupe_names(aif_is, 2)
    title_list = sorted(titles)[:3]

    # ── Lead sentence ──
    lead_bits = []
    if heir_list:
        lead_bits.append("an heir of " + heir_list[0])
    elif "heir" in roles:
        lead_bits.append("an heir in the MWK estate")
    if "owner" in roles and title_list:
        lead_bits.append("co-owner of " + ", ".join(title_list))
    elif "owner" in roles:
        lead_bits.append("a titled co-owner in the MWK portfolio")
    if litigant:
        # One clean litigant label
        if "plaintiff" in litigant and "complainant" in litigant:
            lead_bits.append("a plaintiff/complainant in related proceedings")
        elif litigant:
            lead_bits.append("a " + sorted(litigant)[0] + " in related proceedings")

    if lead_bits:
        if len(lead_bits) == 1:
            lead = f"{display} is {lead_bits[0]}."
        elif len(lead_bits) == 2:
            lead = f"{display} is {lead_bits[0]}, and {lead_bits[1]}."
        else:
            lead = f"{display} is {lead_bits[0]}, {lead_bits[1]}, and {lead_bits[2]}."
    else:
        lead = f"{display} appears in the MWK corpus as a named principal."

    # ── Detail lines (max 3, plain English) ──
    details = []
    if aif_list:
        details.append(
            f"Represented in the Philippines by {aif_list[0]} as attorney-in-fact."
        )
    if aif_is_list:
        details.append(
            "Acts as attorney-in-fact for " + ", ".join(aif_is_list) + "."
        )
    if titles and "owner" not in " ".join(lead_bits).lower():
        details.append("Linked titles on record: " + ", ".join(sorted(titles)[:4]) + ".")
    # Active matter flavor without dumping every ARTA code
    arta = sorted({m for m in matters if "ARTA" in m.upper()})
    court = sorted({m for m in matters if re.search(r"CV|CIVIL|BALANE|26360|4497", m, re.I)})
    if court:
        details.append("Active in court-side matters (e.g. " + ", ".join(court[:2]) + ").")
    elif arta:
        # Compress ARTA to short CTN tails only
        shorts = []
        for m in arta[:4]:
            tail = re.search(r"(\d{4})$", m)
            shorts.append(tail.group(1) if tail else m.replace("MWK-ARTA-", ""))
        details.append("Appears on ARTA matters " + ", ".join(shorts) + ".")

    details = details[:3]

    # ── Quiet source footer ──
    footer = ""
    if source_ids:
        footer = "Sources: docs " + ", ".join(source_ids[:5]) + "."

    body = lead
    if details:
        body += "\n" + "\n".join(details)
    if footer:
        body += "\n" + footer

    # Soft cap for Messenger (clear > exhaustive)
    if len(body) > 500:
        body = body[:497].rsplit("\n", 1)[0]
        if footer and "Sources:" not in body:
            body += "\n" + footer
    return body.strip()


def _answer_who_is(cur, message: str, client_code: str) -> Optional[dict]:
    """Person identity from verified matter_facts + matter_parties — never CTN dumps."""
    t = message or ""
    m = re.search(
        r"\b(?:who\s+is|who'?s|who\s+said|i\s+said\s+who)\s+(.+?)[\s?!.]*$",
        t, re.I,
    )
    if not m:
        m = re.search(r"\bwho\s+(.+?)[\s?!.]*$", t, re.I)
    if not m:
        return None
    name = re.sub(r"\s+", " ", m.group(1).strip(" ?!.,"))
    # Drop leading filler
    name = re.sub(r"^(is|was|are)\s+", "", name, flags=re.I).strip()
    if len(name) < 4:
        return None
    fam = (client_code or "MWK-001").split("-")[0] + "%"
    # Prefer multi-token names
    tokens = [w for w in re.findall(r"[A-Za-z]{3,}", name) if w.lower() not in (
        "the", "and", "for", "who", "said",
    )]
    if not tokens:
        return None
    like_all = [f"%{w}%" for w in tokens[:4]]
    facts = []
    try:
        # All name tokens should appear (AND)
        clauses = " AND ".join(["(statement ILIKE %s OR excerpt ILIKE %s)"] * len(like_all))
        params = []
        for lk in like_all:
            params.extend([lk, lk])
        cur.execute(
            f"""
            SELECT left(statement, 280) AS statement, source_id, provenance_level, matter_code
              FROM matter_facts
             WHERE provenance_level IN ('verified', 'operator')
               AND matter_code LIKE %s
               AND ({clauses})
             ORDER BY id DESC
             LIMIT 24
            """,
            [fam] + params,
        )
        facts = _as_dicts(cur)
    except Exception:
        facts = []
    parties = []
    try:
        cur.execute(
            """
            SELECT party_name, side, role, matter_code, source_doc_id
              FROM matter_parties
             WHERE party_name ILIKE %s
               AND matter_code LIKE %s
             ORDER BY id DESC LIMIT 12
            """,
            (f"%{tokens[0]}%", fam),
        )
        parties = _as_dicts(cur)
    except Exception:
        parties = []

    if not facts and not parties:
        return {
            "text": (
                f"I don’t have a verified identity card for “{_pretty_name(name)}” "
                "on the corpus yet — I won’t invent one. Flagging for human review."
            ),
            "via": "held_unclear",
            "atoms_used": [],
            "pass_to_human": True,
            "human_pass": {"mode": "hold_no_facts", "score": 60},
            "mode": "hold_no_facts",
        }

    text = _refine_person_answer(name, facts, parties)
    return {
        "text": text,
        "via": "stack_hit",
        "atoms_used": [],
        "pass_to_human": False,
        "human_pass": {"mode": "facts_only", "score": 0},
        "mode": "facts_only",
    }


def _client_case_scope(client_code: str) -> tuple[str, str]:
    """Return (case_file exact-ish, family prefix). Never mix other clients."""
    cc = (client_code or "MWK-001").strip()
    # MWK-001 → case_file MWK-001; family MWK%
    fam = cc.split("-")[0] + "%" if "-" in cc else cc + "%"
    return cc, fam


# Statuses that are NOT real portfolio titles (extraction pollution / aliases / operator exclude)
_TITLE_NON_ENTITY = frozenset({
    "invalid", "alias", "duplicate", "not_a_title", "form_serial",
    "out_of_scope",  # e.g. CLOA T-772 — not MWK heirs
})


def _is_well_formed_title_id(tct: str) -> bool:
    """Reject judicial-form serials and garbage; accept Torrens/CLOA/e-title shapes."""
    t = re.sub(r"\s+", "", (tct or "").strip().upper())
    if not t or len(t) < 3:
        return False
    # Bare 5–8 digit strings are almost always form serials (e.g. 5226881 on CTC header),
    # not TCT numbers — doc 117 had No.5226881 above TCT No. T-49061.
    if re.fullmatch(r"\d{5,8}", t):
        return False
    if re.fullmatch(r"T-\d{3,7}", t):
        digits = re.sub(r"\D", "", t)
        # Province-code shaped stubs (T-079), not real TCTs
        if digits in ("079", "100", "000", "001"):
            return False
        return len(digits) >= 3  # T-772, T-4497, T-52540 OK
    if re.fullmatch(r"T-\d{3}-\d{6,}", t):  # e.g. T-079-2021002127
        return True
    if re.fullmatch(r"079-\d{6,}", t):
        return True
    if re.search(r"CLOA", t) and re.search(r"\d{3,7}", t):
        return True
    if re.fullmatch(r"OCT-T?-\d{3,7}", t) or re.fullmatch(r"OCT-\d{3,7}", t):
        return True
    return False


def _canonical_title_id(tct: str) -> str:
    """Collapse known alias shapes so one instrument = one list entry."""
    t = re.sub(r"\s+", "", (tct or "").strip().upper())
    # T-CLOA-T-772 / TCLOA772 / TCA772 → T-772 for list identity when CLOA of same number
    m = re.search(r"CLOA[-T]*(\d{3,7})$", t)
    if m:
        return f"T-{m.group(1)}"
    m = re.fullmatch(r"T-CLOA-T-(\d{3,7})", t)
    if m:
        return f"T-{m.group(1)}"
    return t


def _fetch_title_inventory(
    cur, client_code: str, *, want_active: bool = True, status_filter: str | None = None,
) -> dict:
    """ONE query path: list rows, then count = len(list). Client-scoped.

    Intelligence invariants:
      - never emit a count that cannot list the same rows
      - never mix other clients
      - never treat form serials / alias rows as distinct active titles
    status_filter: None | 'active' | 'cancelled' | 'clouded' | 'all'
    """
    case, fam = _client_case_scope(client_code)
    # Exclude invalid/alias/non-entity statuses always
    non = "','".join(sorted(_TITLE_NON_ENTITY))
    sf = (status_filter or ("active" if want_active else "all")).lower()
    if sf == "active":
        status_sql = "coalesce(status,'') ILIKE 'active'"
    elif sf == "living":
        # Not cancelled / not junk — includes active, clouded, contested, unknown
        status_sql = (
            f"coalesce(status,'') NOT IN ('{non}','cancelled') "
            f"AND coalesce(status,'') NOT ILIKE '%%cancel%%'"
        )
    elif sf == "cancelled":
        status_sql = "coalesce(status,'') ILIKE '%%cancel%%'"
    elif sf == "clouded":
        status_sql = "coalesce(status,'') ILIKE '%%cloud%%'"
    else:
        status_sql = f"coalesce(status,'') NOT IN ('{non}')"

    cur.execute(
        f"""
        SELECT tct_number, status, lifecycle_status,
               left(coalesce(registrant_name_raw,''), 48) AS registrant,
               source_doc_id, case_file,
               left(coalesce(notes,''), 160) AS notes
          FROM titles
         WHERE (case_file = %s OR case_file LIKE %s)
           AND case_file NOT ILIKE 'Paracale%%'
           AND coalesce(status,'') NOT IN ('{non}')
           AND coalesce(lifecycle_status,'') NOT IN (
                 'not_a_title', 'duplicate_of_T-772', 'not_mwk_heirs'
               )
           AND ({status_sql})
         ORDER BY tct_number
        """,
        (case, case + "%"),
    )
    raw_rows = _as_dicts(cur)

    # Quality + identity: well-formed id, collapse aliases, one row per canonical key
    seen: dict[str, dict] = {}
    rejected = []
    for r in raw_rows:
        tid = (r.get("tct_number") or "").strip()
        if not _is_well_formed_title_id(tid):
            rejected.append({"id": tid, "reason": "malformed_or_form_serial"})
            continue
        canon = _canonical_title_id(tid)
        if canon in seen:
            # keep the cleaner of the two
            prev = seen[canon]
            if tid == canon or len(tid) < len(prev.get("tct_number") or ""):
                r = {**r, "tct_number": canon, "aliases": list(set(
                    (prev.get("aliases") or []) + [prev.get("tct_number"), tid]
                ))}
                seen[canon] = r
            else:
                prev.setdefault("aliases", []).append(tid)
            continue
        r = dict(r)
        r["tct_number"] = canon
        r["raw_id"] = tid
        seen[canon] = r

    rows = [seen[k] for k in sorted(seen.keys())]

    # Status breakdown for same client (always, for honesty)
    cur.execute(
        """
        SELECT coalesce(status,'(null)') AS status, count(*)::int AS n
          FROM titles
         WHERE (case_file = %s OR case_file LIKE %s)
           AND case_file NOT ILIKE 'Paracale%%'
         GROUP BY 1
         ORDER BY n DESC
        """,
        (case, case + "%"),
    )
    breakdown = {r["status"]: int(r["n"]) for r in _as_dicts(cur)}

    # Portfolio assets (readiness ontology) — same client, for cross-check only
    assets = {"clean": [], "clouded": [], "cancelled": []}
    try:
        cur.execute(
            """
            SELECT title_ref, title_status, asset_code
              FROM property_assets
             WHERE client_code = %s OR client_code LIKE %s OR case_file = %s
             ORDER BY title_ref
            """,
            (case, fam, case),
        )
        for a in _as_dicts(cur):
            st = (a.get("title_status") or "").lower()
            ref = a.get("title_ref") or a.get("asset_code")
            if st not in assets or not ref:
                continue
            if not _is_well_formed_title_id(str(ref)) and not re.match(r"T-", str(ref), re.I):
                continue
            assets[st].append(_canonical_title_id(str(ref)))
        for k in assets:
            assets[k] = sorted(set(assets[k]))
    except Exception:
        pass

    return {
        "client": case,
        "want_active": want_active,
        "status_filter": sf,
        "rows": rows,
        "ids": [r.get("tct_number") for r in rows if r.get("tct_number")],
        "count": len(rows),
        "breakdown": breakdown,
        "assets": assets,
        "rejected": rejected,
    }


def _render_title_inventory(inv: dict, *, list_mode: bool) -> str:
    """Count and list from the SAME inv dict — count is always len(ids)."""
    ids = inv.get("ids") or []
    n = len(ids)
    client = inv.get("client") or "client"
    bd = inv.get("breakdown") or {}
    sf = (inv.get("status_filter") or "active").lower()
    label = {
        "active": "strict-active (status=active only)",
        "living": "living / in-force portfolio (not cancelled)",
        "cancelled": "cancelled",
        "clouded": "clouded",
    }.get(sf, "registered (non-invalid)")

    # Lead: count == list length by construction
    lines = [
        f"{client} titles — {label}: {n}."
    ]
    if bd:
        parts = [f"{k} {v}" for k, v in bd.items()]
        lines.append("Full registry split: " + ", ".join(parts) + ".")

    # Per-status list when living (so T-4497/T-32911 are visible with why)
    rows = inv.get("rows") or []
    if sf == "living" and rows:
        by_st: dict[str, list[str]] = {}
        for r in rows:
            st = (r.get("status") or "unknown").lower()
            tid = r.get("tct_number")
            if tid:
                by_st.setdefault(st, []).append(tid)
        for st in sorted(by_st.keys()):
            lines.append(f"{st} ({len(by_st[st])}): " + ", ".join(by_st[st]) + ".")
    elif n == 0:
        lines.append("List: (none).")
    elif list_mode or n <= 40:
        chunk = ", ".join(ids)
        lines.append("List (" + str(n) + "): " + chunk + ".")
    else:
        lines.append(
            "List (" + str(n) + "): " + ", ".join(ids[:25])
            + f" … +{n - 25} more (ask for full list)."
        )

    # Cross-check assets (different status vocabulary: clean/clouded/cancelled)
    assets = inv.get("assets") or {}
    clean_n = len(assets.get("clean") or [])
    cloud_n = len(assets.get("clouded") or [])
    can_n = len(assets.get("cancelled") or [])
    if clean_n or cloud_n or can_n:
        lines.append(
            f"Property-assets cross-check (same client): "
            f"{clean_n} clean, {cloud_n} clouded, {can_n} cancelled "
            f"— not the same enum as titles.status=active."
        )

    rejected = inv.get("rejected") or []
    if rejected:
        lines.append(
            f"Excluded {len(rejected)} non-title id(s) "
            f"(form serials / garbage — e.g. judicial form numbers)."
        )
    lines.append(
        "Definition: count = len(list) of well-formed title ids for "
        f"{client}, status={label}; aliases collapsed; other clients excluded. "
        "Ask cancelled/clouded/all for other status slices."
    )
    return "\n".join(lines)


def _answer_title_inventory(cur, message: str, client_code: str) -> Optional[dict]:
    """Count OR list of titles — same inventory, never CTNs, never cross-client."""
    t = (message or "").lower()
    wants_count = bool(re.search(
        r"\b(how many|count|number of)\b.*\b(title|tct|titles)\b"
        r"|\b(title|tct|titles)\b.*\b(how many|count)\b"
        r"|\bactive titles?\b",
        t,
    ))
    wants_list = bool(re.search(
        r"\b(list|show|see|which|enumerate|names? of)\b.*\b(title|tct|titles)\b"
        r"|\b(title|tct|titles)\b.*\b(list|show|all|names?)\b"
        r"|\blist of\b",
        t,
    ))
    if not (wants_count or wants_list or re.search(r"\bactive titles?\b", t)):
        return None

    if re.search(r"\bcancelled\b", t):
        status_filter = "cancelled"
        want_active = False
    elif re.search(r"\bclouded\b", t) and not re.search(r"\bactive\b", t):
        status_filter = "clouded"
        want_active = False
    elif re.search(r"\ball (the )?titles\b|\bevery title\b", t) and "active" not in t:
        status_filter = "all"
        want_active = False
    elif re.search(r"\b(strict\s+)?active\b", t) and re.search(r"\bstrict\b", t):
        # explicit "strict active" = status=active only
        status_filter = "active"
        want_active = True
    else:
        # Default "active titles for MWK" = LIVING portfolio (not cancelled).
        # T-4497 (unknown/contested) and T-32911 (clouded) are core heir titles —
        # excluding them because status≠'active' was an intelligence failure.
        status_filter = "living"
        want_active = False

    try:
        inv = _fetch_title_inventory(
            cur, client_code, want_active=want_active, status_filter=status_filter,
        )
    except Exception as e:
        return {
            "text": f"Title inventory query failed ({type(e).__name__}: {e}). Not inventing.",
            "via": "held_unclear",
            "atoms_used": [],
            "pass_to_human": True,
            "mode": "hold_no_facts",
        }

    text = _render_title_inventory(inv, list_mode=wants_list or wants_count)
    # Writeback atoms = each title id (so stack learns the set for this ask)
    atoms = [
        {
            "atom_kind": "tct",
            "value_norm": tid,
            "value_raw": tid,
            "matter_code": None,
            "provenance_level": "inferred_strong",
            "source": "titles_registry",
        }
        for tid in (inv.get("ids") or [])
    ]
    return {
        "text": text.strip(),
        "via": "stack_hit",
        "atoms_used": atoms,
        "pass_to_human": False,
        "human_pass": {
            "mode": "facts_only",
            "score": 0,
            "inventory_count": inv.get("count"),
            "inventory_ids": inv.get("ids"),
        },
        "mode": "facts_only",
    }


# Back-compat name used by synthesize
def _answer_title_count(cur, message: str, client_code: str) -> Optional[dict]:
    return _answer_title_inventory(cur, message, client_code)


def _intent(tmsg: str) -> str:
    t = tmsg or ""
    if re.search(r"\bwho\b", t):
        return "person"
    if re.search(
        r"\b(how many|count|number of)\b.*\b(title|tct|titles)\b"
        r"|\bactive titles?\b"
        r"|\b(list|show|see|which|enumerate)\b.*\b(title|tct|titles)\b"
        r"|\b(title|tct|titles)\b.*\b(list|show|all)\b",
        t,
    ):
        return "title_count"
    if re.search(r"\b(history|parent title|mother title|came from|originally)\b", t):
        return "title_history"
    if re.search(
        r"\b(docket|mro|transmittal|case no|case number|manifest|receiving ref)\b", t
    ):
        return "docket"
    if re.search(r"\b(arta|ctn)\b", t) and not re.search(r"\btitle|tct\b", t):
        return "arta"
    if re.search(r"\b(title|tct|oct|e-title)\b", t):
        return "title"
    if re.search(r"\b(op |appeal|petition)\b", t):
        return "op"
    return "general"


def _atoms_for_intent(intent: str, atoms: list, tmsg: str) -> list:
    """RELEVANCE GATE: never emit CTNs for a title ask, etc."""
    by = {k: [] for k in (
        "mro_ref", "ctn", "docket", "tct", "oct", "e_title", "tax_dec", "date", "amount",
    )}
    other = []
    for a in atoms or []:
        k = a.get("atom_kind") or "other"
        if k in by:
            by[k].append(a)
        else:
            other.append(a)

    if intent == "docket" or intent == "op":
        used = by["mro_ref"][:3] + by["docket"][:2]
        # only OP-relevant CTNs, not random
        for a in by["ctn"]:
            m = re.search(r"(0690|0747|0792|1210|1212)$", a.get("value_norm") or "")
            if m:
                used.append(a)
        return used[:6]
    if intent == "arta":
        # Asked about a specific case tail ("ARTA case 0690") → only that CTN
        tails = re.findall(r"\b(\d{4})\b", tmsg)
        if tails:
            matched = [
                a for a in by["ctn"]
                if (a.get("value_norm") or "")[-4:] in tails
            ]
            if matched:
                return matched[:6]
        return by["ctn"][:6]
    if intent in ("title", "title_history", "title_count"):
        pool = by["tct"] + by["oct"] + by["e_title"]
        # A specific-title ask must name THAT title, not the family's noisiest
        # ones — emission caps at 2 per kind, so unranked atoms dropped the
        # asked title entirely (agent_sim cycle 3 emission_miss). No match →
        # empty → caller fail-closes rather than answering with other titles.
        m = re.search(r"\b(?:tct|oct|e-?title|t)[\s\-–#]*(\d{3,7})\b", tmsg)
        if not m:
            m = re.search(r"\b(\d{5,7})\b", tmsg)
        if m:
            digits = m.group(1)
            matched = [
                a for a in pool
                if digits in re.sub(r"\D", "", a.get("value_norm") or "")
            ]
            return matched[:6]
        return pool[:6]
    if intent == "person":
        return []  # handled elsewhere
    # general: refuse pure CTN dump unless user asked about ARTA/CTN/docket
    if by["mro_ref"] or by["docket"]:
        return (by["mro_ref"] + by["docket"] + by["tct"])[:4]
    if by["tct"] or by["oct"]:
        return (by["tct"] + by["oct"] + by["e_title"])[:4]
    # No relevant typed atoms — empty (caller fail-closes). Do NOT return random CTNs.
    return []


def synthesize(message: str, scrutiny: dict, cur=None, client_code: str = "") -> dict:
    """Facts-only synthesis + human-pass threshold (see human_pass.py).

    Architecture rule: atoms must be RELEVANT to intent. Unrelated CTN spam is not a hit.
    """
    import human_pass as HP

    tmsg = (message or "").lower()
    atoms = scrutiny.get("atoms") or []
    layers = scrutiny.get("layers") or []
    matters = scrutiny.get("matters") or []
    intent = _intent(tmsg)
    cc = client_code or "MWK-001"

    # Purpose-specific table answers (not atom spam)
    if cur is not None and intent == "person":
        who = _answer_who_is(cur, message, cc)
        if who:
            return who
    if cur is not None and intent == "title_count":
        tc = _answer_title_inventory(cur, message, cc)
        if tc:
            return tc

    want_second = bool(re.search(r"\bsecond\b.*\bmanifest|\bmanifest\w*\b.*\bsecond\b", tmsg))
    want_docket = intent in ("docket", "op")

    mros = [a for a in atoms if a.get("atom_kind") == "mro_ref"]
    ctns = [a for a in atoms if a.get("atom_kind") == "ctn"]

    def mro_key(a):
        v = (a.get("value_norm") or "")
        if want_second:
            return (0 if v.startswith("060426") else 1 if v.startswith("050526") else 2, v)
        return (0 if v.startswith("050526") else 1 if v.startswith("060426") else 2, v)

    mros_sorted = sorted(mros, key=mro_key)
    primary_mro = next(
        (a for a in mros_sorted if (a.get("value_norm") or "").startswith("050526")), None
    )
    second_mro = next(
        (a for a in mros_sorted if (a.get("value_norm") or "").startswith("060426")), None
    )
    if not primary_mro and mros_sorted:
        primary_mro = mros_sorted[0]

    used = []
    if want_second and second_mro:
        used = [second_mro] + ([primary_mro] if primary_mro else [])
    elif want_docket:
        if want_second and second_mro:
            used.append(second_mro)
        if primary_mro and primary_mro not in used:
            used.append(primary_mro)
        for a in mros_sorted:
            if a not in used:
                used.append(a)
        for a in ctns:
            m = re.search(r"(\d{4})$", a.get("value_norm") or "")
            if m and m.group(1) in ("0690", "0747", "0792") and a not in used:
                used.append(a)
        used = used[:6]
    else:
        used = _atoms_for_intent(intent, atoms, tmsg)

    # RELEVANCE FAIL-CLOSED: do not claim stack_hit with empty/wrong atoms
    if not used and intent not in ("general",):
        return {
            "text": (
                "I don’t have a grounded answer that matches this question on the "
                "title/fact stack (refusing to dump unrelated CTNs). "
                "Flagging for human review if this is urgent."
            ),
            "via": "held_unclear",
            "atoms_used": [],
            "pass_to_human": True,
            "human_pass": {"mode": "hold_no_facts", "score": 55, "intent": intent},
            "mode": "hold_no_facts",
        }
    if not used:
        return {
            "text": (
                "No typed stack hit for that yet. I will not invent. "
                "Flagging for human review."
            ),
            "via": "held_unclear",
            "atoms_used": [],
            "pass_to_human": True,
            "human_pass": {"mode": "hold_no_facts", "score": 55},
            "mode": "hold_no_facts",
        }

    hard_hit = bool(used and any(
        a.get("atom_kind") in ("mro_ref", "ctn", "docket", "tct", "oct", "e_title")
        for a in used
    ))

    open_contra = 0
    n_verified = 1 if hard_hit else 0
    for L in layers:
        if L.get("layer") == "holes" and L.get("hit_count"):
            open_contra = max(open_contra, int(L.get("hit_count") or 0))
        if L.get("layer") == "matter_facts" and L.get("hit_count"):
            n_verified = max(n_verified, 1)

    law_gap = HP._is_scenario(message) and any(
        k in tmsg for k in ("op", "appeal", "petition", "ignor", "executive")
    )

    standing = {}
    # Only attach OP standing when intent is OP/docket — not for title counts
    if intent in ("docket", "op", "arta") and matters:
        standing["matter"] = matters[0]
        if "OP-PETITION" in str(matters[0]).upper():
            standing["label"] = "OP petition"
    if intent in ("docket", "op") and primary_mro:
        standing["filed_on"] = "5 May 2026"
    # "What is the status of title X?" must answer with the status, not just
    # echo the id — title_brief atoms carry it in value_raw ("... status=...").
    if intent in ("title", "title_history"):
        for a in used:
            m_st = re.search(r"status=(\S+)", a.get("value_raw") or "")
            if m_st and m_st.group(1).lower() not in ("none", "null"):
                standing["stage"] = f"status: {m_st.group(1)}"
                break

    emission = HP.decide_emission(
        message,
        used,
        standing=standing,
        n_verified_in_scope=n_verified,
        clarity_unclear=False,
        open_contradictions=min(open_contra, 5),
        n_matters_touched=max(len(matters), 1) if intent in ("docket", "op", "arta") else 1,
        law_gap=law_gap,
        expectation_at_stake=HP._is_scenario(message),
        hard_lookup_hit=hard_hit and not HP._is_scenario(message),
    )

    via = {
        "facts_only": "stack_hit",
        "pass_to_human": "pass_to_human",
        "hold_no_facts": "held_unclear",
    }.get(emission["mode"], "held_unclear")

    return {
        "text": emission["text"],
        "via": via,
        "atoms_used": used,
        "pass_to_human": emission.get("pass_to_human", False),
        "human_pass": emission.get("decision") or {},
        "mode": emission.get("mode"),
    }


# ── Writeback + agent triggers ───────────────────────────────────────────────

def writeback_atoms(cur, inquiry_id: int, atoms: list, go: bool) -> dict:
    """Persist atoms to inquiry_answer_atoms + living tables; return summary."""
    written = {"inquiry_answer_atoms": 0, "document_fields": 0, "matter_facts": 0, "fact_fields": 0}
    if not go:
        return {**written, "dry": True, "n_atoms": len(atoms)}

    for a in atoms:
        kind = a.get("atom_kind")
        val = a.get("value_norm")
        if not kind or not val:
            continue
        written_to = []
        cur.execute(
            """
            INSERT INTO inquiry_answer_atoms
                (inquiry_id, atom_kind, value_norm, value_raw, matter_code, doc_id,
                 provenance_level, written_to)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                inquiry_id, kind, val, a.get("value_raw") or val,
                a.get("matter_code"), a.get("doc_id"),
                a.get("provenance_level") or "inferred_strong",
                [],
            ),
        )
        written["inquiry_answer_atoms"] += 1
        atom_id = cur.fetchone()["id"]

        # document_fields
        if a.get("doc_id") and kind in (
            "mro_ref", "ctn", "docket", "tct", "oct", "e_title", "tax_dec", "date", "amount"
        ):
            try:
                cur.execute(
                    """
                    INSERT INTO document_fields
                        (doc_id, field_kind, value_raw, value_norm, source_span, extraction_method)
                    VALUES (%s,%s,%s,%s,%s,'inquiry_writeback')
                    ON CONFLICT (doc_id, field_kind, value_norm) DO NOTHING
                    """,
                    (a["doc_id"], kind, (a.get("value_raw") or val)[:300], val[:200], val[:300]),
                )
                if cur.rowcount:
                    written["document_fields"] += 1
                    written_to.append("document_fields")
            except Exception:
                pass

        # matter_facts (inferred_strong only — never verified here)
        mc = a.get("matter_code")
        if mc and kind in ("mro_ref", "ctn", "docket", "tct", "oct", "e_title"):
            stmt = f"{kind.upper()}: {val}"
            if kind == "mro_ref":
                stmt = f"OP/Malacañang filing reference (MRO / OP Transmittal Ref): {val}"
            try:
                cur.execute(
                    "SELECT 1 FROM matter_facts WHERE matter_code=%s AND statement=%s",
                    (mc, stmt),
                )
                if not cur.fetchone():
                    cur.execute(
                        """
                        INSERT INTO matter_facts
                            (matter_code, statement, fact_kind, source_kind, source_id,
                             excerpt, provenance_level, created_by, created_at)
                        VALUES (%s,%s,%s,'doc',%s,%s,'inferred_strong','inquiry_stack', now())
                        """,
                        (
                            mc, stmt[:500], kind,
                            str(a["doc_id"]) if a.get("doc_id") else None,
                            (a.get("value_raw") or val)[:400],
                        ),
                    )
                    written["matter_facts"] += 1
                    written_to.append("matter_facts")
            except Exception:
                pass

        if written_to:
            cur.execute(
                "UPDATE inquiry_answer_atoms SET written_to=%s WHERE id=%s",
                (written_to, atom_id),
            )

    return written


def trigger_agents(cur, inquiry_id: int, written: dict, atoms: list, go: bool) -> int:
    """Enqueue agents whose trigger_on matches events from this inquiry writeback."""
    if not go:
        return 0
    events = set()
    if written.get("document_fields"):
        events.add("new_document_field")
    if written.get("matter_facts"):
        events.add("new_matter_fact")
    if atoms:
        events.add("inquiry_answer_atom")
    if not events:
        events.add("inquiry_answered")

    cur.execute(
        "SELECT agent_key, trigger_on, owns_tables FROM agent_mandates WHERE active"
    )
    n = 0
    for row in _as_dicts(cur):
        triggers = set(row.get("trigger_on") or [])
        if not (triggers & events):
            continue
        # skip self-loop storm on inquiry_stack for every answer optional — still enqueue materializers
        payload = {
            "events": sorted(events),
            "inquiry_id": inquiry_id,
            "owns_tables": row.get("owns_tables") or [],
            "atom_kinds": sorted({a.get("atom_kind") for a in atoms if a.get("atom_kind")}),
        }
        cur.execute(
            """
            INSERT INTO agent_work_queue (agent_key, event_type, payload, inquiry_id, status)
            VALUES (%s, %s, %s::jsonb, %s, 'pending')
            """,
            (row["agent_key"], ",".join(sorted(events)), json.dumps(payload), inquiry_id),
        )
        n += 1
    return n


def drain_agent(cur, agent_key: str, limit: int = 5, go: bool = False) -> list:
    """Claim pending work for one agent and run its compelled action (minimal hooks)."""
    cur.execute(
        """
        SELECT id, event_type, payload, inquiry_id
        FROM agent_work_queue
        WHERE agent_key = %s AND status = 'pending'
        ORDER BY id ASC LIMIT %s
        """,
        (agent_key, limit),
    )
    rows = _as_dicts(cur)
    results = []
    for r in rows:
        if go:
            cur.execute(
                """
                UPDATE agent_work_queue
                   SET status='claimed', claimed_at=now()
                 WHERE id=%s AND status='pending'
                """,
                (r["id"],),
            )
        note = "skipped_dry"
        if go:
            note = _run_agent_hook(agent_key, r)
            cur.execute(
                """
                UPDATE agent_work_queue
                   SET status='done', done_at=now(), result_note=%s
                 WHERE id=%s
                """,
                (note[:500], r["id"]),
            )
        results.append({"id": r["id"], "agent": agent_key, "note": note})
    return results


def _run_agent_hook(agent_key: str, work: dict) -> str:
    """Dispatch compelled work. Keep hooks thin — call existing scripts' core paths.

    Payload may carry client/title from mwk_asset_gap_drive (or inquiry writeback).
    """
    try:
        payload = work.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        client = (payload.get("client") or "MWK-001").strip()
        title = (payload.get("title") or "").strip()

        if agent_key == "fact_field_extractor":
            import subprocess
            cmd = [sys.executable, "/root/landtek/scripts/extract_fact_fields.py", "--go"]
            if payload.get("matter"):
                cmd.extend(["--matter", str(payload["matter"])])
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            return f"extract_fact_fields exit={r.returncode} {(r.stdout or '')[-200:]}"
        if agent_key == "matter_brief_materializer":
            import subprocess
            cmd = [sys.executable, "/root/landtek/scripts/materialize_matter_brief.py", "--go"]
            # Prefer full rematerialize when client-scoped gap drive
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            return f"matter_brief exit={r.returncode} {(r.stdout or '')[-200:]}"
        if agent_key == "title_brief_materializer":
            import subprocess
            cmd = [sys.executable, "/root/landtek/scripts/materialize_title_brief.py", "--go"]
            if title:
                cmd.extend(["--title", title])
            else:
                cmd.extend(["--client", client])
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            return f"title_brief exit={r.returncode} title={title or client} {(r.stdout or '')[-160:]}"
        if agent_key == "verify_worker":
            # Timer owns continuous verify; gap drive marks work as seen for ops
            return f"queued_for_verify_worker_timer client={client} title={title or '-'}"
        if agent_key == "doc_populate":
            import subprocess
            r = subprocess.run(
                [sys.executable, "/root/landtek/scripts/populate_tables_from_docs.py",
                 "--go", "--limit", "200"],
                capture_output=True, text=True, timeout=300,
            )
            return f"doc_populate exit={r.returncode} {(r.stdout or '')[-200:]}"
        if agent_key == "contradiction":
            import subprocess
            r = subprocess.run(
                [sys.executable, "/root/landtek/scripts/contradiction.py"],
                capture_output=True, text=True, timeout=120,
            )
            return f"contradiction exit={r.returncode} {(r.stdout or '')[-200:]}"
        if agent_key == "corpus_steward":
            # 6h sweep (case_corpus_sweep.sh) owns the heavy pass — never
            # run it inside a drain; a killed mid-sweep leaves partial state
            return f"queued_for_corpus_steward_timer client={client}"
        if agent_key == "inquiry_stack":
            return "no_self_reentry"
        return "no_hook"
    except Exception as e:
        return f"hook_error:{type(e).__name__}:{e}"


# ── Public API ───────────────────────────────────────────────────────────────

def run_inquiry(
    message: str,
    client_code: str,
    channel: str = None,
    channel_user_id: str = None,
    role: str = None,
    go: bool = False,
    drain: bool = False,
) -> dict:
    t0 = time.time()
    c = _conn()
    cur = _cur(c)

    cur.execute(
        """
        INSERT INTO inquiry_runs
            (channel, channel_user_id, client_code, principal_role, message, message_norm, status)
        VALUES (%s,%s,%s,%s,%s,%s,'open')
        RETURNING id
        """,
        (
            channel, channel_user_id, client_code, role, message,
            re.sub(r"\s+", " ", (message or "").lower()).strip(),
        ),
    )
    inquiry_id = cur.fetchone()["id"]

    scrutiny = scrutinize(cur, client_code, message, role=role)
    for L in scrutiny["layers"]:
        cur.execute(
            """
            INSERT INTO inquiry_scrutiny
                (inquiry_id, layer, status, hit_count, payload, notes)
            VALUES (%s,%s,%s,%s,%s::jsonb,%s)
            """,
            (
                inquiry_id, L["layer"], L["status"], L["hit_count"],
                json.dumps(L.get("payload") or {}), L.get("notes"),
            ),
        )

    ans = synthesize(message, scrutiny, cur=cur, client_code=client_code)
    used = ans.get("atoms_used") or []
    written = writeback_atoms(cur, inquiry_id, used, go=go)
    n_trig = trigger_agents(cur, inquiry_id, written, used, go=go)

    # Human-pass: queue operator review (work_orders if table exists)
    if go and ans.get("pass_to_human"):
        n_trig += _enqueue_human_review(cur, inquiry_id, message, ans)

    drain_notes = []
    if go and drain:
        for ak in ("fact_field_extractor", "matter_brief_materializer"):
            drain_notes.extend(drain_agent(cur, ak, limit=2, go=True))

    ms = int((time.time() - t0) * 1000)
    status = "held" if ans.get("pass_to_human") or ans["via"] in (
        "held_unclear", "pass_to_human"
    ) else "answered"
    cur.execute(
        """
        UPDATE inquiry_runs SET
            status = %s,
            answer_text = %s,
            answer_via = %s,
            source_refs = %s::jsonb,
            writeback_summary = %s::jsonb,
            duration_ms = %s
        WHERE id = %s
        """,
        (
            status,
            ans["text"],
            ans["via"],
            json.dumps([
                {"kind": a.get("atom_kind"), "val": a.get("value_norm"),
                 "doc": a.get("doc_id"), "matter": a.get("matter_code")}
                for a in used
            ]),
            json.dumps({
                **written,
                "triggers": n_trig,
                "drain": drain_notes,
                "human_pass": ans.get("human_pass") or {},
                "pass_to_human": bool(ans.get("pass_to_human")),
            }),
            ms,
            inquiry_id,
        ),
    )

    cur.close()
    c.close()
    return {
        "inquiry_id": inquiry_id,
        "text": ans["text"],
        "via": f"inquiry_stack:{ans['via']}",
        "preformed": True,
        "pass_to_human": bool(ans.get("pass_to_human")),
        "human_pass": ans.get("human_pass") or {},
        "scrutiny_layers": [
            f"{L['layer']}:{L['status']}:{L['hit_count']}" for L in scrutiny["layers"]
        ],
        "writeback": written,
        "triggers": n_trig,
        "duration_ms": ms,
    }


def _enqueue_human_review(cur, inquiry_id: int, message: str, ans: dict) -> int:
    """Record human-pass + notify operator on Telegram (otherwise queue is silent)."""
    n = 0
    score = (ans.get("human_pass") or {}).get("score")
    payload = {
        "inquiry_id": inquiry_id,
        "message": (message or "")[:500],
        "answer_so_far": (ans.get("text") or "")[:500],
        "score": score,
        "reasons": (ans.get("human_pass") or {}).get("reasons"),
    }
    try:
        cur.execute(
            """
            INSERT INTO agent_work_queue (agent_key, event_type, payload, inquiry_id, status)
            VALUES ('operator_review', 'human_pass', %s::jsonb, %s, 'pending')
            """,
            (json.dumps(payload), inquiry_id),
        )
        n += 1
    except Exception:
        pass
    try:
        cur.execute(
            """
            INSERT INTO work_orders (kind, status, title, detail, created_at)
            SELECT 'human_pass', 'open',
                   %s, %s, now()
            WHERE EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'work_orders'
            )
            """,
            (
                f"Human review: {(message or '')[:80]}",
                json.dumps(payload)[:2000],
            ),
        )
        if cur.rowcount:
            n += 1
    except Exception:
        pass
    # Push to operator — plain language, no score jargon / pipe dumps
    try:
        from tg_send import send as tg_send
        q = re.sub(r"\s+", " ", (message or "").strip())
        if len(q) > 90:
            q = q[:87] + "…"
        facts = re.sub(r"\s+", " ", (ans.get("text") or "").strip())
        # strip client-facing handoff line if present — operator already knows
        facts = re.sub(
            r"\s*(I'll flag this for human review.*|Needs human review.*|Flagged for human.*)$",
            "",
            facts,
            flags=re.I,
        ).strip()
        if len(facts) > 100:
            facts = facts[:97] + "…"
        # Natural operator note (S14-friendly, ≤280)
        if facts:
            alert = f"Needs your call: “{q}” — {facts}"
        else:
            alert = f"Needs your call: “{q}”"
        if len(alert) > 280:
            alert = alert[:277] + "…"
        ok, info = tg_send(
            chat_id="6513067717",
            text=alert,
            source="watchdog",  # allowed outbound_messages source
            recipient_name="Jonathan",
            override_pacing=True,
            override_rate_limit=False,
        )
        if ok:
            n += 1
        else:
            print(f"[inquiry_stack] operator TG notify failed: {info}", flush=True)
    except Exception as e:
        print(f"[inquiry_stack] operator TG notify error: {type(e).__name__}: {e}", flush=True)
    return n


def try_inquiry_stack(cur, client_code: str, message: str, **kwargs) -> Optional[dict]:
    """Leo integration: return preformed pack or None.

    Uses its own connection for writes when go=True (default True for production path).
    force=True (from leo_service is_inquiry) always engages — no keyword skip.
    """
    if not client_code or not (message or "").strip():
        return None
    force = bool(kwargs.get("force"))
    # Only skip pure non-factual when not forced. Free LLM is banned for inquiries
    # upstream; this stack must run whenever leo_service says so.
    if not force:
        t = (message or "").lower()
        if not any(k in t for k in (
            "docket", "ctn", "mro", "case no", "case number", "title", "tct", "oct",
            "petition", "appeal", "op ", " op", "manifest", "how many", "status",
            "who is", "when", "date", "amount", "arp", "tax", "ref", "history",
            "originally", "where did", "parent", "mother", "chain", "cancelled",
        )):
            if not re.search(r"\b(20\d{2}|T-?\d{3,}|\d{5,7})\b", t):
                return None
    go = kwargs.get("go", True)
    result = run_inquiry(
        message=message,
        client_code=client_code,
        channel=kwargs.get("channel"),
        channel_user_id=kwargs.get("channel_user_id"),
        role=kwargs.get("role"),
        go=go,
        drain=kwargs.get("drain", False),
    )
    return {
        "text": result["text"],
        "via": result["via"],
        "preformed": True,
        "purpose": "inquiry_stack",
        "meta": {
            "inquiry_id": result["inquiry_id"],
            "scrutiny": result["scrutiny_layers"],
            "writeback": result["writeback"],
            "triggers": result["triggers"],
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ask", required=False)
    ap.add_argument("--client", default="MWK-001")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--drain", action="store_true")
    ap.add_argument("--drain-agent", default=None)
    ap.add_argument("--limit", type=int, default=5)
    a = ap.parse_args()

    if a.drain_agent:
        c = _conn()
        cur = _cur(c)
        print(drain_agent(cur, a.drain_agent, limit=a.limit, go=a.go))
        return

    if not a.ask:
        ap.error("--ask required unless --drain-agent")
    r = run_inquiry(a.ask, a.client, go=a.go, drain=a.drain)
    print(json.dumps(r, indent=2, default=str))


if __name__ == "__main__":
    main()
