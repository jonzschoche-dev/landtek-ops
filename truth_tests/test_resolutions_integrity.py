#!/usr/bin/env python3
"""test_resolutions_integrity.py — Resolutions table integrity.

  - Every resolutions.source_doc_id (if not NULL) must resolve to a real document.
  - Every resolutions.adjudicator_entity_id (if not NULL) must resolve to a real entity.
  - Every code in affected_matter_codes must exist in matters.
  - escalations.source_resolution_id (if not NULL) must resolve to a resolution.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, TruthFailure


def no_dangling_source_doc(cur):
    cur.execute("""
        SELECT id, source_doc_id FROM resolutions
         WHERE source_doc_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM documents d WHERE d.id = resolutions.source_doc_id)
    """)
    bad = cur.fetchall()
    if bad:
        raise TruthFailure(f"dangling source_doc_id refs: {[(r['id'], r['source_doc_id']) for r in bad]}")


def no_dangling_adjudicator(cur):
    cur.execute("""
        SELECT id, adjudicator_entity_id FROM resolutions
         WHERE adjudicator_entity_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM entities e WHERE e.id = resolutions.adjudicator_entity_id)
    """)
    bad = cur.fetchall()
    if bad:
        raise TruthFailure(f"dangling adjudicator_entity_id refs: {[(r['id'], r['adjudicator_entity_id']) for r in bad]}")


def affected_matters_valid(cur):
    cur.execute("""
        SELECT r.id, mc FROM resolutions r, UNNEST(r.affected_matter_codes) mc
         WHERE NOT EXISTS (SELECT 1 FROM matters m WHERE m.matter_code = mc)
    """)
    bad = cur.fetchall()
    if bad:
        raise TruthFailure(f"resolutions reference unknown matter_codes: {[(r['id'], r['mc']) for r in bad]}")


def escalations_resolve(cur):
    cur.execute("""
        SELECT id, source_resolution_id FROM escalations
         WHERE source_resolution_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM resolutions r WHERE r.id = escalations.source_resolution_id)
    """)
    bad = cur.fetchall()
    if bad:
        raise TruthFailure(f"escalations reference dead resolutions: {[(r['id'], r['source_resolution_id']) for r in bad]}")


TESTS = [
    ("resolutions.source_doc_fk", no_dangling_source_doc),
    ("resolutions.adjudicator_fk", no_dangling_adjudicator),
    ("resolutions.affected_matters_valid", affected_matters_valid),
    ("escalations.source_resolution_fk", escalations_resolve),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
