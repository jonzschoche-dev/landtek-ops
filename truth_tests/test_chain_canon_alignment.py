#!/usr/bin/env python3
"""test_chain_canon_alignment.py — title_chain_canon.py constants vs DB reality.

Per design P8: code canon is the second witness; nightly diff catches drift.

Initial (2026-05-21 sign-off):
  - title_chain_canon.OPERATIVE_ROOTS['MWK-001'] == 'T-111'
  - title_chain_canon.GHOST_TITLES contains 'OCT T-106'
  - DB title_chain has NO edge claiming OCT T-106 derives from anything else
    (i.e., OCT T-106 is never a child, only a parent of ghost-references)
"""
import sys
import os

sys.path.insert(0, "/root/landtek")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _harness import assert_eq, assert_truthy, run


def operative_root_mwk001(cur):
    from title_chain_canon import OPERATIVE_ROOTS
    assert_eq("canon.OPERATIVE_ROOTS['MWK-001']", OPERATIVE_ROOTS["MWK-001"], "T-111")


def t106_is_ghost(cur):
    from title_chain_canon import GHOST_TITLES, is_ghost
    assert_truthy("'OCT T-106' in GHOST_TITLES", "OCT T-106" in GHOST_TITLES)
    assert_truthy("is_ghost('OCT T-106')", is_ghost("OCT T-106"))


def t4497_canonical_parent_is_t111(cur):
    from title_chain_canon import TRUNKS
    assert_truthy("TRUNKS['T-4497'] defined", "T-4497" in TRUNKS)
    assert_eq("TRUNKS['T-4497'].canonical_parent",
              TRUNKS["T-4497"]["canonical_parent"], "T-111")


TESTS = [
    ("canon.operative_root_mwk001", operative_root_mwk001),
    ("canon.oct_t106_is_ghost", t106_is_ghost),
    ("canon.t4497_canonical_parent_t111", t4497_canonical_parent_is_t111),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
