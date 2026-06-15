#!/usr/bin/env python3
"""test_cross_client_integrity.py — the "this can never happen again" guard.

Filed 2026-06-15 after Inocalla documents were found mis-filed under MWK and the deploy_258
entity consolidation had silently drifted back apart (operator: "it's the sign of a dumb
system"). These three assertions make the cross-client separation self-enforcing — if a
future ingest re-introduces conflation, the truth-test gate fails the deploy. The detection
logic lives in scripts/cross_client_sentinel.py; this test just asserts its findings are empty.

  1. canon_applied      — no documented alias entity (CANON_ALIAS_MERGES) is live again
                          (extraction re-spawned a consolidated entity -> run --apply-canon)
  2. no_cross_principal — no person is a DEFINING party in >1 real client (excl. allowlist);
                          a new one is either a true namesake or a mis-file -> human review
  3. no_misfile         — no document names >=2 distinct parties of one other real client and
                          zero of its own (the 513/525 Inocalla-under-MWK pattern)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from _harness import run, TruthFailure
import cross_client_sentinel as ccs


def canon_applied(cur):
    drift = ccs.drift_residual(cur)
    if drift:
        rows = ", ".join(f"#{a} \"{nm}\"->#{s}" for s, a, nm in drift)
        raise TruthFailure(
            f"entity-consolidation canon has drifted ({len(drift)} alias(es) live again): "
            f"{rows}. Run: python3 scripts/cross_client_sentinel.py --apply-canon")


def no_cross_principal(cur):
    bad = ccs.multi_defining_principals(cur)
    if bad:
        rows = ", ".join(f"#{eid} {nm} {clients}" for eid, nm, clients in bad)
        raise TruthFailure(
            f"{len(bad)} person(s) are defining parties in >1 client (conflation risk): {rows}. "
            f"If legitimate, add to CROSS_CLIENT_PRINCIPAL_ALLOWLIST in case_theories/_clients.py.")


def no_misfile(cur):
    cands = ccs.misfile_candidates(cur)
    if cands:
        rows = ", ".join(f"doc {c['doc_id']} ({c['current']}->{c['suggest']})" for c in cands)
        raise TruthFailure(
            f"{len(cands)} document(s) filed under a client whose parties belong to another: {rows}.")


TESTS = [
    ("cross_client.canon_applied", canon_applied),
    ("cross_client.no_cross_principal", no_cross_principal),
    ("cross_client.no_misfile", no_misfile),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
