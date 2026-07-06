#!/usr/bin/env python3
"""test_separate_matters.py — mechanical guard for the "stay separate" invariants that
the retired LLM truth_qa harness used to check by interrogating Leo (removed deploy_725).

CLAUDE.md "Critical do-nots":
  - T-30683 (Manguisoc Mercedes) and T-4494 (Cabanbanan San Vicente) are SEPARATE
    properties — NOT derivatives of T-4497; treat as their own matters.
  - MMK != MWK — never conflate Mary Worrick Keesey with MMK.

The risk is real, not theoretical: deploy_136 auto-promoted over-broad OCT-field
"derivative" edges (memory: title-chain-oct-field-overbroad-edges). These assertions
lock the current-correct state (verified 2026-07-06: 0 direct edges, 0 descendants,
0 MMK entities) so a future auto-promotion can't silently pull a separate matter into
the T-4497 chain, and an extraction can't merge MMK into MWK, without turning the deploy
gate red. Deterministic + creditless — the doctrine replacement for the LLM harness.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure


def no_direct_4497_edge(cur):
    """No title_chain edge may make a separate matter a DIRECT derivative of T-4497."""
    cur.execute("""SELECT parent_title, child_title FROM title_chain
                   WHERE parent_title ~ '4497' AND child_title ~ '30683|4494'""")
    bad = cur.fetchall()
    if bad:
        rows = ", ".join(f"{r['parent_title']}->{r['child_title']}" for r in bad)
        raise TruthFailure(
            f"{len(bad)} title_chain edge(s) make a SEPARATE matter a direct derivative of "
            f"T-4497: {rows}. T-30683 (Manguisoc) / T-4494 (Cabanbanan) are separate properties "
            f"(CLAUDE.md). Delete the edge — likely a deploy_136-style over-promotion.")


def not_4497_descendant(cur):
    """Recursive: no separate-matter title may be REACHABLE as a descendant of T-4497."""
    cur.execute("""
        WITH RECURSIVE d AS (
            SELECT child_title FROM title_chain WHERE parent_title ~ '^T-?4497'
            UNION
            SELECT tc.child_title FROM title_chain tc JOIN d ON tc.parent_title = d.child_title
        )
        SELECT array_agg(DISTINCT child_title) AS hits FROM d WHERE child_title ~ '30683|4494'""")
    row = cur.fetchone()
    hits = row["hits"] if row else None
    if hits:
        raise TruthFailure(
            f"separate matter(s) {hits} are reachable as descendants of T-4497 in title_chain — "
            f"they must stay separate (Manguisoc / Cabanbanan are own matters, not the Keesey chain). "
            f"Sever the contaminating edge.")


def no_mmk_mwk_conflation(cur):
    """MMK != MWK: no single entity may carry BOTH an MMK token and an MWK/Worrick token."""
    cur.execute("""
        SELECT id, canonical_name FROM entities
        WHERE (canonical_name || ' ' || array_to_string(coalesce(aliases, ARRAY[]::text[]), ' ')) ~* '\\mMMK\\M'
          AND (canonical_name || ' ' || array_to_string(coalesce(aliases, ARRAY[]::text[]), ' ')) ~* '\\mMWK\\M|worrick'""")
    bad = cur.fetchall()
    if bad:
        rows = ", ".join(f"#{r['id']} {r['canonical_name']}" for r in bad)
        raise TruthFailure(
            f"{len(bad)} entity conflates MMK with MWK/Worrick (the MMK != MWK invariant): {rows}. "
            f"Split them — Mary Worrick Keesey is never MMK.")


TESTS = [
    ("separate_matter.t30683_t4494_no_direct_4497_edge", no_direct_4497_edge),
    ("separate_matter.t30683_t4494_not_4497_descendant", not_4497_descendant),
    ("entities.no_mmk_mwk_conflation", no_mmk_mwk_conflation),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
