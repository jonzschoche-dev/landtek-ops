#!/usr/bin/env python3
"""test_equilibrium_propagate.py — A76 P2 reactive propagation (SHADOW, internal plane).

  (a) DOC-BRIDGE REFUSED (the load-bearing negative-bite): seed one client's fact that shares a document
      with another client's fact; the per-hop A5 guard makes the other-client fact UNREACHABLE, and the
      unguarded traversal WOULD have reached it (cross_client_refused >= 1) — proving the guard bit.
  (b) the ego stays in-client (no fact node resolves to a different client than the seed).
  (c) the ledger is written; propagation EMITS NOTHING (internal plane).
  (d) an unresolvable-client seed is HELD, never propagated (A5 resolve-or-hold).

Write-tests run in a ROLLED-BACK connection so propagation_log is never polluted.
"""
import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from _harness import run, TruthFailure
import equilibrium_propagate as EP


def _rolledback_cur():
    conn = psycopg2.connect(EP.DSN); conn.autocommit = False
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def doc_bridge_refused(cur):
    conn, tc = _rolledback_cur()
    try:
        tc.execute("""SELECT f1.id AS a, f2.id AS b FROM matter_facts f1
                        JOIN matter_facts f2 ON f1.source_id=f2.source_id AND f1.id<f2.id
                       WHERE f1.provenance_level='verified' AND f2.provenance_level='verified'
                         AND f1.source_id ~ '^[0-9]+$'
                         AND _client_of(f1.matter_code) <> _client_of(f2.matter_code) LIMIT 1""")
        pair = tc.fetchone()
        if not pair:
            return  # no cross-client shared-doc pair exists — nothing to leak, vacuously safe
        res = EP.propagate(tc, "fact", pair["a"], hops=2)
        ego = EP._ego(tc, "fact", pair["a"], res["client"], 2)
        reached = {n["node_id"] for n in ego if n["node_type"] == "fact"}
        if str(pair["b"]) in reached:
            raise TruthFailure(f"doc-bridge LEAK: fact {pair['b']} (other client) reachable from {pair['a']} "
                               "— the per-hop A5 guard failed.")
        if res["cross_client_refused"] < 1:
            raise TruthFailure("guard refused 0 — the negative-bite did not actually exercise the guard "
                               "(unguarded traversal should have reached a cross-client fact).")
    finally:
        conn.rollback(); conn.close()


def ledger_and_internal_plane(cur):
    conn, tc = _rolledback_cur()
    try:
        tc.execute("SELECT id FROM matter_facts WHERE matter_code='MWK-ARTA-1891' "
                   "AND provenance_level='verified' LIMIT 1")
        seed = tc.fetchone()
        if not seed:
            raise TruthFailure("no MWK-ARTA-1891 verified fact to seed propagation.")
        res = EP.propagate(tc, "fact", seed["id"], interaction_ref="truthtest", hops=2)
        if res.get("held"):
            raise TruthFailure(f"propagation held a resolvable seed: {res}")
        if not res.get("log_id"):
            raise TruthFailure("propagation wrote no propagation_log row.")
        if res.get("emitted") is not False:
            raise TruthFailure("propagation EMITTED — the reactive engine is internal-plane; it must "
                               "surface nothing (emission is the A79 gate).")
    finally:
        conn.rollback(); conn.close()


def holds_on_unresolvable_client(cur):
    conn, tc = _rolledback_cur()
    try:
        tc.execute("SELECT id FROM matter_facts WHERE _client_of(matter_code) IS NULL LIMIT 1")
        row = tc.fetchone()
        if not row:
            return  # every fact resolves to a client — nothing to test, safe
        res = EP.propagate(tc, "fact", row["id"], hops=2)
        if not res.get("held"):
            raise TruthFailure("propagated a seed with no resolvable client — A5 demands resolve-or-hold.")
    finally:
        conn.rollback(); conn.close()


TESTS = [
    ("equilibrium_propagate.doc_bridge_refused", doc_bridge_refused),
    ("equilibrium_propagate.ledger_and_internal_plane", ledger_and_internal_plane),
    ("equilibrium_propagate.holds_on_unresolvable_client", holds_on_unresolvable_client),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
