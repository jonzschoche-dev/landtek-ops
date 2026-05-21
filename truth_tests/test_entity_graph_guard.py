#!/usr/bin/env python3
"""test_entity_graph_guard.py — guard contract assertions.

The deploy_252 entity-graph guard downgrades flag_unrelated proposals to
needs_manual_review when the doc's own entities overlap with the client's
keystone/transferee graph. This test pins two things:

  1. The doc_classification_proposals.status check constraint allows
     'needs_manual_review' (deploy_252's status target).
  2. At least one proposal currently has status='needs_manual_review' AND
     review_notes referencing 'entity_graph_guard' — proof that the guard
     has run and the platform-level cross-check is alive.

If the guard's review_notes pattern changes, update this test alongside
the guard.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import assert_truthy, run, TruthFailure


def status_check_allows_needs_manual_review(cur):
    """The status CHECK constraint must permit the new value."""
    cur.execute("""
        SELECT pg_get_constraintdef(oid) AS def
          FROM pg_constraint
         WHERE conname = 'doc_classification_proposals_status_check'
    """)
    r = cur.fetchone()
    if not r:
        raise TruthFailure("doc_classification_proposals_status_check constraint missing")
    if "needs_manual_review" not in (r["def"] or ""):
        raise TruthFailure(
            f"status_check_constraint does not include 'needs_manual_review': {r['def']}"
        )


def guard_has_run_at_least_once(cur):
    """Verifies the guard has fingerprints in the proposals table at any status.
    Earlier the test required status='needs_manual_review' but deploy_260 legitimately
    consumes those into 'applied' — the guard's run is recorded in review_notes /
    reviewed_by regardless of final status. The fingerprint is what matters."""
    cur.execute("""
        SELECT COUNT(*) AS n FROM doc_classification_proposals
         WHERE (reviewed_by IN ('entity_graph_guard', 'entity_graph_guard_text')
                OR review_notes ILIKE %s)
    """, ("%entity_graph_guard%",))
    n = cur.fetchone()["n"]
    if n < 1:
        raise TruthFailure(
            "no proposals carry entity_graph_guard fingerprint in any state; "
            "either the guard never ran, or all its records were destroyed"
        )


TESTS = [
    ("guard.status_check_allows_needs_manual_review", status_check_allows_needs_manual_review),
    ("guard.has_run_at_least_once", guard_has_run_at_least_once),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
