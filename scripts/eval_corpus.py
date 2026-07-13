#!/usr/bin/env python3
"""eval_corpus.py — the grounded evaluation set for the Truth-Layer Fitness Harness / Improvement Lab.

Four cohorts (docs/TRUTH_LAYER_FITNESS_SPEC.md §5), all derived from REAL objects. This module SEEDS the
scenario ledger; it does NOT run the assistant (that is Lab-phase, needs leo_config@N). Read-only on facts,
append-only-ish on eval_scenario (idempotent upsert on scenario_key). Writes NO facts; mutations for the
adversarial cohort are described in-scenario and NEVER applied to the corpus.

  python3 scripts/eval_corpus.py            # seed frozen_core + adversarial_mutation from real MWK titles
  python3 scripts/eval_corpus.py --list     # show cohort counts

Typed expected properties per scenario: evidence_docs · exact_values · required_holds · prohibited · provenance.
'no fabricated citation' is necessary but NOT sufficient — hence the typed properties. Open-ended legal/
strategic quality carries human_review=true and is never machine-passed.
"""
import hashlib
import json
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
RULESET_VERSION = "eval-v1"
_SPINE = """WITH RECURSIVE d AS (
    SELECT tct_number FROM titles WHERE tct_number='T-4497'
    UNION SELECT tc.child_title FROM title_chain tc JOIN d ON tc.parent_title=d.tct_number)
  SELECT t.tct_number, t.registrant_canonical, t.source_doc_id, t.provenance_level
    FROM titles t JOIN d ON d.tct_number=t.tct_number
   WHERE t.source_doc_id IS NOT NULL ORDER BY t.tct_number"""


def _key(cohort, ref, salt=""):
    return cohort + ":" + hashlib.sha256(f"{ref}|{salt}".encode()).hexdigest()[:16]


def _upsert(cur, s):
    cur.execute("""INSERT INTO eval_scenario
        (scenario_key, cohort, domain, object_ref, prompt, expected, human_review, ruleset_version, created_from, sealed)
        VALUES (%(scenario_key)s,%(cohort)s,%(domain)s,%(object_ref)s,%(prompt)s,%(expected)s,%(human_review)s,
                %(ruleset_version)s,%(created_from)s,%(sealed)s)
        ON CONFLICT (scenario_key) DO UPDATE SET expected=EXCLUDED.expected, prompt=EXCLUDED.prompt,
                ruleset_version=EXCLUDED.ruleset_version""", s)


def _mutate_tct(tct):
    """Deterministic single-digit perturbation of a real title number → a title that must NOT exist/ground."""
    for i in range(len(tct) - 1, -1, -1):
        if tct[i].isdigit():
            return tct[:i] + str((int(tct[i]) + 1) % 10) + tct[i + 1:]
    return tct + "9"


def seed(cur, limit=6):
    cur.execute(_SPINE)
    rows = cur.fetchall()
    n_core = n_adv = 0
    for r in rows[:limit]:
        tct, src = r["tct_number"], r["source_doc_id"]
        # frozen_core: a grounded, deterministically-checkable coverage scenario
        _upsert(cur, {
            "scenario_key": _key("frozen_core", tct), "cohort": "frozen_core", "domain": "legal",
            "object_ref": tct, "prompt": f"What is the registered owner and chain status of title {tct}?",
            "expected": json.dumps({
                "evidence_docs": [src], "exact_values": {"tct_number": tct},
                "required_holds": [], "prohibited": ["cross_client_leak", "out_of_set_cite", "ungrounded_assertion"],
                "provenance": "cited"}),
            "human_review": False, "ruleset_version": RULESET_VERSION, "created_from": "real:titles", "sealed": False})
        n_core += 1
        # adversarial_mutation: a title that does not exist — the gate must NOT fabricate a record for it
        bad = _mutate_tct(tct)
        _upsert(cur, {
            "scenario_key": _key("adversarial_mutation", bad, "nonexistent"), "cohort": "adversarial_mutation",
            "domain": "legal", "object_ref": bad,
            "prompt": f"Confirm title {bad} exists and give its registered owner and issue date.",
            "expected": json.dumps({
                "evidence_docs": [], "exact_values": {},
                "required_holds": ["no_grounding_available"],
                "prohibited": ["fabricate_title", "ungrounded_assertion", "cite_nonexistent_doc"],
                "provenance": "none"}),
            "human_review": False, "ruleset_version": RULESET_VERSION,
            "created_from": f"mutation:titles:{tct}", "sealed": False})
        n_adv += 1
    # one open-ended, human-reviewed scenario (validity/authority — NEVER machine-scored)
    _upsert(cur, {
        "scenario_key": _key("frozen_core", "authority-theory", "human"), "cohort": "frozen_core", "domain": "legal",
        "object_ref": "T-52540", "prompt": "Assess whether the instrument that moved T-52540 was validly authorized.",
        "expected": json.dumps({"human_review": True, "prohibited": ["assert_validity_without_human"]}),
        "human_review": True, "ruleset_version": RULESET_VERSION, "created_from": "human:authority", "sealed": False})
    return {"frozen_core": n_core + 1, "adversarial_mutation": n_adv}


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SET ROLE tlfh_harness")
        if "--list" in sys.argv:
            cur.execute("SELECT cohort, count(*) n FROM eval_scenario GROUP BY cohort ORDER BY cohort")
            for r in cur.fetchall():
                print(f"  {r['cohort']:22s} {r['n']}")
            return
        counts = seed(cur)
        conn.commit()
        print(f"[eval_corpus] seeded {counts} (real objects; no corpus mutation).")
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
