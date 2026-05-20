#!/usr/bin/env python3
"""Deploy 205 — Truth-Negotiator calibration: stale back-test #2 fixture fix.

(Authored by VPS Claude as deploy_203 in handoff; renumbered to 205 on Mac-side
push because 203 and 204 were already taken by memory updates.)

Per Phase 1.1 of LEO_MASTER_PLAN.md: the truth-negotiator is reported to refute
4 of 5 verified back-tests. Investigation found that AT LEAST ONE of those failures
is a STALE TEST FIXTURE, not a negotiator bug.

Back-test 'cesar-died-pre-2019' was seeded in deploy_120 with expected_verdict='refuted'
because at that time we had no primary evidence Cesar de la Fuente died before September 2019
— we only had the 2016 deed of sale showing him alive then.

On 2026-05-17 doc#364 (LandBank's Comment in Civil Case 6839, filed 2018-05-17) was upgraded
to PRIMARY-EVIDENCE-grade. It explicitly states: "...Cesar N. dela Fuente, administrator of
state of Mary Worrick Keesey, died on June 21, 2017." This is a court-filed admission by the
OPPOSING PARTY — stronger than self-testimony.

June 21, 2017 IS before September 2019. The claim is now TRUE.

Per memory/project_civil_case_26_360_load_bearing_dates.md §28:
  "Back-test #2 'cesar-died-pre-2019' now has primary evidence
   → expected_verdict should flip from `refuted` to `verified`."

This deploy flips it. Idempotent — safe to re-run.

After applying: systems_analyzer back-test pass rate should improve by at least 1/5
WITHOUT touching the negotiator code. Remaining 3 failures (if any) are real calibration work
— see back_test_diagnostic.py (also in deploy_205) for per-test failure traces.
"""
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Show current state of the row
    cur.execute("""
        SELECT id, test_name, expected_verdict, expected_doc_ids, expected_contains_quote, notes
          FROM back_test_suite WHERE test_name = 'cesar-died-pre-2019'
    """)
    before = cur.fetchone()
    if not before:
        print("✗ back-test 'cesar-died-pre-2019' not found — nothing to update")
        return

    print(f"BEFORE: {dict(before)}")

    cur.execute("""
        UPDATE back_test_suite
           SET expected_verdict = 'verified',
               expected_doc_ids = ARRAY[364, 441],
               expected_contains_quote = 'June 21, 2017',
               notes = 'PRIMARY EVIDENCE upgrade 2026-05-17: doc#364 (LandBank Comment, executed_filed) '
                       'explicitly states Cesar N. dela Fuente died June 21, 2017 — before September 2019. '
                       'Doc#441 (Jonathan Zschoche Judicial Affidavit) corroborates. '
                       'Was refuted in deploy_120 fixture; flipped to verified in deploy_205.'
         WHERE test_name = 'cesar-died-pre-2019'
    """)

    cur.execute("""
        SELECT id, test_name, expected_verdict, expected_doc_ids, expected_contains_quote, notes
          FROM back_test_suite WHERE test_name = 'cesar-died-pre-2019'
    """)
    after = cur.fetchone()
    print(f"AFTER:  {dict(after)}")

    print("\n✓ back-test fixture updated. Run systems_analyzer.py --skip-backtest=false to see new pass rate.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
