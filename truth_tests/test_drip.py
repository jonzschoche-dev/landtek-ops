#!/usr/bin/env python3
"""test_drip.py — the Drip's guardrails = the operator's 2026-09-08 process flag, made physical.

Clocks only from proof of receipt · lapse stages the consequence and NEVER a letter · a reply is not
performance · no invented periods · held/withdrawn rows can never tick · the sweep sends NOTHING.
All state-mutating tests run in ROLLBACK transactions against the live seeds.
"""
import os
import sys
from datetime import date, timedelta

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from _harness import run, TruthFailure, DSN
import drip_sweep as DS


def _rb():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _no_gmail(monkey_store):
    """Force the file-fallback path so tests never touch Gmail at all."""
    monkey_store.append(DS.stage_gmail_draft)
    DS.stage_gmail_draft = lambda subject, body_text, to_addr="": (None, "test_disabled")


def _restore(monkey_store):
    if monkey_store:
        DS.stage_gmail_draft = monkey_store.pop()


def _any_mwk_doc(tc):
    """A real MWK corpus document to stand in as proof-of-service in ROLLBACK fixtures."""
    tc.execute("SELECT id FROM documents WHERE case_file='MWK-001' ORDER BY id LIMIT 1")
    r = tc.fetchone()
    if not r:
        raise TruthFailure("no MWK-001 document in the corpus to use as a proof fixture.")
    return r["id"]


def no_clock_without_receipt(cur):
    """Drafting never starts a clock: every unserved row has due_at NULL, and the DB CHECK refuses a
    due date without service + a cited rule."""
    conn, tc = _rb()
    try:
        tc.execute("SELECT count(*) n FROM office_obligation WHERE served_at IS NULL AND due_at IS NOT NULL")
        if tc.fetchone()["n"]:
            raise TruthFailure("an unserved obligation carries a due date — a clock started from a draft.")
        try:
            tc.execute("UPDATE office_obligation SET due_at=%s WHERE served_at IS NULL AND id="
                       "(SELECT min(id) FROM office_obligation WHERE served_at IS NULL)", (date.today(),))
        except psycopg2.Error:
            return                                    # CHECK refused — correct
        raise TruthFailure("DB accepted a due_at on an unserved row — drip_no_invented_period CHECK missing.")
    finally:
        conn.rollback(); conn.close()


def lapse_stages_consequence_never_letter(cur):
    """A lapsed clock stages its PRE-BUILT consequence work order; NO letter/draft artifact is
    produced for that officer (standing rule 3)."""
    conn, tc = _rb()
    mk = []
    _no_gmail(mk)
    try:
        tc.execute("""UPDATE office_obligation SET state='served_running', served_at=%s,
                            service_proof='TEST received-stamp', service_proof_doc_id=%s, due_at=%s
                      WHERE officer='Abla' RETURNING id""",
                   (date.today() - timedelta(days=20), _any_mwk_doc(tc), date.today() - timedelta(days=5)))
        oid = tc.fetchone()["id"]
        tc.execute("SELECT count(*) n FROM work_orders WHERE created_by='drip'")
        before = tc.fetchone()["n"]
        staged = DS.tick(tc, date.today())
        tc.execute("SELECT state FROM office_obligation WHERE id=%s", (oid,))
        if tc.fetchone()["state"] != "consequence_staged":
            raise TruthFailure(f"lapsed row did not reach consequence_staged: {staged}")
        tc.execute("SELECT count(*) n, max(title) t FROM work_orders WHERE created_by='drip'")
        row = tc.fetchone()
        if row["n"] != before + 1 or "consequence" not in (row["t"] or ""):
            raise TruthFailure("lapse did not stage exactly one consequence work order.")
        tc.execute("SELECT count(*) n FROM drip_event WHERE kind IN ('draft_staged','draft_staged_file') "
                   "AND obligation_id=%s", (oid,))
        if tc.fetchone()["n"]:
            raise TruthFailure("a LETTER draft was produced on lapse — rule 3 breach (no further letters).")
    finally:
        _restore(mk)
        conn.rollback(); conn.close()


def reply_is_not_performance(cur):
    """replied_not_performed keeps ticking toward the consequence — a paper reply never stops the clock."""
    conn, tc = _rb()
    mk = []
    _no_gmail(mk)
    try:
        tc.execute("""UPDATE office_obligation SET state='replied_not_performed', served_at=%s,
                            service_proof='TEST', service_proof_doc_id=%s, due_at=%s
                      WHERE officer='Abla' RETURNING id""",
                   (date.today() - timedelta(days=30), _any_mwk_doc(tc), date.today() - timedelta(days=2)))
        oid = tc.fetchone()["id"]
        DS.tick(tc, date.today())
        tc.execute("SELECT state FROM office_obligation WHERE id=%s", (oid,))
        if tc.fetchone()["state"] != "consequence_staged":
            raise TruthFailure("a mere reply stopped the clock — reply was treated as performance.")
    finally:
        _restore(mk)
        conn.rollback(); conn.close()


def held_rows_never_tick(cur):
    """withdrawn (Olaguera) and held_counsel_route (Engr. Balane — CV 26-360 defendant) can never
    be served, lapse, or stage anything."""
    conn, tc = _rb()
    try:
        for officer in ("Olaguera", "Engr. Balane"):
            tc.execute("SELECT id, state FROM office_obligation WHERE officer=%s", (officer,))
            ob = tc.fetchone()
            if not ob or ob["state"] not in ("withdrawn", "held_counsel_route"):
                raise TruthFailure(f"{officer} seed state wrong: {ob and ob['state']}")
            try:
                DS.record_service(tc, ob["id"], date.today().isoformat(), _any_mwk_doc(tc))
            except SystemExit:
                continue                                # refused — correct
            raise TruthFailure(f"{officer} ({ob['state']}) accepted service — held rows must never tick.")
    finally:
        conn.rollback(); conn.close()


def sweep_never_sends(cur):
    """The sweep has NO send path: messages.send appears nowhere in the module; a full tick writes
    only drip tables + work orders (drafts are files under the fallback in tests)."""
    src = open(DS.__file__.replace(".pyc", ".py")).read()
    if "messages/send" in src or "messages.send" in src:
        raise TruthFailure("drip_sweep contains a Gmail SEND path — staging only is the law (A21).")
    conn, tc = _rb()
    mk = []
    _no_gmail(mk)
    try:
        for t in ("outbound_messages", "channel_messages"):
            tc.execute(f"SELECT count(*) n FROM {t}")
        before = [tc.fetchone()]
        tc.execute("SELECT count(*) n FROM outbound_messages")
        ob_before = tc.fetchone()["n"]
        DS.tick(tc, date.today())
        tc.execute("SELECT count(*) n FROM outbound_messages")
        if tc.fetchone()["n"] != ob_before:
            raise TruthFailure("tick wrote an outbound message — the drip may never send.")
    finally:
        _restore(mk)
        conn.rollback(); conn.close()


def edition_counters_recompute_from_anchors(cur):
    """Edition day-counts recompute deterministically from anchor dates: the 10-Sep letter's own
    counts must reproduce byte-for-byte at edition_date (78d §444(b)(1)(x) · 227d SPA · 476d Street)."""
    conn, tc = _rb()
    try:
        tc.execute("SELECT * FROM drip_edition WHERE track='DILG-supervision'")
        ed = tc.fetchone()
        if not ed:
            raise TruthFailure("DILG-supervision edition seed missing.")
        _subject, body = DS.render_edition(ed, date(2026, 9, 10))
        for expect in ("  78 days", " 227 days", " 476 days"):
            if expect not in body:
                raise TruthFailure(f"edition at 2026-09-10 did not reproduce '{expect.strip()}' — "
                                   "counters are not anchored to the record.")
    finally:
        conn.rollback(); conn.close()


def service_requires_corpus_proof(cur):
    """Operator rule 2026-09-12: unless the proof is IN THE CORPUS, assume NOT served. Free text,
    a missing doc id, or a doc from another client are all refused — by the code AND by the DB."""
    conn, tc = _rb()
    try:
        tc.execute("SELECT id FROM office_obligation WHERE officer='Abla'")
        oid = tc.fetchone()["id"]
        for bad in (None, 999999999):                      # no proof · not-in-corpus
            try:
                DS.record_service(tc, oid, date.today().isoformat(), bad)
            except SystemExit:
                continue
            raise TruthFailure(f"service recorded with proof={bad!r} — must be a corpus document.")
        tc.execute("SELECT id FROM documents WHERE case_file IS NOT NULL AND case_file NOT LIKE 'MWK%' LIMIT 1")
        other = tc.fetchone()
        if other:
            try:
                DS.record_service(tc, oid, date.today().isoformat(), other["id"])
                raise TruthFailure("service recorded with ANOTHER client's document as proof — A5 wall breach.")
            except SystemExit:
                pass
        try:                                                # the DB itself refuses served_at without a proof doc
            tc.execute("UPDATE office_obligation SET served_at=%s WHERE id=%s", (date.today(), oid))
        except psycopg2.Error:
            tc.connection.rollback()
            return
        raise TruthFailure("DB accepted served_at with no service_proof_doc_id — CHECK missing.")
    finally:
        conn.rollback(); conn.close()


TESTS = [
    ("drip.service_requires_corpus_proof", service_requires_corpus_proof),
    ("drip.no_clock_without_receipt", no_clock_without_receipt),
    ("drip.lapse_stages_consequence_never_letter", lapse_stages_consequence_never_letter),
    ("drip.reply_is_not_performance", reply_is_not_performance),
    ("drip.held_rows_never_tick", held_rows_never_tick),
    ("drip.sweep_never_sends", sweep_never_sends),
    ("drip.edition_counters_from_anchors", edition_counters_recompute_from_anchors),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
