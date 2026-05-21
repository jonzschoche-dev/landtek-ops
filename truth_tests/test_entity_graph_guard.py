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
        SELECT consrc
          FROM pg_constraint
         WHERE conname = 'doc_classification_proposals_status_check'
    """)
    # Postgres ≥12 doesn't have consrc; use pg_get_constraintdef instead.
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
    cur.execute("""
        SELECT COUNT(*) AS n FROM doc_classification_proposals
         WHERE status = 'needs_manual_review'
           AND reviewed_by = 'entity_graph_guard'
           AND review_notes ILIKE %s
    """, ("%entity_graph_guard%",))
    n = cur.fetchone()["n"]
    if n < 1:
        raise TruthFailure(
            "no proposals have status='needs_manual_review' from entity_graph_guard; "
            "either the guard never ran or its output was reverted"
        )


TESTS = [
    ("guard.status_check_allows_needs_manual_review", status_check_allows_needs_manual_review),
    ("guard.has_run_at_least_once", guard_has_run_at_least_once),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
