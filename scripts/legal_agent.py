#!/usr/bin/env python3
"""legal_agent.py — the discerning final-output reasoner: a multi-step legal harness. $0 (local 14B).

Single-shot prompting isn't discerning. This reasons in passes, the way a lawyer does — and each pass
is forced to do ONE thing well, on the strongest local model (qwen2.5:14b):

  1. ELEMENT-MAP  — identify the issues/claims + their legal ELEMENTS; map which VERIFIED facts support
                    each element; mark every element SUPPORTED (fact ids) or UNSUPPORTED (gap).
  2. DRAFT        — write Analysis & Recommendations from the map: only supported elements as
                    established, unsupported as gaps; governing law cited by exact section; matter
                    separation enforced (an administrative matter never "decides" a judicial one).
  3. SELF-CRITIQUE+REVISE — adversarially check the draft (citations match the provided law incl. the
                    correct SUB-provision; separation respected; nothing invented; specific) and output
                    the corrected final.

Output stays DERIVED REASONING (counsel-vetted) over the deterministic verified ground. analyze(mc)
returns {"element_map":…, "analysis":…} for case_memo; CLI prints both.

  python3 scripts/legal_agent.py MWK-ARTA-1891
"""
import datetime
import json
import os
import re
import sys
import urllib.request

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from legal_authority import retrieve_chunks
from matter_readiness import assess as _rd_assess, verdict as _rd_verdict

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://100.117.118.47:11434")
MODEL = os.environ.get("LEGAL_AGENT_MODEL", "qwen2.5:14b-instruct")
JUDICIAL = {"MWK-CV26360", "MWK-CV6839", "MWK-PARALLEL-CV6922", "MWK-PARALLEL-CRIM9221", "PAR-CV13-131220"}

# Exact output contract — Ollama structured outputs constrain the 14B to these keys (no key drift).
_SCHEMA = {
    "type": "object",
    "properties": {
        "priority": {"type": "string"},
        "summary": {"type": "string"},
        "objective": {"type": "string"},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "actions": {"type": "array", "items": {
            "type": "object",
            "properties": {"owner": {"type": "string"}, "deadline": {"type": "string"}, "draft": {"type": "string"},
                           "condition": {"type": "string"}},
            "required": ["owner", "deadline", "draft", "condition"],
        }},
    },
    "required": ["priority", "summary", "objective", "gaps", "evidence", "actions"],
}


def _llm(prompt, temp=0.2, fmt=None):
    body = {"model": MODEL, "stream": False, "options": {"temperature": temp}, "prompt": prompt}
    if fmt:
        body["format"] = fmt
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read()).get("response", "").strip()


def _coerce(s):
    """Parse a JSON object out of the model response (tolerant of stray text)."""
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s or "", re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
        return None


def _forums(ftext):
    fl = (ftext or "").lower(); out = []
    for k, code in [("arta", "ARTA"), ("csc", "CSC"), ("civil service", "CSC"), ("ombudsman", "OMBUDSMAN"),
                    ("dilg", "DILG"), ("agrarian", "DAR-DARAB"), ("darab", "DAR-DARAB"), ("deeds", "RD-LRA")]:
        if k in fl and code not in out:
            out.append(code)
    return out


def _gather(mc):
    c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("SELECT title, coalesce(forum,court_or_agency,''), coalesce(docket_number,'') FROM matters WHERE matter_code=%s", (mc,))
    title, forum, docket = cur.fetchone() or ("", "", "")
    cur.execute("SELECT doc_id FROM matter_relevance WHERE focal_matter=%s AND tier='OFF-PROFILE'", (mc,))
    off = {r[0] for r in cur.fetchall()}
    cur.execute("""SELECT id, statement, source_id FROM matter_facts WHERE matter_code=%s AND provenance_level='verified'
                   ORDER BY id""", (mc,))
    facts = [(i, s, src) for i, s, src in cur.fetchall() if not (src and src.isdigit() and int(src) in off)]
    factstr = "\n".join(f"[F{i}] {s} (doc:{src})" for i, s, src in facts)[:12000]
    laws = []
    for lf in _forums(forum):
        try:
            for cit, txt, vf, d in retrieve_chunks(lf, (title or "") + " " + factstr[:400], 3):
                laws.append(f"[{lf} {cit}] {txt.strip()[:260]}")
        except Exception:
            pass
    lawstr = "\n".join(laws)[:3500]
    # operator-set objective hint (what this matter is FOR)
    cur.execute("SELECT contribution, leverage, note FROM matter_objectives WHERE matter_code=%s ORDER BY updated_at DESC LIMIT 1", (mc,))
    o = cur.fetchone()
    objective_note = (f"operator-set role: {o[0]} (leverage {o[1]}/3) — {o[2]}" if o else "")
    related_ctx = _related_context(cur, mc)
    # data-layer gaps from the readiness pre-flight → lets the memo name the exact missing sources
    try:
        _ra = _rd_assess(cur, mc)
        _ready, _fixes, _adv = _rd_verdict(_ra) if _ra else (True, [], [])
        readiness_gaps = ("; ".join(_fixes + _adv)[:600] if (_fixes or _adv)
                          else "(pre-flight: data layer READY — no missing sources flagged)")
    except Exception:
        readiness_gaps = ""
    return title, forum, docket, factstr, lawstr, objective_note, related_ctx, readiness_gaps


def _split_markers(text):
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"\s*\[?(PRIORITY|SUMMARY|OBJECTIVE|GAPS|EVIDENCE|ACTIONS|RELATED|LINKAGE|STRATEGIC)\]?\s*[:\-]?\s*(.*)", line)
        if m and (line.lstrip().startswith("[") or m.group(2) == "" or len(line) < 40):
            cur = m.group(1).lower()
            out[cur] = m.group(2).strip() + "\n"
        elif cur is not None:
            out[cur] += line + "\n"
    return {k: v.strip() for k, v in out.items()}


def _party_ids(cur, mc):
    cur.execute("SELECT plaintiff_entity_ids, respondent_entity_ids FROM matters WHERE matter_code=%s", (mc,))
    row = cur.fetchone() or (None, None)
    ids = set()
    for arr in row:
        if arr:
            ids |= set(arr)
    cur.execute("SELECT entity_id FROM matter_parties WHERE matter_code=%s AND entity_id IS NOT NULL", (mc,))
    ids |= {r[0] for r in cur.fetchall()}
    return ids


def _related_context(cur, mc):
    """Evidence-grounded related matters, bucketed by coupling TYPE (shared docs in the corpus)."""
    cur.execute("""SELECT mr.doc_matter, count(*) c, upper(coalesce(m.forum,m.court_or_agency,'')||' '||coalesce(m.title,''))
                   FROM matter_relevance mr LEFT JOIN matters m ON m.matter_code=mr.doc_matter
                   WHERE mr.focal_matter=%s AND mr.doc_matter IS NOT NULL AND mr.doc_matter<>%s
                   GROUP BY 1,3 ORDER BY c DESC""", (mc, mc))
    admin, prop = [], []
    for dm, c, ctx in cur.fetchall():
        tag = f"{dm} ({c} shared docs)"
        if any(k in (dm + " " + ctx) for k in ("ARTA", "DILG", "OP-PETITION", "RED TAPE", "11032", "EXECUTIVE SEC")):
            admin.append(tag)
        else:
            prop.append(tag)
    parts = []
    if admin:
        parts.append("SAME ADMINISTRATIVE CAMPAIGN (RA 11032 / red-tape vs LGU Mercedes officials — genuinely "
                     "related, same fight): " + ", ".join(admin[:10]))
    if prop:
        parts.append("SAME ESTATE but a SEPARATE property/ownership track (context only; different defendants, "
                     "e.g. CV-26360): " + ", ".join(prop[:8]))
    body = "\n- ".join(parts) if parts else "none recorded in the corpus yet"
    return ("RELATED MATTERS (evidence-grounded via shared documents/entities in the corpus):\n- " + body +
            "\nThe complaint itself and its email attachments assert the fuller web of related matters; where "
            "those are not yet ingested, the related-matters map is INCOMPLETE — flag to obtain.")


def analyze(mc):
    title, forum, docket, factstr, lawstr, objective_note, related_ctx, readiness_gaps = _gather(mc)
    today = datetime.date.today()
    deadline = (today + datetime.timedelta(days=10)).isoformat()
    aug12 = datetime.date(2026, 8, 12)
    dtest = (aug12 - today).days
    kind = "JUDICIAL (a court case)" if mc in JUDICIAL else "ADMINISTRATIVE (agency/red-tape; NOT a court case)"
    fp = ("FIRST PRINCIPLES: the SOLE purpose of this memo is VICTORY in " + mc + " itself — forcing this "
          "forum to ACT. 'Victory' = the agency/court delivering the concrete relief this forum can give "
          "(for an administrative matter: the agency compels the LGU to comply / issues a directive or "
          "adverse finding / meaningful escalation succeeds). Evidence for parallel or related cases is a "
          "BYPRODUCT, NEVER a driver — do not let it shape the recommended actions.")
    sep = ("RELATEDNESS RULE: This matter is " + kind + ".\n" + related_ctx + "\nBe CLEAR and explicit about "
           "the genuinely related matters (especially the sibling RA 11032/ARTA complaints — the same campaign), "
           "but NEVER say this matter decides a separate judicial case (e.g. CV-26360, different defendants); "
           "for that property/ownership track the connection is context only.")

    # PASS 1 — element map (rigor: issues → elements → supported/gap)
    p1 = (f"You are a Philippine litigation analyst. Matter {mc} ({title}; forum: {forum}). Using ONLY "
          f"the VERIFIED FACTS and GOVERNING LAW below, identify each legal ISSUE/claim and its ELEMENTS. "
          f"For each element, list the supporting fact ids [F#], then mark it SUPPORTED or UNSUPPORTED "
          f"(a gap). Be rigorous; do not invent. Format:\nISSUE: ...\n  - Element: ... -> SUPPORTED [F#,F#] "
          f"| UNSUPPORTED (gap)\n\nVERIFIED FACTS:\n{factstr}\n\nGOVERNING LAW:\n{lawstr or '(none)'}")
    element_map = _llm(p1)

    # PASS 2 — counsel-ready analysis, forced to an exact SCHEMA (Ollama structured outputs)
    datectx = (f"Today is {today.isoformat()}. Use {deadline} (~10 days) as the realistic default action "
               f"deadline unless a statute/forum sets a sooner one. CV-26360 testimony is 2026-08-12 "
               f"({dtest} days away). Every date MUST be ISO (YYYY-MM-DD) and in 2026 or 2027 — NEVER earlier.")
    fields = (f"priority: 'High|Medium|Low — one-line reason'. summary: ONE sentence (current posture + the "
              f"single most important next action). objective: what VICTORY in THIS matter looks like (the "
              f"concrete outcome this forum can deliver) + the single most direct lever; 2-3 sentences. gaps: "
              f"2-3 strings — each states WHAT is missing, WHY it matters for action, and the FASTEST way to "
              f"close it (name the specific doc/source to retrieve when known, e.g. 'retrieve doc:699'). "
              f"evidence: 2-3 strings, each a CONCRETE issue→element→support with a real fact id — e.g. "
              f"'FOI obstruction: failure to act on valid records requests — SUPPORTED [F5405]' (do NOT output "
              f"the literal words 'Issue' or 'key element'). actions: 2-3 objects, the prioritized PATH TO "
              f"VICTORY (force the agency to act + escalation ladder; build a non-response record; close gaps "
              f"— NOT 'generate pattern evidence'). Each object = {{owner, deadline (YYYY-MM-DD in 2026), draft "
              f"(2-4 sentences copy-paste-ready naming docket {docket}, the specific violation, the prejudice "
              f"to the estate/heirs, and the escalation if ignored), condition}}. condition='' for an action "
              f"that can proceed now; when a BLOCKING gap exists, ALSO give an INTERIM action with "
              f"condition='Interim — while awaiting <X>' (a holding/follow-up letter that proceeds now, with "
              f"its draft) AND a CONDITIONAL action with condition='If <specific doc/info> is obtained'.")
    p2 = (f"You are a senior litigation associate. {fp}\n{sep}\n{datectx}\n"
          f"DATA-LAYER GAPS (from the pre-flight — use these to write the gaps section and any conditional/"
          f"interim actions; name the specific docs): {readiness_gaps}\n"
          f"Operator's stated objective: {objective_note or '(not set)'}\nMatter {mc} ({title}; forum {forum}; "
          f"docket {docket}). Crisp and professional; never invent facts, names, or official titles (there is "
          f"NO 'DILG Commissioner'; DILG has a Secretary, here Provincial Director Relucio). LAW DISCIPLINE "
          f"(this is a MULTI-AGENCY matter — do NOT infer law): cite ONLY statutes/sections that appear in the "
          f"GOVERNING LAW block below; never add a law, section, or circular from general knowledge. If a "
          f"needed authority is not in the block, write '[authority not embedded — obtain]'.\n"
          f"Fill each field: {fields}\n\n"
          f"ELEMENT MAP:\n{element_map}\n\nGOVERNING LAW:\n{lawstr or '(none)'}\n\nVERIFIED FACTS:\n{factstr}")
    draft = _llm(p2, 0.3, fmt=_SCHEMA)

    # PASS 3 — adversarial self-critique + revise, SAME schema
    p3 = (f"Adversarially CHECK then REVISE this memo JSON for {mc}. {fp}\n{sep}\nChecklist: (1) every statute "
          f"citation MUST appear verbatim in the GOVERNING LAW block below — DELETE any citation not present "
          f"there (no law from memory/inference; this is multi-agency, mis-citation confuses forums); match the "
          f"correct section AND sub-provision (a complaint vs a MUNICIPAL elective official is RA 7160 §61(b), "
          f"not §61(a)). (2) No fact, name, office, or "
          f"official TITLE not supported by the VERIFIED FACTS — replace any invented addressee with "
          f"'[addressee — verify]'. (3) Each action is a step toward VICTORY IN THIS MATTER with owner + a "
          f"deadline IN 2026 (use {deadline} if unsure) + 2-4 sentences of copy-paste-ready draft; no "
          f"'generate pattern evidence' action. (4) summary is ONE sentence. (5) evidence items are concrete "
          f"(no placeholder words like 'Issue' or 'key element'). (6) each gap states what's missing + why it "
          f"matters + the fastest way to close it. (7) if a BLOCKING gap exists, there is an INTERIM action "
          f"(condition='Interim — while awaiting …', proceeds now, with draft) AND a CONDITIONAL one "
          f"(condition='If … obtained'); otherwise condition=''. Keep the same fields.\nFields spec: {fields}\n\n"
          f"JSON TO REVISE:\n{draft}\n\nVERIFIED FACTS:\n{factstr}\n\nGOVERNING LAW:\n{lawstr or '(none)'}")
    final = _llm(p3, 0.2, fmt=_SCHEMA)
    parts = _coerce(final) or _coerce(draft) or {"summary": "(agent output could not be parsed)"}
    # deterministic safety-nets: dates never earlier than 2026; related is corpus-fact, not model prose
    for a in (parts.get("actions") or []):
        if isinstance(a, dict) and not re.match(r"^202[6-9]-\d\d-\d\d", str(a.get("deadline", ""))):
            a["deadline"] = deadline
    parts["related_ctx"] = related_ctx
    parts["element_map"] = element_map
    parts["_deadline"] = deadline
    return parts


def main():
    mc = sys.argv[1] if len(sys.argv) > 1 else "MWK-ARTA-1891"
    print(f"[legal_agent] reasoning over {mc} via {MODEL} (3 passes)…", flush=True)
    r = analyze(mc)
    print(json.dumps({k: v for k, v in r.items() if k != "element_map"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
