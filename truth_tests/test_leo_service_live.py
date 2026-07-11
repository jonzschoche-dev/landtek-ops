#!/usr/bin/env python3
"""test_leo_service_live.py — the headless Leo LIVE cutover invariants (COMM-AGENT-MAX T4).

The shadow spine (test_leo_service_spine.py) proved the reasoning loop. This proves the LIVE gate:
  (a) no FAIL-verdict reply ships (a fail is always remediated first),
  (b) an ungrounded / fabricated-cite input is caught + remediated (negative-tested to bite),
  (c) an unresolved sender is HELD, never answered (A25),
  (d) client A's message never pulls client B's context (A5),
  (e) THE cutover guarantee — an OUTWARD (client) reply is HELD for human approval, never auto-sent:
      * no 'sent' row is outward-without-an-approval-order (live audit), AND
      * _send_decision on an unapproved outward move returns 'hold' + enqueues an outward_action
        (negative-tested on an isolated connection, rolled back).
"""
import json
import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/root/landtek/scripts")
sys.path.insert(0, "/root/landtek")
from _harness import run, TruthFailure, DSN

from leo_answer_gate import gate, remediate
from platform_coordinator import client_of
import leo_service


def switch_and_ledger_present(cur):
    for t in ("public.leo_channel_mode", "public.leo_shadow_replies"):
        cur.execute("SELECT to_regclass(%s) AS t", (t,))
        if not cur.fetchone()["t"]:
            raise TruthFailure(f"{t} missing — the cutover switch / shadow ledger must exist.")


def no_fail_ships(cur):
    cur.execute("""SELECT count(*) AS n FROM leo_shadow_replies
                   WHERE action IN ('sent','shadow_logged') AND verdict='fail' AND remediated IS NOT TRUE""")
    if cur.fetchone()["n"]:
        raise TruthFailure("a FAIL-verdict reply shipped/would-ship without remediation.")


def no_outward_sent_without_approval(cur):
    """THE A21 live guarantee: nothing outward was delivered without a human-approval order."""
    cur.execute("""SELECT count(*) AS n FROM leo_shadow_replies
                   WHERE action='sent' AND guard_class='outward' AND order_id IS NULL""")
    n = cur.fetchone()["n"]
    if n:
        raise TruthFailure(f"{n} OUTWARD reply(ies) were SENT with no approval order — a client was "
                           "messaged without human sign-off (A21 breach).")


def outward_held_without_approval_negative(cur):
    """Negative-bite: an unapproved outward move must HOLD + enqueue, never resolve to 'send'."""
    conn = psycopg2.connect(DSN); conn.autocommit = False
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # JJ's messenger identity classifies outward; a fresh reply has no approval
        decision, kind, oid = leo_service._send_decision(
            c, "messenger", "37446980471566856", "UNIQUE-UNAPPROVED-" + os.urandom(6).hex())
        if decision != "hold" or not oid:
            raise TruthFailure(f"an unapproved OUTWARD reply resolved to {decision!r} (order={oid}) — "
                               "it must HOLD and enqueue an outward_action for human certification.")
        c.execute("SELECT kind, status FROM work_orders WHERE id=%s", (oid,))
        w = c.fetchone()
        if not w or w["kind"] != "outward_action":
            raise TruthFailure("the held outward reply did not enqueue an outward_action work order.")
    finally:
        conn.rollback(); c.close(); conn.close()


def unresolved_sender_held(cur):
    if client_of(cur, "messenger", "NO_SUCH_STRANGER_ID_000") is not None:
        raise TruthFailure("client_of resolved an unknown identity — a stranger could be answered (A25).")


def fabricated_cite_caught(cur):
    bad = "Great news — the court ruled for us, see doc:99999999, cascading to void every derivative title."
    res = gate(cur, bad)
    if res["verdict"] != "fail":
        raise TruthFailure("gate did not fail a fabricated-cite + ungrounded-cascade reply.")
    if "99999999" in remediate(cur, bad, res):
        raise TruthFailure("remediate left the fabricated citation in the reply.")


def client_isolation_scope(cur):
    cur.execute("""SELECT count(*) AS n FROM matter_facts mf
                    WHERE mf.matter_code LIKE 'MWK%'
                      AND mf.matter_code IN (SELECT matter_code FROM matters
                                              WHERE client_code IS NOT NULL AND client_code NOT LIKE 'MWK%')""")
    if cur.fetchone()["n"]:
        raise TruthFailure("a non-MWK client's fact sits in the MWK grounding scope (A5 leak).")


TESTS = [
    ("leo_live.switch_and_ledger_present", switch_and_ledger_present),
    ("leo_live.no_fail_ships", no_fail_ships),
    ("leo_live.no_outward_sent_without_approval", no_outward_sent_without_approval),
    ("leo_live.outward_held_without_approval_negative", outward_held_without_approval_negative),
    ("leo_live.unresolved_sender_held", unresolved_sender_held),
    ("leo_live.fabricated_cite_caught", fabricated_cite_caught),
    ("leo_live.client_isolation_scope", client_isolation_scope),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
