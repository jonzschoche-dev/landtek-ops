#!/usr/bin/env python3
"""test_leo_service_spine.py — the headless Leo reply loop, end-to-end (COMM-AGENT-MAX T3).

Asserts the governed spine holds:
  (a) no reply ships with a FAIL verdict — a gate fail is always remediated before it becomes would_send.
  (b) a fabricated-cite / ungrounded-cascade reply is CAUGHT and remediated (negative-tested to bite).
  (c) an unresolved sender is HELD, never answered with a guessed client's context (A25).
  (d) client-isolation: a client's grounding never pulls a different client's facts (A5).
All read-only (gate/remediate/client_of only SELECT); no live send anywhere (the service is shadow-only).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/root/landtek/scripts")
sys.path.insert(0, "/root/landtek")
from _harness import run, TruthFailure

from leo_answer_gate import gate, remediate          # the answer-gate under test
from platform_coordinator import client_of           # A25 resolve-or-hold


def ledger_present(cur):
    cur.execute("SELECT to_regclass('public.leo_shadow_replies') AS t")
    if not cur.fetchone()["t"]:
        raise TruthFailure("leo_shadow_replies missing — the shadow surface must exist (deploy leo_shadow_replies).")


def no_fail_ships_unremediated(cur):
    """Every shadow-logged reply with a FAIL verdict must have been remediated ($0 grounded-only)."""
    cur.execute("""SELECT count(*) AS n FROM leo_shadow_replies
                   WHERE action='shadow_logged' AND verdict='fail' AND remediated IS NOT TRUE""")
    n = cur.fetchone()["n"]
    if n:
        raise TruthFailure(f"{n} shadow reply(ies) had a FAIL verdict but were NOT remediated — an "
                           "ungrounded reply reached would_send. Every fail must go through remediate().")


def fabricated_cite_caught_and_remediated(cur):
    """Negative test — the gate must BITE on a fabricated cite + ungrounded cascade, and remediate must strip it."""
    bad = ("Good news — the court already ruled entirely in our favor, see doc:99999999, and this "
           "cascades to cancel all derivative titles automatically.")
    res = gate(cur, bad)
    if res["verdict"] != "fail":
        raise TruthFailure("gate did NOT fail a reply citing a non-existent doc:99999999 + an ungrounded "
                           "cascade — the answer-gate does not bite; fabrications would ship.")
    fixed = remediate(cur, bad, res)
    if "99999999" in fixed or "doc:99999999" in fixed:
        raise TruthFailure("remediate() left the fabricated citation in the reply — grounded-only rewrite failed.")


def grounded_reply_passes(cur):
    """A safe, non-asserting reply must PASS (no false positives that would block real answers)."""
    good = "Salamat sa mensahe! I'll check with the team and follow up with you shortly."
    if gate(cur, good)["verdict"] != "pass":
        raise TruthFailure("gate FAILED a clean, non-factual reply — false positive would block real answers.")


def unresolved_sender_held(cur):
    """An identity not bound to any client resolves to None → the service HOLDS (never answers, A25)."""
    if client_of(cur, "messenger", "NO_SUCH_STRANGER_ID_000") is not None:
        raise TruthFailure("client_of resolved an unknown identity to a client — a stranger would be "
                           "answered with a guessed client's context (A25 violation).")


def client_isolation_scope(cur):
    """A5: the client-family grounding scope must never contain a fact owned by a different client."""
    cur.execute("""SELECT count(*) AS n FROM matter_facts mf
                    WHERE mf.matter_code LIKE 'MWK%'
                      AND mf.matter_code IN (SELECT matter_code FROM matters
                                              WHERE client_code IS NOT NULL AND client_code NOT LIKE 'MWK%')""")
    n = cur.fetchone()["n"]
    if n:
        raise TruthFailure(f"{n} fact(s) in the MWK grounding scope belong to a NON-MWK client — "
                           "client A's reply could pull client B's context (A5 leak).")


TESTS = [
    ("leo_spine.ledger_present", ledger_present),
    ("leo_spine.no_fail_ships_unremediated", no_fail_ships_unremediated),
    ("leo_spine.fabricated_cite_caught_and_remediated", fabricated_cite_caught_and_remediated),
    ("leo_spine.grounded_reply_passes", grounded_reply_passes),
    ("leo_spine.unresolved_sender_held", unresolved_sender_held),
    ("leo_spine.client_isolation_scope", client_isolation_scope),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
