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
import json
import os
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
    return title, forum, docket, factstr, lawstr


def analyze(mc):
    title, forum, docket, factstr, lawstr = _gather(mc)
    kind = "JUDICIAL (a court case)" if mc in JUDICIAL else "ADMINISTRATIVE (agency/red-tape; NOT a court case)"
    sep = ("SEPARATION RULE: This matter is " + kind + ". CV-26360 is a SEPARATE judicial proceeding "
           "(RTC; Aug-12 testimony). An administrative matter must NEVER be said to win/lose/decide "
           "CV-26360 — link only as 'pattern evidence of obstruction usable in CV-26360 / the larger "
           "Accion Reivindicatoria.'")

    p1 = (f"You are a Philippine litigation analyst. Matter {mc} ({title}; forum: {forum}). Using ONLY "
          f"the VERIFIED FACTS and GOVERNING LAW below, identify each legal ISSUE/claim and its ELEMENTS. "
          f"For each element, list the supporting fact ids [F#], then mark it SUPPORTED or UNSUPPORTED "
          f"(a gap). Be rigorous; do not invent. Format:\nISSUE: ...\n  - Element: ... -> SUPPORTED [F#,F#] "
          f"| UNSUPPORTED (gap)\n\nVERIFIED FACTS:\n{factstr}\n\nGOVERNING LAW:\n{lawstr or '(none)'}")
    element_map = _llm(p1)

    p2 = (f"You are drafting an Action Memo block for counsel on matter {mc}. {sep}\nUse the ELEMENT MAP "
          f"below: treat SUPPORTED elements as established; list UNSUPPORTED ones as gaps to close. Cite "
          f"GOVERNING LAW by EXACT section (and correct sub-provision). Output sections:\nEXECUTIVE SUMMARY "
          f"(3-4 sentences)\nSTRENGTHS\nRISKS\nRECOMMENDED ACTIONS (numbered; each [Owner] [Deadline ~7-10 "
          f"days] then DRAFT: a ready-to-paste paragraph naming docket {docket}, the specific violation, "
          f"the prejudice to the estate/heirs, and escalation if no action by the deadline)\nGAPS\n"
          f"Do not sign.\n\nELEMENT MAP:\n{element_map}\n\nGOVERNING LAW:\n{lawstr or '(none)'}")
    draft = _llm(p2, 0.3)

    p3 = (f"Adversarially CHECK then REVISE this legal draft for matter {mc}. {sep}\nChecklist: (1) every "
          f"statute citation must match the GOVERNING LAW provided — correct section AND sub-provision "
          f"(e.g. a complaint vs a MUNICIPAL elective official is RA 7160 §61(b), not §61(a)); fix any "
          f"mismatch or remove the citation. (2) Separation respected. (3) No fact, name, office, or "
          f"OFFICIAL TITLE that is not in the VERIFIED FACTS — do NOT invent titles (e.g. there is no "
          f"'DILG Commissioner'; DILG has a Secretary and, here, Provincial Director Relucio). Replace any "
          f"unverified addressee with a role you can support, or '[addressee — verify]'. (4) Keep 2-3 "
          f"DISTINCT, specific recommendations (not one, not repetitive). Output ONLY the corrected final "
          f"memo text — no commentary, no sign-off.\n\nDRAFT:\n{draft}\n\nVERIFIED FACTS:\n{factstr}\n\nGOVERNING LAW:\n{lawstr or '(none)'}")
    final = _llm(p3, 0.2)
    return {"element_map": element_map, "analysis": final}


def main():
    mc = sys.argv[1] if len(sys.argv) > 1 else "MWK-ARTA-1891"
    print(f"[legal_agent] reasoning over {mc} via {MODEL} (3 passes)…", flush=True)
    r = analyze(mc)
    print("\n===== ELEMENT MAP =====\n" + r["element_map"])
    print("\n===== ANALYSIS (post self-critique) =====\n" + r["analysis"])


if __name__ == "__main__":
    main()
