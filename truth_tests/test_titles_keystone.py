#!/usr/bin/env python3
"""test_titles_keystone.py — User-confirmed facts about the keystone titles.

Initial assertions (2026-05-21 sign-off):
  - T-4497 registrant_canonical = 'HEIRS OF MARY WORRICK KEESEY'
  - T-4497 lifecycle_status = 'contested'

Additional facts must be user-confirmed before being added here.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import assert_eq, assert_row_exists, run


def t4497_registrant(cur):
    r = assert_row_exists(
        cur, "T-4497 must exist in titles",
        "SELECT registrant_canonical, lifecycle_status FROM titles WHERE tct_number = %s",
        "T-4497",
    )
    assert_eq("T-4497.registrant_canonical", r["registrant_canonical"],
              "HEIRS OF MARY WORRICK KEESEY")


def t4497_lifecycle(cur):
    r = assert_row_exists(
        cur, "T-4497 must exist", "SELECT lifecycle_status FROM titles WHERE tct_number = %s",
        "T-4497",
    )
    assert_eq("T-4497.lifecycle_status", r["lifecycle_status"], "contested")


TESTS = [
    ("titles.T-4497.registrant_canonical", t4497_registrant),
    ("titles.T-4497.lifecycle_status", t4497_lifecycle),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
