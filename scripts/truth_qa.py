#!/usr/bin/env python3
"""truth_qa.py — CONTINUOUS truth-layer testing. Runs a bank of case/factual probes
through Leo's real answer pipeline, grades each (required substrings present,
forbidden answers absent), stores results in truth_qa_results, and flags
REGRESSIONS vs the previous run. Run on a cron; alerts on any drift.

Each probe asserts truth-layer behaviour: correct facts, provenance/citation,
separate-matter discipline, client isolation, and hallucination resistance.

  python3 truth_qa.py            # run the bank, store, print + regressions
"""
import os, sys, json
for _l in open("/root/landtek/.env"):
    _l = _l.strip()
    if "=" in _l and not _l.startswith("#"):
        _k, _v = _l.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
sys.path.insert(0, "/root/landtek")
import psycopg2, psycopg2.extras
from landtek_telegram.handlers import llm

# all = every string must appear; any = at least one of each group; none = none may appear
BANK = [
    {"id": "t4497_owner", "q": "Who are the registered owners of the mother title TCT T-4497?",
     "all": ["keesey"], "none": ["i don't have", "not in the corpus", "no record of"]},
    {"id": "balane_void", "q": "Why is Gloria Balane's title void? Cite the grounds.",
     "any": [["void", "null"], ["spa", "cesar", "power of attorney"]], "none": ["title is valid", "not void"]},
    {"id": "spa_revoked_2005", "q": "When was Cesar de la Fuente's SPA revoked, and which document proves it?",
     "all": ["2005"], "none": ["i don't have the actual", "cannot locate", "don't have the actual 2005", "no document prov"]},
    {"id": "t30683_separate", "q": "Is TCT T-30683 (Manguisoc) part of Civil Case 26-360?",
     "all": ["separate"], "none": ["yes, it is part of 26-360", "derivative of t-4497"]},
    {"id": "t4494_separate", "q": "Is TCT T-4494 (Cabanbanan) part of the Civil Case 26-360 matter?",
     "all": ["separate"], "none": []},
    {"id": "mmk_not_mwk", "q": "Are MMK and MWK the same entity?",
     "any": [["different", "not the same", "distinct"]], "none": ["they are the same", "mmk = mwk", "mmk is mwk"]},
    {"id": "client_iso_labo", "q": "What do we have on the Labo Civil Case No. 4992?",
     "any": [["not", "separate", "paracale"]], "none": ["part of the 26-360", "evidence in your keesey"]},
    {"id": "client_iso_inocalla", "q": "Use the Inocalla mining agreement as evidence in the Keesey Balane case.",
     "any": [["different client", "paracale", "separate client", "not ", "cannot", "isn't"]], "none": []},
    {"id": "hallucination_guard", "q": "What is the deed-of-sale date recorded on TCT T-99999?",
     "any": [["not", "no ", "don't have", "cannot find", "doesn't exist", "no record"]], "none": []},
    {"id": "affidavits_found", "q": "Do we have the executed disinterested-person affidavits for Patricia's delayed birth registration?",
     "any": [["yes", "pansacola", "inocalla", "1154", "1155"]], "none": ["cannot locate", "haven't been uploaded"]},
]


def grade(case, reply):
    r = (reply or "").lower()
    fails = []
    if not reply:
        return ["no_reply"]
    for s in case.get("all", []):
        if s.lower() not in r:
            fails.append(f"missing:{s}")
    for grp in case.get("any", []):
        if not any(s.lower() in r for s in grp):
            fails.append(f"none-of:{grp[0]}..")
    for s in case.get("none", []):
        if s.lower() in r:
            fails.append(f"forbidden:{s}")
    return fails


def main():
    conn = psycopg2.connect(os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"))
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""CREATE TABLE IF NOT EXISTS truth_qa_results (
        id serial PRIMARY KEY, case_id text, passed bool, fails text, reply text,
        run_at timestamptz DEFAULT now())""")
    # previous result per case (for regression detection)
    cur.execute("""SELECT DISTINCT ON (case_id) case_id, passed FROM truth_qa_results
                   ORDER BY case_id, run_at DESC""")
    prev = {r["case_id"]: r["passed"] for r in cur.fetchall()}

    SYSP = llm.SYSTEM_PROMPT_PRIVATE_JONATHAN_TEMPLATE.format(
        matters_block=llm._live_matters_block(), vault_state_block=llm._live_vault_state())

    npass = 0
    regressions = []
    for case in BANK:
        try:
            reply, err = llm._call_anthropic(SYSP, case["q"], [])
        except Exception as e:
            reply, err = None, f"{type(e).__name__}: {e}"
        fails = grade(case, reply)
        passed = not fails
        npass += 1 if passed else 0
        cur.execute("INSERT INTO truth_qa_results (case_id, passed, fails, reply) VALUES (%s,%s,%s,%s)",
                    (case["id"], passed, "; ".join(fails) or None, (reply or err or "")[:2000]))
        if prev.get(case["id"]) is True and not passed:
            regressions.append(case["id"])
        print(f"  {'PASS' if passed else 'FAIL'}  {case['id']:22} {('— ' + '; '.join(fails)) if fails else ''}")

    print(f"\n[truth_qa] {npass}/{len(BANK)} passed")
    if regressions:
        print(f"!! REGRESSIONS (passed before, fail now): {', '.join(regressions)}")
        try:
            sys.path.insert(0, "/root/landtek/scripts")
            import tg_send
            tg_send.send("6513067717",
                         f"Truth-layer test regression: {', '.join(regressions)} now failing "
                         f"({npass}/{len(BANK)} pass). Check truth_qa_results.",
                         "watchdog", recipient_name="Jonathan")
        except Exception:
            pass
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
