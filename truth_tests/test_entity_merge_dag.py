#!/usr/bin/env python3
"""test_entity_merge_dag.py — lock invariant A15: the entity merge graph is a DAG (deploy_732).

`entities.canonical_id` is the merge graph — a duplicate entity points at its canonical head. Following
`canonical_id` must always TERMINATE at a head (NULL / self), never loop. A cycle (A→B→A) means
resolution never converges, and "which entity is canonical?" becomes undefined — silently corrupting every
join that resolves through the merge graph (doc_entities, matter_facts party links, client isolation).

Two mechanical assertions, both creditless:
  1. acyclic     — no entity is reachable from itself by following canonical_id (the A15 invariant).
  2. no_dangling — every merge edge resolves to an EXISTING canonical head (integrity companion).

Verified 2026-07-06: 9 merge edges, all depth-1, 0 cycles, 0 dangling — this locks that clean state so a
future merge/consolidation can't introduce a cycle or a dangling head without turning the deploy gate red.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure


def canonical_id_acyclic(cur):
    """No entity may be reachable from itself by following canonical_id (A15)."""
    cur.execute("""
        WITH RECURSIVE walk(start_id, cur_id, depth, path, cycle) AS (
            SELECT id, canonical_id, 1, ARRAY[id], false
            FROM entities WHERE canonical_id IS NOT NULL AND canonical_id <> id
          UNION ALL
            SELECT w.start_id, e.canonical_id, w.depth + 1, w.path || e.id, e.id = ANY(w.path)
            FROM walk w JOIN entities e ON e.id = w.cur_id
            WHERE NOT w.cycle AND e.canonical_id IS NOT NULL AND e.canonical_id <> e.id AND w.depth < 100
        )
        SELECT DISTINCT start_id FROM walk WHERE cycle ORDER BY start_id LIMIT 20""")
    bad = [r["start_id"] for r in cur.fetchall()]
    if bad:
        raise TruthFailure(
            f"entities.canonical_id has a MERGE CYCLE reachable from entity id(s) {bad}: following "
            f"canonical_id loops instead of terminating at a canonical head (A15). Resolution can never "
            f"converge. Break it — pick one head and repoint the others' canonical_id to it.")


def canonical_id_no_dangling(cur):
    """Every merge edge must resolve to an existing canonical head (A15 integrity companion)."""
    cur.execute("""
        SELECT e.id, e.canonical_id FROM entities e
        WHERE e.canonical_id IS NOT NULL AND e.canonical_id <> e.id
          AND NOT EXISTS (SELECT 1 FROM entities h WHERE h.id = e.canonical_id)
        ORDER BY e.id LIMIT 20""")
    bad = cur.fetchall()
    if bad:
        rows = ", ".join(f"#{r['id']}->#{r['canonical_id']}" for r in bad)
        raise TruthFailure(
            f"{len(bad)} entity(ies) have a DANGLING canonical_id (points to a missing entity): {rows}. "
            f"A merge edge must resolve to an existing canonical head (A15).")


TESTS = [
    ("entities.canonical_id_acyclic", canonical_id_acyclic),
    ("entities.canonical_id_no_dangling", canonical_id_no_dangling),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
