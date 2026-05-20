#!/usr/bin/env python3
"""Deploy 206 — Truth-Negotiator calibration (round 2): broaden `cesar-is-dead`
back-test fixture to accept any of the three valid death-evidence docs.

CONTEXT (deploy_205 diagnostic findings):
  The `cesar-is-dead` back-test failed because expected_doc_ids = [407] —
  Salvador Osum's Tagalog affidavit ("Patay na po") — was not in the ranker's
  top-10. The negotiator correctly reached verdict='verified' using DIFFERENT
  but valid evidence: filed Balane complaints referencing "the late Cesar M.
  De La Fuente."

USER CORRECTION (2026-05-20):
  "cesar is dead is found exclusively in the just compensation documents"

  → The canonical documentary evidence of Cesar's death lives in the just-comp
  case docs (LandBank's CV-6839 filings), not in the Balane complaints.

ENTITY-TABLE EVIDENCE:
  Entity #1348 ("Cesar de La Fuente", verified, KEYSTONE, 53 mentions) role says:
    "deceased 2017-06-21 per doc#364 (LandBank filing in CV-6839)."
  doc#364 is therefore the canonical death-evidence document.

WHAT THIS DEPLOY DOES:
  - Broadens `cesar-is-dead` expected_doc_ids from [407] to [364, 407, 441]
    so the test passes when the negotiator surfaces ANY of:
      * doc#364 — LandBank's 2018 court-filed admission (canonical)
      * doc#407 — Salvador Osum's Judicial Affidavit ("Patay na po")
      * doc#441 — Jonathan Zschoche Judicial Affidavit (corroborating)
  - Pairs with code change in truth_negotiator.py:
      * `_expand_entity_anchors()` — pulls entity aliases at probe time, so
        "Cesar M" anchor expands to "Cesar Dela Fuente", "Cesar de la Fuente",
        etc., catching doc#364 which the literal "%Cesar M%" grep missed.
      * `Court Filing` CLASS_RANK bumped 9→11 — court-filed admissions are
        the highest evidentiary class (on-record opposing-party statements),
        previously inverted below one-party complaints.

Idempotent — safe to re-run.
"""
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT id, test_name, expected_verdict, expected_doc_ids,
               expected_contains_quote, notes
          FROM back_test_suite WHERE test_name = 'cesar-is-dead'
    """)
    before = cur.fetchone()
    if not before:
        print("✗ back-test 'cesar-is-dead' not found")
        return
    print(f"BEFORE: {dict(before)}")

    cur.execute("""
        UPDATE back_test_suite
           SET expected_doc_ids = ARRAY[364, 407, 441],
               notes = 'Death evidence is multi-document per 2026-05-20 user correction: '
                       'CANONICAL = doc#364 (LandBank 2018 Comment in CV-6839, '
                       'court-filed admission by opposing party that Cesar dela Fuente '
                       'died 2017-06-21). CORROBORATING = doc#407 (Salvador Osum Tagalog '
                       'judicial affidavit, "Patay na po"), doc#441 (Zschoche Judicial '
                       'Affidavit). Per entity #1348 KEYSTONE role: "deceased 2017-06-21 '
                       'per doc#364." Test passes if ANY of these three surface in top-10. '
                       'Fixture broadened in deploy_206 along with truth_negotiator '
                       '_expand_entity_anchors() to handle Cesar M./N./Dela Fuente variants.'
         WHERE test_name = 'cesar-is-dead'
    """)

    cur.execute("""
        SELECT id, test_name, expected_verdict, expected_doc_ids,
               expected_contains_quote, notes
          FROM back_test_suite WHERE test_name = 'cesar-is-dead'
    """)
    after = cur.fetchone()
    print(f"AFTER:  {dict(after)}")
    print("\n✓ fixture broadened. Re-run back_test_diagnostic.py to confirm impact.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
