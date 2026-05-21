#!/usr/bin/env python3
"""test_torralba_linkage.py — Princess Balane Torralba IS the Balane↔Torralba bridge.

Filed 2026-05-21 after Jonathan corrected my misclassification of the
Torralba CA petition as "unrelated precedent" (it's Balane family litigation).
This test prevents the regression.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import assert_eq, assert_row_exists, assert_truthy, run


def princess_balane_torralba_hub_exists(cur):
    r = assert_row_exists(
        cur, "entity #2391 Princess Balane Torralba must remain canonical",
        "SELECT canonical_name FROM entities WHERE id = 2391"
    )
    assert_truthy("#2391.canonical_name contains 'Balane' AND 'Torralba'",
                  "Balane" in r["canonical_name"] and "Torralba" in r["canonical_name"])


def torralba_docs_attached_to_balane_matter(cur):
    cur.execute("""
        SELECT id, matter_code FROM documents
         WHERE id IN (581, 582, 583, 585)
         ORDER BY id
    """)
    rows = cur.fetchall()
    if len(rows) != 4:
        from _harness import TruthFailure
        raise TruthFailure(f"expected 4 Torralba docs, found {len(rows)}")
    for r in rows:
        if r["matter_code"] != "MWK-CV26360":
            from _harness import TruthFailure
            raise TruthFailure(
                f"doc#{r['id']} matter_code={r['matter_code']!r}; "
                f"expected MWK-CV26360 (Torralba is Balane-family litigation — "
                f"see memory/feedback_torralba_balane_linkage.md)")


TESTS = [
    ("torralba.princess_balane_torralba_hub_exists", princess_balane_torralba_hub_exists),
    ("torralba.docs_581_582_583_585_in_cv26360", torralba_docs_attached_to_balane_matter),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
