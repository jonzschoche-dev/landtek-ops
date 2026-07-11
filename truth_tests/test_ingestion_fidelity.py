#!/usr/bin/env python3
"""test_ingestion_fidelity.py — A77: ingestion is a fact-source, not a file-drop.

Covers ONLY the code deploy_870 added (the pre-existing enforcement — tg_prov_facts verbatim
grounding, ontvv_* triggers, sink resolve-or-hold — is covered by test_provenance_integrity /
test_lossless_comms_intake and is not re-tested here):

  1. GRADED resolution (comms_artifact_sink): a bind below COMMS_BIND_MIN_CONF is HELD with the
     candidate bind + confidence + matched identity RECORDED on the ledger (auditable, never
     guessed); an explicit operator bind (bind_confidence NULL) grades 1.0 and passes.
  2. WRITER-side owner gate (ingest_gate.owner_gate): a fact-write citing a doc whose client owner
     cannot be resolved is REFUSED + held — the exact V4 null-owner bypass class proven live
     2026-07-11 (docs 1172/1177 seeded MWK-OP-PETITION facts). Negative-tested end-to-end through
     harvest_facts AND verify_worker, in rolled-back transactions (prod untouched).

Count-independent: no live-count assertions; every check is a synthetic-row negative test.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/root/landtek/scripts")
sys.path.insert(0, "/root/landtek")

import psycopg2
import psycopg2.extras

from _harness import run, TruthFailure, DSN

LONG_TEXT = ("REPUBLIC OF THE PHILIPPINES, PROVINCE OF TRUTHTEST. This synthetic instrument "
             "references TCT T-99123 covering a parcel of land situated in Barangay Synthetic, "
             "containing an area of 1,234 square meters, dated reference June 5, 2016, for the "
             "consideration of P 123,456.00 paid in full. " * 2)


def _txn():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _mk_doc(c, case_file, text):
    c.execute("""INSERT INTO documents (master_form, ingest_source, original_filename, mime_type,
                   file_path, content_hash, case_file, classification, extracted_text)
                 VALUES ('digital','truth_test','tt_a77_synth.txt','text/plain',
                         '/tmp/tt_a77_synth.txt', md5(random()::text), %s,
                         'truth_test_synthetic', %s) RETURNING id""", (case_file, text))
    return c.fetchone()["id"]


def _real_client(c):
    c.execute("SELECT client_code FROM clients ORDER BY client_code LIMIT 1")
    r = c.fetchone()
    if not r:
        raise TruthFailure("no clients row exists — cannot build the control case")
    return r["client_code"]


def low_confidence_bind_held(cur):
    """A77(1) negative: bind at 0.50 < threshold -> HELD, confidence + identity recorded."""
    import comms_artifact_sink as sink
    prev = os.environ.get("COMMS_BIND_MIN_CONF")
    os.environ["COMMS_BIND_MIN_CONF"] = "0.80"
    conn, c = _txn()
    try:
        client = _real_client(c)
        c.execute("INSERT INTO channels (name) VALUES ('truthtest-a77') RETURNING id")
        chan_id = c.fetchone()["id"]
        c.execute("""INSERT INTO channel_users (channel_id, channel_user_id, display_name,
                       mapped_client_code, bind_confidence)
                     VALUES (%s, 'tt-lowconf-user', 'TT Low Conf', %s, 0.50)""", (chan_id, client))
        r = sink.land_artifact("truthtest-a77", "tt-lowconf-user", None, "t.pdf",
                               b"%PDF-1.4 tt synthetic", mime="application/pdf", conn=conn)
        if r.get("status") != "held" or r.get("reason") != "low_confidence_bind":
            raise TruthFailure(f"below-threshold bind was NOT held: {r}")
        if r.get("client_code") is not None:
            raise TruthFailure(f"held artifact still carries a client_code (guessed bind): {r}")
        c.execute("""SELECT status, reason, bind_confidence, matched_identity, client_code
                     FROM comms_artifacts WHERE channel='truthtest-a77'
                     ORDER BY id DESC LIMIT 1""")
        led = c.fetchone()
        if not led or led["status"] != "held":
            raise TruthFailure(f"no held ledger row recorded for the low-confidence bind: {led}")
        if led["bind_confidence"] is None or float(led["bind_confidence"]) != 0.50:
            raise TruthFailure(f"bind_confidence not recorded on the held ledger row: {led}")
        if not (led["matched_identity"] or "").strip():
            raise TruthFailure(f"matched_identity not recorded — held artifact not auditable: {led}")
        if led["client_code"] is not None:
            raise TruthFailure(f"held ledger row carries client_code — a hold binds to nobody: {led}")
        print(f"      [bite] {led['reason']}  (bind_confidence={led['bind_confidence']}, "
              f"matched_identity={led['matched_identity']})")
        # control: explicit operator bind (bind_confidence NULL) grades 1.0 -> clears the threshold
        c.execute("UPDATE channel_users SET bind_confidence=NULL WHERE channel_user_id='tt-lowconf-user'")
        cl, conf, ident = sink._resolve_client(c, "truthtest-a77", "tt-lowconf-user")
        if cl != client or conf != 1.0:
            raise TruthFailure(f"explicit bind should grade 1.0 for {client}, got ({cl}, {conf})")
    finally:
        conn.rollback(); c.close(); conn.close()
        if prev is None:
            os.environ.pop("COMMS_BIND_MIN_CONF", None)
        else:
            os.environ["COMMS_BIND_MIN_CONF"] = prev


def harvest_refuses_unresolved_owner(cur):
    """A77(1) negative: harvest on a doc with NO resolvable client owner -> zero facts, visible hold.
    Control: same text under a resolvable owner -> facts flow (the gate discriminates, not blankets)."""
    import harvest_facts
    conn, c = _txn()
    try:
        matter = "TT-A77-OWNERGATE"
        orphan = _mk_doc(c, None, LONG_TEXT)          # case_file NULL -> owner unresolvable
        c.execute("INSERT INTO document_matter_links (doc_id, matter_code) VALUES (%s,%s)",
                  (orphan, matter))
        n, nd = harvest_facts.harvest_matter(c, matter, go=True)
        c.execute("SELECT count(*) AS n FROM matter_facts WHERE matter_code=%s AND source_id=%s",
                  (matter, str(orphan)))
        if c.fetchone()["n"] != 0:
            raise TruthFailure(f"harvest formed an edge from unresolved-owner doc {orphan} — "
                               f"the V4 null-owner bypass class is OPEN at the writer")
        c.execute("""SELECT description FROM holes_findings
                     WHERE routine_name='ingestion_fidelity_gate'
                       AND hole_type='unresolved_doc_owner' AND doc_id=%s AND matter_code=%s
                       AND status='open'""", (orphan, matter))
        hold = c.fetchone()
        if not hold:
            raise TruthFailure(f"unresolved-owner refusal for doc {orphan} left NO visible hold — "
                               "silent refusal violates degrade-don't-crash")
        print(f"      [bite] {hold['description'][:160]}…")
        # control — resolvable owner, same text: facts must flow
        client = _real_client(c)
        ok_doc = _mk_doc(c, client, LONG_TEXT)
        c.execute("INSERT INTO document_matter_links (doc_id, matter_code) VALUES (%s,%s)",
                  (ok_doc, matter))
        harvest_facts.harvest_matter(c, matter, go=True)
        c.execute("SELECT count(*) AS n FROM matter_facts WHERE matter_code=%s AND source_id=%s",
                  (matter, str(ok_doc)))
        if c.fetchone()["n"] == 0:
            raise TruthFailure("control failed: resolvable-owner doc produced no facts — "
                               "the gate is blanket-refusing instead of discriminating")
    finally:
        conn.rollback(); c.close(); conn.close()


def verify_worker_holds_unresolved_owner(cur):
    """A77(1) negative: verify_worker HOLDS an unresolved-owner doc BEFORE spending inference —
    no edge, a visible hold, and a held_unresolved_owner attempt log (cooldown honored)."""
    import verify_worker
    conn, c = _txn()
    try:
        matter = "TT-A77-OWNERGATE"
        orphan = _mk_doc(c, None, LONG_TEXT)  # > 200 chars, owner unresolvable
        r = verify_worker.process_doc(c, {"id": orphan, "matter_code": matter}, go=True)
        if "HELD" not in (r.get("skip") or ""):
            raise TruthFailure(f"verify_worker did not hold the unresolved-owner doc: {r}")
        c.execute("SELECT status FROM verify_worker_log WHERE doc_id=%s "
                  "ORDER BY attempted_at DESC LIMIT 1", (orphan,))
        log = c.fetchone()
        if not log or log["status"] != "held_unresolved_owner":
            raise TruthFailure(f"held read was not attempt-logged (cooldown would re-spin): {log}")
        c.execute("""SELECT 1 FROM holes_findings WHERE routine_name='ingestion_fidelity_gate'
                       AND hole_type='unresolved_doc_owner' AND doc_id=%s AND status='open'""",
                  (orphan,))
        if not c.fetchone():
            raise TruthFailure("verify_worker hold left no visible holes_findings record")
        print(f"      [bite] {r['skip']}")
    finally:
        conn.rollback(); c.close(); conn.close()


TESTS = [
    ("A77 low-confidence bind is held + auditable (sink)", low_confidence_bind_held),
    ("A77 harvest refuses unresolved-owner doc (no edge, visible hold)", harvest_refuses_unresolved_owner),
    ("A77 verify_worker holds unresolved-owner doc pre-inference", verify_worker_holds_unresolved_owner),
]

if __name__ == "__main__":
    passed, failed = run(TESTS)
    sys.exit(1 if failed else 0)
