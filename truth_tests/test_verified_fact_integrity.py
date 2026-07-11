#!/usr/bin/env python3
"""test_verified_fact_integrity.py — A78: a verified fact is earned; contradiction is caught at
the gate; facts do not rot.

Covers ONLY the code deploy_870 added ("VERIFIED requires a grounded basis" is the pre-existing
tg_prov_facts / ontvv_v3 enforcement, already guarded by test_provenance_integrity — not re-tested):

  1. contradiction.conflicts_with_verified — the deterministic, $0 INGEST gate: an incoming record
     whose event-date CONFLICTS with a VERIFIED fact is flagged (same date = corroboration, passes).
  2. The gate is WIRED: a contradicting ingest through harvest_facts is HELD (no matter_facts row,
     visible contradiction_hold), upstream of any propagation.
  3. Facts don't rot (re-ingest): when a source doc's extracted_text changes, no-longer-grounded
     verified facts are DEMOTED (deploy_830) and the doc's verify_worker_log cooldown is CLEARED
     (deploy_870 re-arm) so verified can be re-earned against the new text.
  4. Facts don't rot (challenge): contradiction.scan() records an A74-style CHALLENGE with a
     machine-checkable recheck_condition, and close_resolved_challenges() releases it when the
     contradiction resolves.

All negative tests run in rolled-back transactions — prod untouched. Count-independent.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/root/landtek/scripts")
sys.path.insert(0, "/root/landtek")

import psycopg2
import psycopg2.extras

from _harness import run, TruthFailure, DSN

DEED_TEXT = ("REPUBLIC OF THE PHILIPPINES. KNOW ALL MEN BY THESE PRESENTS: This Deed of Absolute "
             "Sale executed on June 5, 2016 by and between the synthetic parties, covering the "
             "parcel of land under TCT T-99123 situated in the Municipality of Truthtest, "
             "Province of Synthetic, containing an area of 1,234 square meters more or less.")
DEED_EXCERPT = "Deed of Absolute Sale executed on June 5, 2016 by and between the synthetic parties"
CONFLICT_TEXT = ("Synthetic pleading for the record: the annexed instrument shows the Deed of "
                 "Absolute Sale dated September 29, 2019 as presented by the adverse party, "
                 "which this office received for evaluation and comparison against the record. "
                 "The same annex covers the parcel registered under TCT T-99123 with an area "
                 "of 1,234 square meters more or less per the technical description on file.")


def _txn():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _mk_doc(c, case_file, text):
    c.execute("""INSERT INTO documents (master_form, ingest_source, original_filename, mime_type,
                   file_path, content_hash, case_file, classification, extracted_text)
                 VALUES ('digital','truth_test','tt_a78_synth.txt','text/plain',
                         '/tmp/tt_a78_synth.txt', md5(random()::text), %s,
                         'truth_test_synthetic', %s) RETURNING id""", (case_file, text))
    return c.fetchone()["id"]


def _mk_verified(c, matter, doc_id, statement, excerpt):
    c.execute("""INSERT INTO matter_facts (matter_code, statement, fact_kind, source_kind,
                   source_id, excerpt, provenance_level, confidence, created_by)
                 VALUES (%s,%s,'event','doc',%s,%s,'verified',0.9,'truth_test')
                 RETURNING id""", (matter, statement, str(doc_id), excerpt))
    return c.fetchone()["id"]


def contradiction_gate_detects_conflict(cur):
    """A78 negative: same event + different date vs a VERIFIED fact -> conflict; same date -> pass."""
    import contradiction as CONTRA
    conn, c = _txn()
    try:
        matter = "TT-A78-CONTRAGATE"
        doc = _mk_doc(c, None, DEED_TEXT)
        fid = _mk_verified(c, matter, doc,
                           "The synthetic Deed of Absolute Sale was executed on June 5, 2016.",
                           DEED_EXCERPT)
        conflicts = CONTRA.conflicts_with_verified(c, matter, CONFLICT_TEXT)
        if not conflicts:
            raise TruthFailure("a Sept-29-2019 deed date sailed past a verified June-5-2016 deed "
                               "date — the A78 ingest gate does not bite")
        k = conflicts[0]
        if k["incoming"] != "2019-09" or "2016-06" not in k["verified"] or fid not in k["fact_ids"]:
            raise TruthFailure(f"conflict detected but mis-attributed: {k}")
        print(f"      [bite] event '{k['event']}': incoming {k['incoming']} vs verified "
              f"{k['verified']} (fact_ids {k['fact_ids']})")
        same = CONTRA.conflicts_with_verified(
            c, matter, "the deed of absolute sale executed on June 5, 2016 is confirmed")
        if same:
            raise TruthFailure(f"corroborating same-date mention flagged as conflict "
                               f"(false positive): {same}")
    finally:
        conn.rollback(); c.close(); conn.close()


def harvest_holds_contradicting_ingest(cur):
    """A78 negative, end-to-end: a contradicting doc ingested through harvest -> the conflicting
    fact is HELD (no row), visibly, while non-conflicting facts from the same doc still flow."""
    import contradiction  # noqa: F401 (harvest imports it)
    import harvest_facts
    conn, c = _txn()
    try:
        matter = "TT-A78-CONTRAGATE"
        base = _mk_doc(c, None, DEED_TEXT)
        _mk_verified(c, matter, base,
                     "The synthetic Deed of Absolute Sale was executed on June 5, 2016.",
                     DEED_EXCERPT)
        c.execute("SELECT client_code FROM clients ORDER BY client_code LIMIT 1")
        client = c.fetchone()["client_code"]
        incoming = _mk_doc(c, client, CONFLICT_TEXT)
        c.execute("INSERT INTO document_matter_links (doc_id, matter_code) VALUES (%s,%s)",
                  (incoming, matter))
        harvest_facts.harvest_matter(c, matter, go=True)
        c.execute("""SELECT count(*) AS n FROM matter_facts WHERE matter_code=%s AND source_id=%s
                       AND (statement ILIKE '%%september 29, 2019%%'
                            OR excerpt ILIKE '%%september 29, 2019%%')""", (matter, str(incoming)))
        if c.fetchone()["n"] != 0:
            raise TruthFailure("the contradicting Sept-29-2019 fact was WRITTEN — conflict "
                               "propagated instead of held at ingest")
        c.execute("""SELECT description FROM holes_findings
                     WHERE routine_name='ingestion_fidelity_gate' AND hole_type='contradiction_hold'
                       AND doc_id=%s AND matter_code=%s AND status='open'""", (incoming, matter))
        hold = c.fetchone()
        if not hold:
            raise TruthFailure("contradicting ingest was refused SILENTLY — no visible hold")
        print(f"      [bite] {hold['description'][:170]}…")
        c.execute("SELECT count(*) AS n FROM matter_facts WHERE matter_code=%s AND source_id=%s",
                  (matter, str(incoming)))
        if c.fetchone()["n"] == 0:
            raise TruthFailure("gate blanket-refused the whole doc — non-conflicting facts "
                               "(title reference) should still flow")
    finally:
        conn.rollback(); c.close(); conn.close()


def reingest_rearms_recheck(cur):
    """A78 'facts don't rot' negative: source text re-arrives -> ungrounded verified fact DEMOTED
    (deploy_830) AND the doc's read-cooldown CLEARED (deploy_870) so verified can be re-earned."""
    conn, c = _txn()
    try:
        matter = "TT-A78-REARM"
        doc = _mk_doc(c, None, DEED_TEXT)
        fid = _mk_verified(c, matter, doc,
                           "The synthetic Deed of Absolute Sale was executed on June 5, 2016.",
                           DEED_EXCERPT)
        c.execute("INSERT INTO verify_worker_log (doc_id, n_verified, n_proposed, status) "
                  "VALUES (%s, 1, 0, 'ok')", (doc,))
        c.execute("UPDATE documents SET extracted_text=%s WHERE id=%s",
                  ("Corrected re-OCR: this synthetic instrument is a Contract of Lease signed on "
                   "January 15, 2021 — the earlier transcription was a misread of a different page.",
                   doc))
        c.execute("SELECT provenance_level FROM matter_facts WHERE id=%s", (fid,))
        lvl = c.fetchone()["provenance_level"]
        if lvl == "verified":
            raise TruthFailure("extracted_text changed but the no-longer-grounded fact is STILL "
                               "verified — the reground guard is not firing")
        c.execute("SELECT count(*) AS n FROM verify_worker_log WHERE doc_id=%s", (doc,))
        left = c.fetchone()["n"]
        if left != 0:
            raise TruthFailure(f"re-ingested doc still has {left} cooldown row(s) — the re-arm "
                               "is missing; demoted facts would sit 14 days in limbo")
        print(f"      [bite] fact {fid}: verified -> {lvl}; cooldown rows for doc {doc}: {left} "
              f"(re-read re-armed)")
    finally:
        conn.rollback(); c.close(); conn.close()


def challenge_recorded_and_recheck_closes(cur):
    """A78 challenge negative: verified facts in a date contradiction get an OPEN challenge with a
    machine-checkable recheck_condition; resolving the contradiction auto-releases it (A74)."""
    import contradiction as CONTRA
    conn, c = _txn()
    try:
        matter = "TT-A78-CHLG"
        text = DEED_TEXT + (" Whereas a second annex presented the Deed of Absolute Sale dated "
                            "September 29, 2019 for the same parcel, per the adverse submission.")
        doc = _mk_doc(c, None, text)
        _mk_verified(c, matter, doc,
                     "The synthetic Deed of Absolute Sale was executed on June 5, 2016.",
                     DEED_EXCERPT)
        _mk_verified(c, matter, doc,
                     "An annex presents the synthetic Deed of Absolute Sale as dated September 29, 2019.",
                     "Deed of Absolute Sale dated September 29, 2019 for the same parcel")
        CONTRA.scan(c)
        c.execute("""SELECT description, metadata->>'recheck_condition' AS rc FROM holes_findings
                     WHERE routine_name='contradiction_challenge' AND matter_code=%s
                       AND status='open'""", (matter,))
        ch = c.fetchone()
        if not ch:
            raise TruthFailure("verified facts carry two dates for one deed but NO challenge was "
                               "recorded — challenged facts would stay silently trusted")
        if not (ch["rc"] or "").strip():
            raise TruthFailure(f"challenge lacks a machine-checkable recheck_condition (A74): {ch}")
        print(f"      [bite] {ch['description'][:150]}…")
        print(f"      [recheck_condition] {ch['rc'][:130]}…")
        c.execute("UPDATE contradictions SET status='reconciled' WHERE matter_code=%s", (matter,))
        CONTRA.close_resolved_challenges(c)
        c.execute("""SELECT status FROM holes_findings
                     WHERE routine_name='contradiction_challenge' AND matter_code=%s""", (matter,))
        st = c.fetchone()["status"]
        if st != "remediated":
            raise TruthFailure(f"contradiction resolved but the challenge stayed '{st}' — the A74 "
                               "recheck sweep is not honoring its own recheck_condition")
    finally:
        conn.rollback(); c.close(); conn.close()


TESTS = [
    ("A78 contradiction gate detects date conflict vs verified", contradiction_gate_detects_conflict),
    ("A78 contradicting ingest held at harvest (not propagated)", harvest_holds_contradicting_ingest),
    ("A78 re-ingested source demotes ungrounded + re-arms re-read", reingest_rearms_recheck),
    ("A78 challenged verified facts carry a recheck that releases", challenge_recorded_and_recheck_closes),
]

if __name__ == "__main__":
    passed, failed = run(TESTS)
    sys.exit(1 if failed else 0)
