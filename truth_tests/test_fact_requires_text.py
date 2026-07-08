#!/usr/bin/env python3
"""test_fact_requires_text.py — corpus-wide mechanical assertion for A48 (ONTOLOGY §2.17 / §4).

**What A48 requires.** A `Fact`/`Relationship` in the semantic layer must cite a **source document with a
usable `text` signal** (`text_length >= 50`) — knowledge is never extracted from a textless document. This is
the true signal→semantic dependency: TEXT is what rises to a citable fact. (The verbatim-`excerpt` rule for
the `verified` tier is separately enforced by `enforce_provenance_facts`, A2/A20.)

**Why it is the `text` signal and NOT the full ConnectivityGate.** The draft A48 said "a Fact may be extracted
only from a *ConnectedDocument* (all 5 signals)." That was FALSIFIED against the live corpus (2026-07-08):
`matter_facts` trace to 971 distinct source docs, of which only **84** are fully connected — 887 are not. Even
scoping the prerequisite to the `verified` tier was too strong (only **13** of 484 verified-fact source docs are
fully connected). The one factor true at every tier: **every fact-source doc has usable text** (899/899
inferred_strong, 484/484 verified, 3/3 operator). So connectivity (A41) governs a document's *completeness*; it
is not a prerequisite for extracting a cited fact — text is. Graduating the draft A48 as-is would have declared
887 docs' worth of knowledge un-citable. This test asserts the correct, grounded invariant.

Deterministic, read-only, creditless. Only counts numeric `source_id` (a document id).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure


def fact_source_has_text(cur):
    """A48: every matter_facts row citing a document must cite one with a usable text signal (>=50 chars)."""
    cur.execute("""
        SELECT f.id, f.source_id
        FROM matter_facts f
        JOIN documents d ON d.id = f.source_id::int
        WHERE f.source_id ~ '^[0-9]+$'
          AND coalesce(length(d.extracted_text), 0) < 50
        ORDER BY f.id LIMIT 25""")
    bad = cur.fetchall()
    if bad:
        raise TruthFailure(
            f"{len(bad)} fact(s) cite a source document with NO usable text (<50 chars) — knowledge extracted "
            f"from a textless doc (A48 / §2.17): fact ids {[r['id'] for r in bad]}. A fact must rise from a "
            f"document that actually has text; re-OCR the source or re-tier the fact.")


def fact_text_coverage_reported(cur):
    """Non-threshold visibility: surface how fact-source docs split by connectivity (the A48 grounding)."""
    cur.execute("""
        SELECT count(DISTINCT source_id) AS fact_source_docs
        FROM matter_facts WHERE source_id ~ '^[0-9]+$'""")
    r = cur.fetchone()
    if r is None or r["fact_source_docs"] is None:
        raise TruthFailure("fact-source-doc query returned no rows — schema/read problem")
    print(f"      [A48] facts cite {r['fact_source_docs']} distinct source docs — each must have usable text "
          f"(connectivity is NOT required to cite a fact)")


TESTS = [
    ("semantic.fact_requires_text_signal", fact_source_has_text),
    ("semantic.fact_text_coverage_reported", fact_text_coverage_reported),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
