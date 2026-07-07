#!/usr/bin/env python3
"""test_connected_document_count.py — corpus-wide mechanical assertion for A41 (ONTOLOGY §2.17).

**What A41 requires.** A `ConnectedDocument` satisfies ALL 5 ConnectivityGate signals — `extracted_text`
(≥50 chars) · `model_used` · `ocr_quality` · `corpus_backfill_state.embedded` · `document_type` — and a
half-connected doc is NEVER treated as fully connected / absorbed as evidence. `supervisor.py::_connect_verify`
enforces this at the OCR-remediation CHOKEPOINT, but nothing kept the invariant honest CORPUS-WIDE. This test
closes that gap so the 86/1579 stops being an anecdotal count and becomes a governed, failing assertion.

**Why the assertion is a CONSISTENCY invariant, not a count threshold.** A hardcoded `connected == 86` would
FAIL the moment the live layer connects doc #87 — it would punish progress. Instead we assert the property
that must hold at ANY count:

    `model_used` is the EARNED provenance stamp (ONTOLOGY §2.17 / A42) — the "this doc was fully processed"
    marker. Every doc that carries it MUST also clear the other 4 signals. A doc with `model_used` set but a
    missing signal is provenance stamped onto a half-connected doc = the exact A41 violation. Verified live
    2026-07-08: 86 stamped · 86 fully-connected · **0 inconsistent** (provenance is the binding constraint).

This stays green as connectivity GROWS and fails the instant a doc is marked processed without clearing the
gate (a fabricated or partial connection). The second check surfaces the live count on every run so the
number is always visible in the deploy + nightly output. Deterministic, read-only, creditless.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure

# The 5 ConnectivityGate signals, per document (mirrors supervisor.py::_connect_verify exactly).
_SIGNALS = """
  SELECT d.id,
    (coalesce(length(d.extracted_text), 0) >= 50)                                             AS txt,
    (d.model_used IS NOT NULL)                                                                AS prov,
    (d.document_type IS NOT NULL)                                                             AS typ,
    EXISTS (SELECT 1 FROM ocr_quality q WHERE q.doc_id = d.id)                                AS qual,
    EXISTS (SELECT 1 FROM corpus_backfill_state cb WHERE cb.doc_id = d.id AND cb.embedded IS TRUE) AS emb
  FROM documents d
"""


def provenance_implies_fully_connected(cur):
    """A41 (corpus-wide): every doc carrying an EARNED `model_used` stamp must clear all 5 gate signals."""
    cur.execute(f"""
        SELECT id FROM ({_SIGNALS}) s
        WHERE prov AND NOT (txt AND typ AND qual AND emb)
        ORDER BY id LIMIT 25""")
    bad = [r["id"] for r in cur.fetchall()]
    if bad:
        raise TruthFailure(
            f"{len(bad)} document(s) carry a `model_used` provenance stamp but FAIL a ConnectivityGate "
            f"signal — a half-connected doc treated as fully connected (A41 / §2.17): docs {bad}. Either a "
            f"deterministic signal (text/quality/embedded/document_type) was skipped, or `model_used` was "
            f"set without the doc clearing the gate. Re-run supervisor.py connect-verify on each.")


def connected_count_reported(cur):
    """Non-threshold visibility: surface the governed connected count on every run (never anecdotal again).
    Only fails if the query itself can't read the corpus — the number is a health signal, not a gate."""
    cur.execute(f"""
        SELECT count(*) AS total,
               count(*) FILTER (WHERE txt AND prov AND typ AND qual AND emb) AS connected
        FROM ({_SIGNALS}) s""")
    r = cur.fetchone()
    if r is None or r["total"] is None:
        raise TruthFailure("connectivity count query returned no rows — schema/read problem")
    print(f"      [connectivity] {r['connected']}/{r['total']} documents fully connected (all 5 signals)")


TESTS = [
    ("connectivity.provenance_implies_all_5_signals", provenance_implies_fully_connected),
    ("connectivity.connected_count_reported", connected_count_reported),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
