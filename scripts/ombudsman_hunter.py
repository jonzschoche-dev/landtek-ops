#!/usr/bin/env python3
"""ombudsman_hunter.py — the offensive Ombudsman layer of the Grounded Matter Engine.

The ARTA cluster is a property grievance pled in a red-tape forum that structurally trends to
closure. The Office of the Ombudsman is the SHARPER forum: it prosecutes the *public officers
themselves* for graft (R.A. 3019), the Code of Conduct (R.A. 6713), and the RPC public-officer
crimes. strategy_engine already names "COA / Ombudsman / ARTA Sec.21 legal pressure" as the MWK
north-star lever — this engine is what OPERATIONALIZES the Ombudsman half of that lever.

What it does, deterministically ($0):
  1. CULL     — assemble the roster of public officers who touched the matters (seed + corpus scan).
  2. PROFILE  — gather each officer's incidents across the whole portfolio (cross-matter).
  3. ELEMENTS — map incidents onto the graft/misconduct templates; per-element have/thin/missing.
  4. RIPENESS — route the forum (elective->Ombudsman, appointive/career->CSC; SG>=27->Sandiganbayan),
                check the prescription posture, and gate on element strength.
  5. SCORE    — rank by strength x north-star leverage x forum-fit.
  6. EMIT     — upsert ombudsman_candidates with EVIDENCE HANDLES (fact_ids / doc ids); for RIPE
                candidates, write a case_synthesizer playbook JSON so the existing dossier machinery
                renders the grounded Complaint-Affidavit support.

Discipline (load-bearing):
  * Candidates are LEADS, not verified facts (provenance=inferred_strong). Every signal a candidate
    claims points to a source row — no naked assertions.
  * The engine NEVER files and NEVER sets status='filed'. Filing against a named public officer is a
    held, human-approved decision. The ripe ceiling is 'held_for_filing'.
  * Statute PERIODS (prescription, counter-affidavit windows) are flagged NEEDS-COUNSEL-VERIFICATION,
    matching the agency:OMBUDSMAN desk posture in agents.py.

  python3 scripts/ombudsman_hunter.py --scan            # run the pipeline, write candidates
  python3 scripts/ombudsman_hunter.py --board           # phone-friendly ranked leads
  python3 scripts/ombudsman_hunter.py --candidate 3     # one lead: elements, evidence handles, gaps
  python3 scripts/ombudsman_hunter.py --playbook 3      # emit a case_synthesizer playbook for a RIPE lead
  python3 scripts/ombudsman_hunter.py --law-check       # is the RA 3019/6713/6770 law library embedded?
  python3 scripts/ombudsman_hunter.py --doctrine        # print the templates + roster (dry, no DB)
"""
import argparse
import json
import os
import re
import sys

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# psycopg2 lives on the VPS runtime; --doctrine is dry (no DB) so import lazily to stay runnable
# on the design side too (offline-sovereign ethos).
psycopg2 = None
psycopg2_extras = None


def _load_pg():
    global psycopg2, psycopg2_extras
    if psycopg2 is None:
        import psycopg2 as _pg
        import psycopg2.extras as _pgx
        psycopg2, psycopg2_extras = _pg, _pgx


def _conn():
    _load_pg()
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


# ─────────────────────────────────────────────────────────────────────────────
# DOCTRINE — the acute legal knowledge, as data.
#
# Each template = one theory of liability. `elements` are the things that must be proven;
# `needs` are the SIGNAL keys whose presence makes the element 'have'. `forum_default` routes
# a candidate before capacity is known (overridden by capacity in RIPENESS). Prescription is
# the current posture with the caveat that it is counsel-verifiable, not asserted.
# ─────────────────────────────────────────────────────────────────────────────
VIOLATIONS = {
    "ra3019_3e": {
        "statute": "R.A. 3019, Sec. 3(e)",
        "gist": "manifest partiality / evident bad faith / gross inexcusable negligence causing "
                "undue injury OR giving an unwarranted benefit",
        "forum_default": "OMBUDSMAN",
        "elements": {
            "public_officer":  {"needs": ["official_capacity"],   "label": "respondent is a public officer in official/administrative functions"},
            "modality":        {"needs": ["manifest_partiality", "bad_faith", "gross_negligence"], "any": True,
                                "label": "acted with manifest partiality, evident bad faith, or gross inexcusable negligence"},
            "injury_or_benefit": {"needs": ["injury_actual", "unwarranted_benefit"], "weak": ["injury_delay"], "any": True,
                                "label": "caused undue injury (ACTUAL damage) OR gave an unwarranted benefit/advantage"},
        },
        "prescription": "20 years from commission (R.A. 3019 Sec. 11 as amended by R.A. 10910, 2016; "
                        "15 years for acts before 16-Jul-2016) — NEEDS-COUNSEL-VERIFICATION",
    },
    "ra3019_3f": {
        "statute": "R.A. 3019, Sec. 3(f)",
        "gist": "neglecting/refusing, after due demand, to act on a matter within a reasonable time "
                "without sufficient justification, to obtain benefit or to discriminate",
        "forum_default": "OMBUDSMAN",
        "elements": {
            "public_officer":  {"needs": ["official_capacity"], "label": "respondent is a public officer"},
            "due_demand":      {"needs": ["due_demand", "records_refusal"], "any": True, "label": "a matter pending after due demand"},
            "unjustified_refusal": {"needs": ["records_refusal", "false_denial"], "weak": ["delay_past_charter", "injury_delay"], "any": True,
                                "label": "refused/neglected to act without sufficient justification"},
            "purpose":         {"needs": ["discrimination", "unwarranted_benefit"], "any": True,
                                "label": "for the purpose of favoring/discriminating (or obtaining benefit)"},
        },
        "prescription": "20 years (same clock as Sec. 3) — NEEDS-COUNSEL-VERIFICATION",
    },
    "ra6713_5a": {
        "statute": "R.A. 6713, Sec. 5(a)",
        "gist": "failure to act promptly on letters/requests within 15 working days",
        "forum_default": "CSC",  # administrative; also cognizable by the Ombudsman
        "elements": {
            "public_officer":  {"needs": ["official_capacity"], "label": "respondent is a public officer"},
            "communication":   {"needs": ["due_demand", "records_refusal"], "any": True, "label": "a letter/request was received"},
            "no_prompt_action": {"needs": ["delay_past_charter", "records_refusal"], "any": True,
                                "label": "not acted upon within 15 working days / the Charter clock"},
        },
        "prescription": "administrative — no fixed criminal clock; act while the omission is live "
                        "— NEEDS-COUNSEL-VERIFICATION",
    },
    "rpc_171": {
        "statute": "Revised Penal Code, Art. 171 / 174 (falsification by a public officer)",
        "gist": "making an untruthful statement in a narration of facts in an official document",
        "forum_default": "OMBUDSMAN",
        "elements": {
            "public_officer":  {"needs": ["official_capacity"], "label": "respondent is a public officer"},
            "official_document": {"needs": ["official_document"], "label": "an official document / official communication"},
            "untruthful_narration": {"needs": ["false_denial"], "label": "an untruthful narration of facts (e.g. a provable false denial of receipt)"},
        },
        "prescription": "15 years (afflictive) — NEEDS-COUNSEL-VERIFICATION",
    },
    "grave_misconduct": {
        "statute": "Grave Misconduct (administrative) — R.A. 6713 Sec. 4(a); Uniform Rules on "
                   "Administrative Cases; cognizable by the Ombudsman/CSC",
        "gist": "a flagrant, corrupt, or clear-intent breach of duty — incl. sitting in judgment of "
                "the complaint against one's own office (irreconcilable conflict of interest)",
        "forum_default": "OMBUDSMAN",
        "elements": {
            "public_officer":  {"needs": ["official_capacity"], "label": "respondent is a public officer"},
            "flagrant_breach": {"needs": ["conflict_of_interest", "additional_requirement", "false_denial"], "weak": ["records_refusal"], "any": True,
                                "label": "a flagrant/corrupt breach (conflict of interest or unlawful requirement — a bare refusal is only 'thin')"},
        },
        "prescription": "administrative — grave misconduct does not prescribe (settled) "
                        "— NEEDS-COUNSEL-VERIFICATION",
    },
}

# The signal LEXICON — deterministic keyword patterns over the verified matter_facts. Each match
# yields an evidence HANDLE (the fact id + its source doc), never an assertion. Extend, don't fork.
SIGNAL_PATTERNS = {
    "official_capacity":   r"\b(mayor|assessor|treasurer|engineer|penro|cenro|register of deeds|registrar|"
                           r"sanggunian|councilor|kagawad|provincial|municipal|officer|official|department head)\b",
    "records_refusal":     r"\b(refus\w+|denied release|did not release|withheld|would not (?:give|release|provide)|"
                           r"no (?:copy|record|response|disposition))\b",
    "false_denial":        r"\b(not received|never received|no record of receipt|denies receiving|claims? .*not received)\b",
    "delay_past_charter":  r"\b(delay\w*|beyond .*(?:days|charter)|failed to (?:act|respond)|unacted|no action for)\b",
    "additional_requirement": r"\b(special power of attorney|SPA from all heirs|additional requirement|"
                           r"proof of legal personality|not in the (?:citizen'?s )?charter)\b",
    "conflict_of_interest": r"\b(did not inhibit|sat (?:in judgment|on the)|own office|conflict of interest|"
                           r"CART|adjudicat\w+ .*own)\b",
    "public_spend":        r"\b(public funds?|₱[\d,]+|appropriat\w+|disbursed|spent .*(?:funds|budget)|"
                           r"P[\d,]{4,}|expenditure|contract)\b",
    "knowledge_admission": r"\b(admit\w+|acknowledg\w+|aware|knew|admission|minutes .*present)\b",
    # Sec. 3(e) undue injury is TIERED for discernment (Llorente v. Sandiganbayan wants ACTUAL,
    # quantified damage). injury_actual = money out of pocket / a receipt for an unrendered service
    # (satisfies the element); injury_delay = mere delay/deprivation/obstruction (the FLOOR → 'thin').
    "injury_actual":       r"\b(official receipt|OR No\.?\s*\d|research fee|paid[^.]{0,30}(?:fee|₱|PHP|under protest)|"
                           r"remittance|out.of.pocket|₱[\d,]{2,}|PHP[\s]*[\d,]{2,})\b",
    "injury_delay":        r"\b(injur\w+|damage|deprived|deprivation|prevented|prejudic\w+|loss to the heirs?|"
                           r"undue delay|obstruct\w+|failure to render service|"
                           r"over (?:eight|nine|ten|eleven|twelve|\d+) months?)\b",
    "unwarranted_benefit": r"\b(unwarranted (?:benefit|advantage)|favor\w+|preference|benefit to)\b",
    "due_demand":          r"\b(demand\w*|request\w*|follow-?up|letter of|written request)\b",
    "official_document":   r"\b(letter|memorandum|resolution|order|certification|joint response|"
                           r"official (?:communication|document)|minutes)\b",
    "discrimination":      r"\b(discriminat\w+|singled out|treated differently)\b",
    "bad_faith":           r"\b(bad faith|deliberate\w*|willful\w*|intentional\w*)\b",
    "manifest_partiality": r"\b(partial\w+|biased|one-sided|favored|CART|sat .*own office)\b",
    "gross_negligence":    r"\b(gross\w* neglig\w+|inexcusable|reckless\w*|patent\w* disregard)\b",
}

# ─────────────────────────────────────────────────────────────────────────────
# SEED_ROSTER — the operator-CURATED overlay: high-value known identities (esp. the flagship Mayor,
# whose entity carries no title in its name) that corpus discovery can't reliably name/classify.
# The LIVE roster is SEED_ROSTER ∪ discover_officers(corpus) — see build_roster(). So the engine
# LEARNS its targets from the whole entities graph and grows as the corpus grows, instead of only
# hunting a hardcoded list. Generic office seeds are dropped once a NAMED officer is discovered.
# ─────────────────────────────────────────────────────────────────────────────
# Geography / role-generic tokens that are too common to identify a specific officer — a fact that
# merely mentions "Mercedes" the town must NOT match "Mayor of Mercedes". Matching keys on the
# DISTINCTIVE tokens (role title + surname) below, never on these.
MATCH_STOPWORDS = {"mercedes", "municipal", "office", "camarines", "norte", "bayan",
                   "denr", "provincial", "the", "and", "of"}

SEED_ROSTER = [
    # official, office, capacity, distinctive match tokens, note (provenance of the seed)
    ("Mayor Alexander Pajarillo",    "Office of the Mayor, Mercedes",             "elective",
     ["Mayor", "Pajarillo"],
     "playbook ombudsman_1891 + fact 5243 — CART Chairperson over complaints vs his own office; fact 5229 — imposed the All-Heirs-SPA requirement"),
    ("Sangguniang Bayan (Mercedes)", "Sangguniang Bayan, Mercedes",               "elective",
     ["Sangguniang", "Kagawad", "Councilor"],
     "playbook ombudsman_1891 — members present/participating at the CART, did not inhibit"),
    ("Municipal Assessor",           "Office of the Municipal Assessor, Mercedes", "appointive",
     ["Assessor"],
     "records-refusal track (27-May-2025 request) — CSC parallel track"),
    ("Municipal Treasurer",          "Office of the Municipal Treasurer, Mercedes","appointive",
     ["Treasurer"],
     "records-refusal track (28-May-2025 request) — CSC parallel track"),
    ("Municipal Engineer",           "Office of the Municipal Engineer, Mercedes", "appointive",
     ["Municipal Engineer", "Engr"],   # NB: fact 6469 names 'Engr. Balane' as Mun. Engineer — do NOT conflate with Gloria Balane (CV-26360)
     "cross-department refusal — CSC parallel track"),
    ("PENRO Fortuno",                "PENRO, Camarines Norte (DENR)",              "career",
     ["Fortuno", "PENRO"],
     "ARTA-1319 respondent; Joint Response 18-Feb-2026 — false-denial angle"),
    ("PENRO Remoto",                 "PENRO, Camarines Norte (DENR)",              "career",
     ["Remoto"],
     "ARTA-1319 co-respondent"),
]

# ── Corpus-driven officer discovery (the "learn across the corpus" layer) ─────
# Title words stripped to isolate the distinctive surname; office phrase kept if nothing survives.
_TITLE_WORDS = {"hon", "atty", "engineer", "engr", "mayor", "vice", "vicemayor", "vice-mayor",
                "assistant", "asst", "senior", "commissioner", "director", "undersecretary",
                "provincial", "municipal", "city", "prosecutor", "councilor", "kagawad", "sheriff",
                "clerk", "registrar", "register", "deeds", "administrator", "governor", "penro",
                "cenro", "ms", "mr", "mrs", "jr", "sr", "of", "the", "office"}
_ELECTIVE_KW = ("mayor", "vice-mayor", "vice mayor", "vicemayor", "governor", "councilor",
                "kagawad", "sanggunian", "congressman", "senator", "barangay captain", "punong")
_CAREER_KW = ("assessor", "treasurer", "engineer", "register of deeds", "registrar", "penro",
              "cenro", "prosecutor", "commissioner", "director", "administrator", "sheriff",
              "clerk", "undersecretary", "provincial assessor", "adjudicator")
# our own side / non-targets — never generate an Ombudsman lead against these
_OURSIDE_RE = (r"heirs of mary|MWK-001|attorney-in-fact|\bheir\b|plaintiff|decedent|estate principal|"
               r"barandon|botor|zschoche|keesey|don qi|private")


def _classify_capacity(blob):
    """Capacity from the officer's OWN title = the EARLIEST-occurring office keyword. A co-mentioned
    official ('...Treasurer, with Mayor Pajarillo') must not flip the classification."""
    b = blob.lower()
    best_pos, best_cap = len(b) + 1, "unknown"
    for kw in _ELECTIVE_KW:
        i = b.find(kw)
        if 0 <= i < best_pos:
            best_pos, best_cap = i, "elective"
    for kw in _CAREER_KW:
        i = b.find(kw)
        if 0 <= i < best_pos:
            best_pos, best_cap = i, "appointive"
    return best_cap


def _match_tokens_from(canonical_name, aliases):
    """Distinctive tokens: surnames from the canonical name (>=3), plus alias tokens (>=4, so noisy
    OCR fragments like 'Mac'/'Ale' don't over-match). Office-only entities match on the phrase."""
    toks = []
    for t in re.split(r"[^A-Za-z]+", canonical_name):
        if len(t) >= 3 and t.lower() not in _TITLE_WORDS and t.lower() not in MATCH_STOPWORDS:
            toks.append(t)
    for a in aliases or []:
        for t in re.split(r"[^A-Za-z]+", a or ""):
            if len(t) >= 4 and t.lower() not in _TITLE_WORDS and t.lower() not in MATCH_STOPWORDS and t not in toks:
                toks.append(t)
    if not toks:  # office-only entity (e.g. "Provincial Assessor") — match the phrase itself
        toks = [canonical_name.strip()]
    return toks[:6]


def discover_officers(cur):
    """LEARN the target set from the entities graph: person-entities whose name/role/affiliation
    signal a PUBLIC OFFICE, excluding our own side + private parties. Grows as the corpus grows."""
    if not _table_exists(cur, "entities"):
        return []
    cur.execute("""
        SELECT id, canonical_name, COALESCE(aliases,'{}'), COALESCE(role,''),
               COALESCE(affiliation,''), COALESCE(mentions_count,0)
        FROM entities
        WHERE type ILIKE '%%person%%' AND canonical_name IS NOT NULL
          AND ( canonical_name ~* '(^| )(mayor|vice.?mayor|assessor|treasurer|engineer|penro|cenro|register of deeds|registrar|commissioner|director|administrator|sheriff|prosecutor|governor|councilor|kagawad|undersecretary|hon\\.)'
             OR role ~* '(mayor|assessor|treasurer|register|registrar|penro|cenro|engineer|commissioner|director|administrator|sheriff|clerk|prosecutor|officer|official|undersecretary|adjudicator|governor|councilor|kagawad|sanggunian)'
             OR affiliation ~* '(municipal|provincial|LGU|DENR|register of deeds|civil service|anti-red tape|ARTA|RTC|MTC|office of|government|city of)' )
          AND (COALESCE(role,'') || ' ' || COALESCE(affiliation,'') || ' ' || canonical_name) !~* %s
        ORDER BY mentions_count DESC NULLS LAST
    """, (_OURSIDE_RE,))
    out = []
    for eid, name, aliases, role, aff, mc in cur.fetchall():
        blob = f"{name} {role} {aff}"
        cap = _classify_capacity(blob)
        office = (aff or role or "public office").strip()
        toks = _match_tokens_from(name, aliases)
        note = f"corpus-discovered [entity {eid}, {mc} mentions]" + (f"; role: {role}" if role else "")
        out.append((name, office[:70], cap, toks, note, "discovered"))
    return out


def build_roster(cur):
    """LIVE roster = corpus-discovered officers ∪ curated seed overlay (deduped). Generic office
    seeds are dropped once a NAMED officer covers that office."""
    discovered = discover_officers(cur)
    disc_tokens = {t.lower() for _n, _o, _c, toks, _no, _s in discovered for t in toks}
    disc_offices = " ".join((n + " " + o).lower() for n, o, _c, _t, _no, _s in discovered)
    roster = [(n, o, c, t, no, "discovered") for (n, o, c, t, no, _s) in discovered]
    for name, office, cap, toks, note in SEED_ROSTER:
        # drop a generic office seed if a named officer already covers that office
        if name in ("Municipal Assessor", "Municipal Treasurer", "Municipal Engineer"):
            offword = name.split()[-1].lower()
            if offword in disc_offices:
                continue
        # skip an exact seed already present by token (avoid duplicates); else keep the seed overlay
        if any(t.lower() in disc_tokens for t in toks) and name not in (
                "Mayor Alexander Pajarillo",):  # always keep the flagship's curated provenance
            continue
        roster.append((name, office, cap, toks, note, "seed"))
    return roster


# ── DB helpers ───────────────────────────────────────────────────────────────
def _table_exists(cur, name):
    cur.execute("SELECT to_regclass(%s)", (name,))
    return cur.fetchone()[0] is not None


def _fetch_facts(cur):
    """Every matter_fact we can scan, with its source handle. Defensive about column presence."""
    if not _table_exists(cur, "matter_facts"):
        return []
    cur.execute("""
        SELECT id, matter_code,
               COALESCE(statement, '') AS statement,
               COALESCE(source_id::text, '') AS source_id,
               COALESCE(provenance_level, '') AS prov
        FROM matter_facts
    """)
    return cur.fetchall()


def _fetch_docmap(cur):
    """source_id (as text) -> document filename, for identity-bearing evidence handles."""
    if not _table_exists(cur, "documents"):
        return {}
    cur.execute("SELECT id::text, COALESCE(original_filename,'') FROM documents")
    return {r[0]: r[1] for r in cur.fetchall()}


def _fetch_fact_texts(cur, fact_ids):
    """id -> statement, for the discernment pass to READ the actual evidence."""
    if not fact_ids:
        return {}
    cur.execute("SELECT id, COALESCE(statement,'') FROM matter_facts WHERE id = ANY(%s)",
                (list(fact_ids),))
    return {r[0]: r[1] for r in cur.fetchall()}


def _ensure_table(cur):
    if _table_exists(cur, "ombudsman_candidates"):
        return
    print("[hunter] ombudsman_candidates table missing — run migrations/deploy_NN_ombudsman_hunter.sql "
          "on the VPS first (executor step). Aborting write.", file=sys.stderr)
    sys.exit(2)


# ── Discernment reasoner (local Ollama — sovereign, $0) ──────────────────────
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
VERIFY_MODEL = os.environ.get("LANDTEK_OMBUDS_MODEL", "qwen2.5:14b-instruct")


def _ollama(prompt):
    import urllib.request
    body = {"model": VERIFY_MODEL, "prompt": prompt, "stream": False,
            "format": "json", "options": {"temperature": 0.0, "num_ctx": 8192}}
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode()).get("response", "").strip()


def _fact_ids_from_handles(handles):
    ids = []
    for h in handles or []:
        m = re.search(r"fact:(\d+)", h)
        if m:
            ids.append(int(m.group(1)))
    return ids


# ── Stages ───────────────────────────────────────────────────────────────────
def _match_official(fact_stmt, match_tokens):
    """Match on DISTINCTIVE role/surname tokens only — never on geography (a fact mentioning the
    town 'Mercedes' must not attach to 'Mayor …Mercedes'). Multi-word tokens match as a phrase."""
    low = fact_stmt.lower()
    for tok in match_tokens:
        t = tok.lower()
        if t in MATCH_STOPWORDS:
            continue
        if " " in t:  # phrase token, e.g. "municipal engineer"
            if t in low:
                return True
        elif re.search(r"\b" + re.escape(t) + r"\b", low):
            return True
    return False


def _scan_signals(text):
    hits = {}
    for sig, pat in SIGNAL_PATTERNS.items():
        if re.search(pat, text, re.IGNORECASE):
            hits[sig] = True
    return hits


def cull_and_profile(facts, roster, docmap=None):
    """official -> {matters:set, incidents:[(fact_id, doc_handle, signals, matter)]}. Handles carry
    the document's IDENTITY (filename) so downstream never mislabels a pleading as a receipt.
    `roster` is the LIVE (corpus-discovered ∪ seed) officer list from build_roster()."""
    docmap = docmap or {}
    profiles = {}
    tokens_by_official = {}
    for official, office, capacity, match_tokens, note, source in roster:
        profiles[official] = {"office": office, "capacity": capacity, "seed_note": note,
                              "source": source, "matters": set(), "incidents": []}
        tokens_by_official[official] = match_tokens
    for fid, matter, stmt, src, prov in facts:
        if prov and prov not in ("verified", "inferred_strong"):
            continue  # scan only grounded facts, never weak/draft
        for official in list(profiles):
            if _match_official(stmt, tokens_by_official[official]):
                sigs = _scan_signals(stmt)
                if not sigs:
                    continue
                if src:
                    dname = docmap.get(str(src), "")
                    handle = f"fact:{fid}|doc:{src}" + (f" ({dname[:48]})" if dname else "")
                else:
                    handle = f"fact:{fid}"
                profiles[official]["matters"].add(matter)
                profiles[official]["incidents"].append((fid, handle, sigs, matter))
    return profiles


def _element_gate(vtemplate, present_signals):
    """Return (elements_report, strength). A 'weak' signal only yields 'thin' — it never proves an
    element (evidence-quality tiering, so keyword presence ≠ element proof)."""
    report = {}
    proven = 0
    for ekey, espec in vtemplate["elements"].items():
        needs = espec["needs"]
        weak = espec.get("weak", [])
        any_mode = espec.get("any", False)
        got = [s for s in needs if s in present_signals]
        got_weak = [s for s in weak if s in present_signals]
        if (any_mode and got) or (not any_mode and len(got) == len(needs)):
            state = "have"
            proven += 1
        elif got or got_weak:
            state = "thin"
        else:
            state = "missing"
        report[ekey] = {"state": state, "label": espec["label"],
                        "handle": sorted({present_signals[s] for s in (got + got_weak) if s in present_signals})}
    strength = round(proven / max(1, len(vtemplate["elements"])), 3)
    return report, strength


def _route_forum(capacity, vtemplate):
    if vtemplate["forum_default"] == "CSC":
        return "CSC"
    # criminal graft: Ombudsman investigates all; Sandiganbayan tries SG>=27 (SG unknown here)
    if capacity == "elective":
        return "OMBUDSMAN"
    if capacity in ("appointive", "career"):
        # still Ombudsman-cognizable criminally; admin may fall to CSC — flag both
        return "OMBUDSMAN"
    return vtemplate["forum_default"]


def build_candidates(profiles):
    """Cross each official's aggregated signals against every violation template -> candidate rows."""
    cands = []
    for official, prof in profiles.items():
        if not prof["incidents"]:
            continue
        # aggregate signal -> best handle (first seen) across all incidents
        agg = {}
        for fid, handle, sigs, matter in prof["incidents"]:
            for s in sigs:
                agg.setdefault(s, handle)
        for vcode, vtmpl in VIOLATIONS.items():
            report, strength = _element_gate(vtmpl, agg)
            if strength == 0:
                continue  # no element even thinly supported — not a lead
            forum = _route_forum(prof["capacity"], vtmpl)
            all_have = all(e["state"] == "have" for e in report.values())
            identified = prof["capacity"] in ("elective", "appointive", "career")
            n_facts = len({fid for fid, _h, _s, _m in prof["incidents"]})
            # DISCERNMENT RULE: the deterministic keyword scan caps at 'ripe' — keyword presence
            # alone can NOT declare a case ready. Only the evidence-reading pass (--verify), which
            # actually reads each cited fact, promotes 'ripe' -> 'held_for_filing'. A single fact is
            # never 'ripe' (needs >=2 distinct grounding facts).
            if all_have and identified and n_facts >= 2:
                status = "ripe"
            elif (all_have or strength >= 0.5) and identified:
                status = "building"
            else:
                status = "seed"
            gaps = [f"pin element '{report[e]['label']}'" for e in report if report[e]["state"] != "have"]
            if status == "ripe":
                gaps.append("run --verify: an evidence-read must confirm each element before this is filing-ready")
            if not identified:
                gaps.append("confirm respondent identity + term/appointment of record (elective vs appointive)")
            leverage = 5 if prof["capacity"] == "elective" else 4
            forum_fit = 1.0 if forum == "OMBUDSMAN" else 0.7
            score = round(strength * leverage * forum_fit, 3)
            signals_handles = {s: [h] for s, h in agg.items()}
            rationale = (f"{status.upper()} (keyword-scan, UNVERIFIED): {int(strength*100)}% of "
                         f"{vtmpl['statute']} elements keyword-supported across {n_facts} fact(s), "
                         f"{len(prof['matters'])} matter(s); forum {forum}. Needs --verify.")
            cands.append({
                "official": official, "office": prof["office"], "capacity": prof["capacity"],
                "matters": sorted(prof["matters"]), "violation_code": vcode,
                "statute": vtmpl["statute"], "forum": forum, "elements": report,
                "signals": signals_handles, "prescription": vtmpl["prescription"],
                "status": status, "strength": strength, "leverage": leverage, "score": score,
                "gaps": gaps, "rationale": rationale,
            })
    cands.sort(key=lambda c: c["score"], reverse=True)
    return cands


def upsert(cur, cands):
    _ensure_table(cur)
    for c in cands:
        cur.execute("""
            INSERT INTO ombudsman_candidates
              (official, office, capacity, matters, violation_code, statute, forum, elements, signals,
               prescription, status, strength, leverage, score, gaps, rationale, provenance, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'inferred_strong', now())
            ON CONFLICT (official, violation_code) DO UPDATE SET
              office=EXCLUDED.office, capacity=EXCLUDED.capacity, matters=EXCLUDED.matters,
              statute=EXCLUDED.statute, forum=EXCLUDED.forum, elements=EXCLUDED.elements,
              signals=EXCLUDED.signals, prescription=EXCLUDED.prescription, status=EXCLUDED.status,
              strength=EXCLUDED.strength, leverage=EXCLUDED.leverage, score=EXCLUDED.score,
              gaps=EXCLUDED.gaps, rationale=EXCLUDED.rationale, updated_at=now()
        """, (c["official"], c["office"], c["capacity"], c["matters"], c["violation_code"],
              c["statute"], c["forum"], json.dumps(c["elements"]), json.dumps(c["signals"]),
              c["prescription"], c["status"], c["strength"], c["leverage"], c["score"],
              json.dumps(c["gaps"]), c["rationale"]))


# ── Commands ─────────────────────────────────────────────────────────────────
def cmd_scan():
    with _conn() as conn, conn.cursor() as cur:
        facts = _fetch_facts(cur)
        if not facts:
            print("[hunter] no matter_facts found — nothing to scan (is PG_DSN pointed at the live DB?)")
            return
        roster = build_roster(cur)
        n_disc = sum(1 for r in roster if r[5] == "discovered")
        docmap = _fetch_docmap(cur)
        profiles = cull_and_profile(facts, roster, docmap)
        cands = build_candidates(profiles)
        upsert(cur, cands)
        ripe = sum(1 for c in cands if c["status"] == "ripe")
        print(f"[hunter] learned {len(roster)} officers ({n_disc} corpus-discovered + "
              f"{len(roster)-n_disc} seed) from the entities graph; scanned {len(facts)} facts -> "
              f"{len(cands)} candidate lead(s) across "
              f"{sum(1 for p in profiles.values() if p['incidents'])} officer(s) with signal-bearing facts; "
              f"{ripe} at 'ripe' (keyword-scan, UNVERIFIED). Run --verify; filing stays human-gated.")


def cmd_officers():
    """Show the LIVE roster the engine learned from the corpus (discovered vs curated seed)."""
    with _conn() as conn, conn.cursor() as cur:
        roster = build_roster(cur)
        disc = [r for r in roster if r[5] == "discovered"]
        seed = [r for r in roster if r[5] == "seed"]
        print(f"OMBUDSMAN HUNTER — learned officer roster: {len(roster)} "
              f"({len(disc)} corpus-discovered + {len(seed)} curated seed)\n")
        print("CORPUS-DISCOVERED (from the entities graph — grows with the corpus):")
        for name, office, cap, toks, note, _s in disc:
            print(f"  {name[:34]:<34} [{cap:<10}] {office[:38]}\n      match {toks} — {note}")
        print("\nCURATED SEED (overlay for identities discovery can't name/classify):")
        for name, office, cap, toks, note, _s in seed:
            print(f"  {name[:34]:<34} [{cap:<10}] {office[:38]}  match {toks}")


def cmd_verify(target):
    """DISCERNMENT PASS — actually READ each cited fact and judge whether it establishes the element
    (not just contains a keyword). Downgrades keyword-coincidence matches; only an evidence-read
    confirmation promotes a candidate to 'held_for_filing'. Local Ollama, $0.  target: id | 'ripe'."""
    with _conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        if not _table_exists(cur, "ombudsman_candidates"):
            print("No candidates. Run --scan first.")
            return
        if str(target).isdigit():
            cur.execute("SELECT * FROM ombudsman_candidates WHERE id=%s", (int(target),))
        else:
            cur.execute("SELECT * FROM ombudsman_candidates WHERE status='ripe' ORDER BY score DESC")
        rows = cur.fetchall()
        if not rows:
            print("Nothing to verify (no matching 'ripe' candidate). Run --board to see statuses.")
            return
        for r in rows:
            elements = dict(r["elements"])
            all_fids = {f for ev in elements.values() for f in _fact_ids_from_handles(ev.get("handle"))}
            texts = _fetch_fact_texts(cur, all_fids)
            print(f"\n[verify] #{r['id']} {r['official']} — {r['statute']}")
            proven = 0
            notes = []
            for ekey, ev in elements.items():
                if ev["state"] == "missing":
                    continue
                fids = _fact_ids_from_handles(ev.get("handle"))
                excerpts = "\n".join(f"- (fact {i}) {texts.get(i,'')[:300]}" for i in fids) or "(no excerpt)"
                prompt = (
                    "You are a strict Philippine anti-graft evidence auditor. Judge ONLY whether the "
                    "evidence below ESTABLISHES the specific element as to the named respondent. Be "
                    "skeptical: a fact that merely mentions the office/town, or is about someone else, "
                    "does NOT establish it.\n\n"
                    f"STATUTE: {r['statute']}\n"
                    f"ELEMENT TO PROVE: {ev['label']}\n"
                    f"RESPONDENT: {r['official']} ({r['office']})\n"
                    f"EVIDENCE:\n{excerpts}\n\n"
                    'Reply STRICT JSON: {"verdict":"have|thin|no","why":"<=15 words"}. '
                    '"have"=evidence directly establishes it; "thin"=related but incomplete; "no"=does not.')
                try:
                    v = json.loads(_ollama(prompt))
                    verdict = v.get("verdict", "thin").lower()
                    why = str(v.get("why", ""))[:90]
                except Exception as e:  # noqa
                    verdict, why = "thin", f"verifier-error: {e}"
                if verdict not in ("have", "thin", "no"):
                    verdict = "thin"
                new_state = {"have": "have", "thin": "thin", "no": "missing"}[verdict]
                ev["state"] = new_state
                ev["verify"] = {"verdict": verdict, "why": why}
                if new_state == "have":
                    proven += 1
                notes.append(f"{ekey}:{verdict} ({why})")
                print(f"    [{new_state:<7}] {ekey} — {why}")
            total = len(elements)
            strength = round(proven / max(1, total), 3)
            all_have = all(ev["state"] == "have" for ev in elements.values())
            identified = r["capacity"] in ("elective", "appointive", "career")
            status = "held_for_filing" if (all_have and identified) else ("building" if strength >= 0.5 else "seed")
            forum_fit = 1.0 if r["forum"] == "OMBUDSMAN" else 0.7
            score = round(strength * (r["leverage"] or 3) * forum_fit, 3)
            gaps = [f"pin element '{ev['label']}'" for ev in elements.values() if ev["state"] != "have"]
            rationale = (f"{status.upper()} (VERIFIED by evidence-read): {int(strength*100)}% of "
                         f"{r['statute']} elements established. " + " · ".join(notes))
            cur.execute("""UPDATE ombudsman_candidates
                           SET elements=%s, status=%s, strength=%s, score=%s, gaps=%s, rationale=%s,
                               provenance='operator', updated_at=now() WHERE id=%s""",
                        (json.dumps(elements), status, strength, score, json.dumps(gaps), rationale, r["id"]))
            print(f"  => {status.upper()}  (strength {int(strength*100)}%, score {score})")
        print("\n[verify] done. Filing remains human-gated — 'held_for_filing' is the ceiling.")


def cmd_board():
    with _conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        if not _table_exists(cur, "ombudsman_candidates"):
            print("No candidates yet. Run --scan (after applying the migration on the VPS).")
            return
        cur.execute("SELECT * FROM ombudsman_candidates ORDER BY score DESC")
        rows = cur.fetchall()
        if not rows:
            print("No candidates yet. Run --scan.")
            return
        print("OMBUDSMAN HUNTER — ranked leads (filing is held; these are LEADS, not verified facts)")
        print("  RIPE = keyword-scan only, UNVERIFIED.  READY = evidence-read confirmed (--verify).\n")
        for r in rows:
            vtag = "✓verified" if r["provenance"] == "operator" else "unverified"
            flag = {"held_for_filing": "READY (hold)", "ripe": "RIPE", "building": "building",
                    "seed": "seed"}.get(r["status"], r["status"])
            print(f"  #{r['id']:>3}  [{flag:<12}] {vtag:<10} score {r['score']:<5}  {r['official']} — {r['statute']}")
            print(f"        {r['rationale']}")
        n_ripe = sum(1 for r in rows if r["status"] == "ripe")
        print(f"\n{n_ripe} 'ripe' lead(s) await evidence-read. Next: --verify ripe (reads the facts, "
              "promotes only what survives); --candidate N; --playbook N (draft; still not filed).")


def cmd_candidate(cid):
    with _conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM ombudsman_candidates WHERE id=%s", (cid,))
        r = cur.fetchone()
        if not r:
            print(f"No candidate #{cid}.")
            return
        print(f"OMBUDSMAN HUNTER — candidate #{r['id']}  [{r['status']}]  score {r['score']}\n")
        print(f"  Respondent : {r['official']} ({r['capacity']}) — {r['office']}")
        print(f"  Theory     : {r['statute']}")
        print(f"  Forum      : {r['forum']}")
        print(f"  Matters    : {', '.join(r['matters'])}")
        print(f"  Prescript. : {r['prescription']}")
        vtag = "VERIFIED by evidence-read" if r["provenance"] == "operator" else "keyword-scan only (run --verify)"
        print(f"  Grounding  : {vtag}")
        print("\n  Element gate (each 'have' points to an evidence handle):")
        for ek, ev in r["elements"].items():
            print(f"    [{ev['state']:<7}] {ev['label']}")
            if ev.get("verify"):
                print(f"              verdict: {ev['verify'].get('verdict')} — {ev['verify'].get('why')}")
            if ev.get("handle"):
                print(f"              handles: {', '.join(ev['handle'])}")
        if r["gaps"]:
            print("\n  Gaps to close before this can graduate to a filing:")
            for g in r["gaps"]:
                print(f"    - {g}")
        print("\n  NOTE: this is an inference-grade LEAD. Filing against a named public officer is a "
              "held decision — nothing here has been filed.")


def cmd_playbook(cid):
    """Emit a case_synthesizer playbook JSON for a ripe candidate (drafting only — not a filing)."""
    with _conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM ombudsman_candidates WHERE id=%s", (cid,))
        r = cur.fetchone()
        if not r:
            print(f"No candidate #{cid}.")
            return
        if r["status"] not in ("ripe", "held_for_filing"):
            print(f"Candidate #{cid} is '{r['status']}', not ripe. Close its gaps first (--candidate {cid}).")
            return
        slug = re.sub(r"[^a-z0-9]+", "_", r["official"].lower()).strip("_")
        vtmpl = VIOLATIONS[r["violation_code"]]
        pb = {
            "title": f"Evidence Support Dossier — Office of the Ombudsman",
            "subtitle": f"{r['statute']} — {r['official']} ({r['office']})",
            "matter": "MWK",
            "purpose_note": ("Prepared by LandTek for counsel. NOT a pleading and NOT a filing — the "
                             "grounded evidentiary support for a working Complaint-Affidavit. Every "
                             "charge is tied to the record; gaps are marked. Filing is counsel's decision."),
            "dispositive_frame": {
                "heading": f"{vtmpl['gist']}",
                "theory": r["rationale"],
                "rag_query": f"{r['official']} {vtmpl['gist']} {' '.join(r['matters'])}",
                "exhibits": [],
                "statutes": [{"cite": r["statute"],
                              "citation_ilike": re.search(r"\d{3,5}", r["statute"]).group(0)
                              if re.search(r"\d{3,5}", r["statute"]) else r["statute"],
                              "kw_ilike": vtmpl["gist"].split()[0]}],
            },
            "elements": [
                {"heading": ev["label"], "theory": f"Supported at level '{ev['state']}'.",
                 "statutes": [{"cite": r["statute"],
                               "citation_ilike": re.search(r"\d{3,5}", r["statute"]).group(0)
                               if re.search(r"\d{3,5}", r["statute"]) else r["statute"],
                               "kw_ilike": vtmpl["gist"].split()[0]}],
                 "rag_query": f"{r['official']} {ev['label']}"}
                for ev in r["elements"].values()
            ],
            "record": {"matters": [m + "%" for m in r["matters"]] or ["MWK%"], "since": "2025-01-01"},
            "gaps": list(r["gaps"]) + [
                "Confirm the respondent's exact identity, office, and term/appointment of record.",
                f"Verify the prescription posture: {r['prescription']}",
                "Confirm elective (Ombudsman) vs appointive/career (CSC parallel track) routing.",
            ],
        }
        here = os.path.dirname(os.path.abspath(__file__))
        out = os.path.join(os.path.dirname(here), "playbooks", f"ombudsman_hunter_{slug}_{r['violation_code']}.json")
        with open(out, "w") as f:
            json.dump(pb, f, indent=2)
        print(f"[hunter] wrote {out}")
        print(f"        render it (drafting only, no filing) with:")
        print(f"        python3 scripts/case_synthesizer.py --playbook {os.path.relpath(out)} "
              f"--out ombudsman_output/{slug}_{r['violation_code']}.md [--frontier]")


def cmd_law_check():
    """Is the Ombudsman law library embedded? Reuses legal_authority, never re-implements it."""
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    try:
        import legal_authority as la
    except Exception as e:  # noqa
        print(f"[hunter] could not import legal_authority ({e}); check RA coverage manually.")
        return
    for cite in ("R.A. 3019 undue injury manifest partiality",
                 "R.A. 6713 act promptly fifteen working days",
                 "R.A. 6770 Ombudsman jurisdiction public officer"):
        try:
            hits = la.retrieve_chunks("OMBUDSMAN", cite, 1)
            ok = "EMBEDDED" if hits else "MISSING — ingest via legal_authority.py --ingest --forum OMBUDSMAN"
            print(f"  [{ok}] {cite}")
        except Exception as e:  # noqa
            print(f"  [error] {cite} — {e}")


def cmd_doctrine():
    print("OMBUDSMAN HUNTER — doctrine (templates + roster), dry / no DB\n")
    print("VIOLATION TEMPLATES:")
    for vc, v in VIOLATIONS.items():
        print(f"  {vc:<18} {v['statute']}  [{v['forum_default']}]")
        print(f"      {v['gist']}")
        print(f"      elements: {', '.join(v['elements'].keys())}")
        print(f"      prescription: {v['prescription']}")
    print("\nSEED ROSTER OVERLAY (the LIVE roster also LEARNS officers from the entities graph "
          "— run --officers):")
    for o, off, cap, toks, note in SEED_ROSTER:
        print(f"  {o:<28} [{cap}] {off}\n      match: {toks}\n      seed: {note}")


def main():
    ap = argparse.ArgumentParser(description="OMBUDSMAN HUNTER — offensive graft-case lead engine ($0; filing is human-gated).")
    ap.add_argument("--scan", action="store_true", help="run the pipeline and write candidates")
    ap.add_argument("--board", action="store_true", help="phone-friendly ranked leads")
    ap.add_argument("--candidate", type=int, metavar="ID", help="one lead: elements + evidence handles + gaps")
    ap.add_argument("--playbook", type=int, metavar="ID", help="emit a case_synthesizer playbook for a ripe lead")
    ap.add_argument("--verify", metavar="ID|ripe", help="DISCERNMENT PASS: read each cited fact + judge grounding "
                    "(local LLM $0); promotes only what survives to held_for_filing. 'ripe' verifies all ripe leads")
    ap.add_argument("--officers", action="store_true", help="show the LIVE roster the engine learned from the corpus (discovered + seed)")
    ap.add_argument("--law-check", action="store_true", help="is the RA 3019/6713/6770 law library embedded?")
    ap.add_argument("--doctrine", action="store_true", help="print templates + seed overlay (dry, no DB)")
    a = ap.parse_args()

    if a.doctrine:
        cmd_doctrine()
    elif a.officers:
        cmd_officers()
    elif a.scan:
        cmd_scan()
    elif a.board:
        cmd_board()
    elif a.candidate is not None:
        cmd_candidate(a.candidate)
    elif a.playbook is not None:
        cmd_playbook(a.playbook)
    elif a.verify is not None:
        cmd_verify(a.verify)
    elif a.law_check:
        cmd_law_check()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
