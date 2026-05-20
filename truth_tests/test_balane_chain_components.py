#!/usr/bin/env python3
"""test_balane_chain_components.py — Void-chain edges + subdivision-plan link.

Initial (2026-05-21 sign-off):
  - title_chain edge T-52540 → 079-2021002127 exists, linked to Psd-05-026197
    via subdivision_plan_id (deploy_220 backfill).
  - The plan row Psd-05-026197 has parent_title='T-52540' AND
    '079-2021002127' is in child_titles.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import assert_eq, assert_truthy, assert_row_exists, run


def balane_chain_edge_exists(cur):
    r = assert_row_exists(
        cur,
        "title_chain edge T-52540 → 079-2021002127 must exist",
        """SELECT subdivision_plan_id, provenance_level FROM title_chain
            WHERE parent_title = 'T-52540' AND child_title = '079-2021002127'""",
    )
    assert_truthy("Balane edge.subdivision_plan_id is set", r["subdivision_plan_id"])


def balane_plan_ref_is_psd_05_026197(cur):
    r = assert_row_exists(
        cur,
        "Balane edge's plan must be Psd-05-026197",
        """SELECT sp.normalized_ref, sp.parent_title, sp.child_titles
             FROM title_chain tc
             JOIN subdivision_plans sp ON sp.id = tc.subdivision_plan_id
            WHERE tc.parent_title = 'T-52540' AND tc.child_title = '079-2021002127'""",
    )
    assert_eq("Balane plan normalized_ref", r["normalized_ref"], "Psd-05-026197")
    assert_eq("Balane plan parent_title", r["parent_title"], "T-52540")
    assert_truthy("'079-2021002127' in child_titles",
                  "079-2021002127" in (r["child_titles"] or []))


TESTS = [
    ("balane.chain_edge_exists", balane_chain_edge_exists),
    ("balane.plan_psd_05_026197", balane_plan_ref_is_psd_05_026197),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
