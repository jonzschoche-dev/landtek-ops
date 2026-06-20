#!/usr/bin/env python3
"""test_provenance_integrity.py — the standing audit for the provenance write-gate (Phase 0).

Filed 2026-06-20 after the knowledge layer was found to have no write discipline — inference could
be (and was) stored as a verified fact. These assertions guarantee the cure holds: every 'verified'
row in the knowledge layer must trace to a RESOLVING source document. If a future write slips an
uncited verified row in (or the gate is dropped), the deploy fails.

  verified facts   — must have source_kind=doc + a source_id that resolves to a real document
  verified parties — must have source_doc_id that resolves
  verified causes  — must have operative_doc_id that resolves

The gate (triggers in migrations/apply_provenance_gate.py) prevents new violations; this test
catches any that exist and documents the tier distribution.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, TruthFailure


def no_uncited_verified_facts(cur):
    cur.execute("""SELECT count(*) AS n FROM matter_facts f WHERE provenance_level='verified'
        AND (source_kind IS DISTINCT FROM 'doc' OR source_id IS NULL
             OR NOT EXISTS (SELECT 1 FROM documents d WHERE d.id::text = f.source_id))""")
    n = cur.fetchone()["n"]
    if n:
        raise TruthFailure(f"{n} 'verified' matter_facts have no resolving doc citation "
                           "(inference mislabelled as fact). Re-tier to operator/inferred.")


def no_uncited_verified_parties(cur):
    cur.execute("""SELECT count(*) AS n FROM matter_parties p WHERE provenance_level='verified'
        AND (source_doc_id IS NULL OR NOT EXISTS (SELECT 1 FROM documents d WHERE d.id = p.source_doc_id))""")
    n = cur.fetchone()["n"]
    if n:
        raise TruthFailure(f"{n} 'verified' matter_parties lack a resolving source_doc_id.")


def no_uncited_verified_causes(cur):
    cur.execute("""SELECT count(*) AS n FROM matter_causes c WHERE provenance_level='verified'
        AND (operative_doc_id IS NULL OR NOT EXISTS (SELECT 1 FROM documents d WHERE d.id = c.operative_doc_id))""")
    n = cur.fetchone()["n"]
    if n:
        raise TruthFailure(f"{n} 'verified' matter_causes lack a resolving operative_doc_id.")


def gate_is_installed(cur):
    cur.execute("""SELECT count(*) AS n FROM pg_trigger
                   WHERE tgname IN ('tg_prov_facts','tg_prov_parties','tg_prov_causes')""")
    if cur.fetchone()["n"] < 3:
        raise TruthFailure("provenance write-gate triggers missing — re-run migrations/apply_provenance_gate.py")


TESTS = [
    ("provenance.gate_installed", gate_is_installed),
    ("provenance.no_uncited_verified_facts", no_uncited_verified_facts),
    ("provenance.no_uncited_verified_parties", no_uncited_verified_parties),
    ("provenance.no_uncited_verified_causes", no_uncited_verified_causes),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
