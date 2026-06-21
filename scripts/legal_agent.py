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

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://100.117.118.47:11434")
MODEL = os.environ.get("LEGAL_AGENT_MODEL", "qwen2.5:14b-instruct")
JUDICIAL = {"MWK-CV26360", "MWK-CV6839", "MWK-PARALLEL-CV6922", "MWK-PARALLEL-CRIM9221", "PAR-CV13-131220"}


def _llm(prompt, temp=0.2):
    body = {"model": MODEL, "stream": False, "options": {"temperature": temp}, "prompt": prompt}
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read()).get("response", "").strip()


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
    # deterministic party-overlap with related matters → how tightly coupled this really is
    focal = _party_ids(cur, mc)
    cur.execute("""SELECT doc_matter, count(*) FROM matter_relevance WHERE focal_matter=%s AND tier='RELATED'
                   AND doc_matter IS NOT NULL AND doc_matter<>%s GROUP BY 1 ORDER BY 2 DESC LIMIT 5""", (mc, mc))
    shared = []
    for rm, _n in cur.fetchall():
        inter = focal & _party_ids(cur, rm)
        if inter:
            shared.append(f"{rm} (shares party entity ids {sorted(inter)})")
    if not focal:
        party_link = "This matter has NO recorded parties of its own; any parallel-case linkage is LOOSE/SECONDARY, not a driver."
    elif shared:
        party_link = "Shared parties exist: " + "; ".join(shared) + " — linkage may be stronger for those, but stay proportional."
    else:
        party_link = "NO shared parties with any related matter — parallel-case linkage is LOOSE/SECONDARY, not a driver."
    return title, forum, docket, factstr, lawstr, objective_note, party_link


def _split_markers(text):
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"\s*\[?(PRIORITY|SUMMARY|OBJECTIVE|GAPS|EVIDENCE|ACTIONS|LINKAGE|STRATEGIC)\]?\s*[:\-]?\s*(.*)", line)
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


def analyze(mc):
    title, forum, docket, factstr, lawstr, objective_note, party_link = _gather(mc)
    today = datetime.date.today()
    deadline = (today + datetime.timedelta(days=10)).isoformat()
    aug12 = datetime.date(2026, 8, 12)
    dtest = (aug12 - today).days
    kind = "JUDICIAL (a court case)" if mc in JUDICIAL else "ADMINISTRATIVE (agency/red-tape; NOT a court case)"
    fp = ("FIRST PRINCIPLES: the SOLE purpose of this memo is VICTORY in " + mc + " itself — forcing this "
          "forum to ACT. 'Victory' = the agency/court delivering the concrete relief this forum can give "
          "(for an administrative matter: the agency compels the LGU to comply / issues a directive or "
          "adverse finding / meaningful escalation succeeds). Evidence for parallel or related cases is a "
          "BYPRODUCT, NEVER a driver — do not overstate it, do not let it shape the recommended actions.")
    sep = ("SEPARATION & COUPLING: This matter is " + kind + ". " + party_link + " CV-26360 is a SEPARATE "
           "judicial proceeding; never say this matter decides it. Any cross-case value is incidental.")

    # PASS 1 — element map (rigor: issues → elements → supported/gap)
    p1 = (f"You are a Philippine litigation analyst. Matter {mc} ({title}; forum: {forum}). Using ONLY "
          f"the VERIFIED FACTS and GOVERNING LAW below, identify each legal ISSUE/claim and its ELEMENTS. "
          f"For each element, list the supporting fact ids [F#], then mark it SUPPORTED or UNSUPPORTED "
          f"(a gap). Be rigorous; do not invent. Format:\nISSUE: ...\n  - Element: ... -> SUPPORTED [F#,F#] "
          f"| UNSUPPORTED (gap)\n\nVERIFIED FACTS:\n{factstr}\n\nGOVERNING LAW:\n{lawstr or '(none)'}")
    element_map = _llm(p1)

    # PASS 2 — counsel-ready marked block
    datectx = (f"Today is {today.isoformat()}. Use {deadline} (~10 days) as the realistic default action "
               f"deadline unless a statute/forum sets a sooner one. CV-26360 testimony is 2026-08-12 "
               f"({dtest} days away) — flag any date-sensitive item relative to it. All dates ISO (YYYY-MM-DD).")
    p2 = (f"You are a senior litigation associate writing a COUNSEL-READY action-memo block for {mc} "
          f"({title}; forum {forum}; docket {docket}). {fp}\n{sep}\n{datectx}\n"
          f"Operator's stated objective for this matter: {objective_note or '(not set)'}\n"
          f"Principles: counsel reads fast — every line must give a verified fact, name a gap, or enable an "
          f"action; crisp and professional; no filler, no long hybrid sentences. Cite law by exact "
          f"section/sub-provision. Never invent facts, names, or official titles (there is NO 'DILG "
          f"Commissioner'; DILG has a Secretary, and here Provincial Director Relucio). Output EXACTLY these "
          f"marked sections and nothing else:\n"
          f"[PRIORITY] High|Medium|Low — one-line reason\n"
          f"[SUMMARY] ONE sentence: current posture + the single most important next action.\n"
          f"[OBJECTIVE] What VICTORY in THIS matter looks like — the concrete outcome this forum can deliver "
          f"— and the single most direct lever to force it. 2-3 lines. (Victory is the agency acting, not "
          f"helping any other case.)\n"
          f"[GAPS] 2-4 short bullets: what is missing that blocks stronger action.\n"
          f"[EVIDENCE] the 2-3 MOST important issues only — each one line: Issue — key element — SUPPORTED [F#] or GAP.\n"
          f"[ACTIONS] 2-3 numbered = the prioritized PATH TO VICTORY: (a) force the agency to act (a time-bound "
          f"demand + a concrete escalation ladder if ignored), (b) build a clean record of non-response, "
          f"(c) close the substance gaps. Each: Owner; Deadline; then 'DRAFT:' 2-4 sentences of copy-paste-ready "
          f"text naming docket {docket}, the specific violation, the prejudice to the estate/heirs, and the "
          f"escalation. Do NOT list 'generate pattern evidence' as an action.\n"
          f"[LINKAGE] Relevance to parallel/related cases — SECONDARY, a byproduct only, 1-2 lines MAX. "
          f"Be honest and proportional given: {party_link}\n\n"
          f"ELEMENT MAP:\n{element_map}\n\nGOVERNING LAW:\n{lawstr or '(none)'}\n\nVERIFIED FACTS:\n{factstr}")
    draft = _llm(p2, 0.3)

    # PASS 3 — adversarial self-critique + revise (keep the marked structure)
    p3 = (f"Adversarially CHECK then REVISE this counsel memo block for {mc}. {fp}\n{sep}\nChecklist: (1) every "
          f"statute citation matches the GOVERNING LAW — correct section AND sub-provision (a complaint vs a "
          f"MUNICIPAL elective official is RA 7160 §61(b), not §61(a)); fix or remove. (2) No fact, name, "
          f"office, or official TITLE not supported by the VERIFIED FACTS — replace any invented addressee "
          f"with '[addressee — verify]'. (3) Each [ACTIONS] item is a step toward VICTORY IN THIS MATTER "
          f"(forcing the agency to act), with Owner + concrete Deadline + 2-4 sentences of genuinely "
          f"copy-paste-ready DRAFT text; no 'generate pattern evidence' action. (4) [OBJECTIVE] states what "
          f"victory in THIS matter is + the lever. (5) [LINKAGE] is SECONDARY and PROPORTIONAL — given "
          f"'{party_link}', it must NOT frame any parallel case as a major asset; if no shared parties, say "
          f"the connection is loose and not a driver, ≤2 lines. (6) [SUMMARY] one sentence. (7) Keep the EXACT "
          f"marked structure ([PRIORITY]/[SUMMARY]/[OBJECTIVE]/[GAPS]/[EVIDENCE]/[ACTIONS]/[LINKAGE]); concise, "
          f"professional. Output ONLY the corrected marked block — no commentary.\n\nBLOCK:\n{draft}\n\n"
          f"VERIFIED FACTS:\n{factstr}\n\nGOVERNING LAW:\n{lawstr or '(none)'}")
    final = _llm(p3, 0.2)
    parts = _split_markers(final)
    if "summary" not in parts:           # parsing fell through — keep the raw text usable
        parts = {"summary": final[:600]}
    parts["element_map"] = element_map
    parts["_deadline"] = deadline
    return parts


def main():
    mc = sys.argv[1] if len(sys.argv) > 1 else "MWK-ARTA-1891"
    print(f"[legal_agent] reasoning over {mc} via {MODEL} (3 passes)…", flush=True)
    r = analyze(mc)
    for k in ("priority", "summary", "objective", "gaps", "evidence", "actions", "linkage"):
        print(f"\n===== {k.upper()} =====\n" + r.get(k, "(missing)"))


if __name__ == "__main__":
    main()
