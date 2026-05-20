#!/usr/bin/env python3
"""test_entities_keystone.py — Keystone entity assertions.

Initial (2026-05-21 sign-off):
  - Entity #1348 'Cesar de La Fuente' exists, provenance=verified, role mentions
    'deceased 2017-06-21'.
  - Entity for Patricia Keesey Zschoche exists with provenance verified.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import assert_eq, assert_row_exists, assert_truthy, run


def cesar_keystone_entity(cur):
    r = assert_row_exists(
        cur, "entity #1348 must exist",
        "SELECT canonical_name, provenance_level, role FROM entities WHERE id = 1348",
    )
    assert_eq("entity#1348.canonical_name", r["canonical_name"], "Cesar de La Fuente")
    assert_eq("entity#1348.provenance_level", r["provenance_level"], "verified")
    assert_truthy("entity#1348.role contains 'deceased 2017-06-21'",
                  r["role"] and "2017-06-21" in r["role"])


def patricia_entity_exists(cur):
    r = assert_row_exists(
        cur,
        "at least one verified Patricia Keesey entity must exist",
        "SELECT canonical_name FROM entities "
        "WHERE canonical_name ILIKE %s AND provenance_level = 'verified' LIMIT 1",
        "%Patricia%Keesey%",
    )


TESTS = [
    ("entities.#1348.cesar_keystone", cesar_keystone_entity),
    ("entities.patricia_keesey_exists", patricia_entity_exists),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
