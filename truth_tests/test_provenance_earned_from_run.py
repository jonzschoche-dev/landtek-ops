#!/usr/bin/env python3
"""test_provenance_earned_from_run.py — A42 mechanical guard: provenance is EARNED, never fabricated.

ONTOLOGY §2.17 / A42: `documents.model_used` is the earned provenance stamp — set ONLY from a real
`extraction_runs` record, never written to make a doc "look connected." `test_connected_document_count.py`
already guards A41 (a stamped doc must clear all 5 signals); this guards the complementary A42 property:
every stamp must TRACE to a completed extraction_runs row. Together they close both failure modes —
stamping a half-connected doc (A41) and stamping with no real run at all (A42).

This is the corpus-wide, deploy+nightly-gated form of the candidate "V8" shadow validator: it catches any
write path (present or future) that sets `model_used` without an extraction_runs backing. Deterministic,
read-only, creditless. Verified 2026-07-08: 86 stamped · 86 backed by a run · 0 fabricated.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure


def provenance_traces_to_extraction_run(cur):
    """Every documents.model_used must have a matching extraction_runs(status='completed', model set) row."""
    cur.execute("""
        SELECT d.id FROM documents d
        WHERE d.model_used IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM extraction_runs er
                          WHERE er.doc_id = d.id AND er.status = 'completed' AND coalesce(er.model,'') <> '')
        ORDER BY d.id LIMIT 25""")
    bad = [r["id"] for r in cur.fetchall()]
    if bad:
        raise TruthFailure(
            f"{len(bad)} document(s) carry a `model_used` provenance stamp with NO completed `extraction_runs` "
            f"row — fabricated provenance (A42 / §2.17 violation): docs {bad}. `model_used` must be EARNED from "
            f"a real extraction run (heightened_ocr or the reocr_gemini atomic accept), never asserted to pass "
            f"the gate. Find the write path that set it and route it through extraction_runs.")


def provenance_count_reported(cur):
    """Surface the earned-provenance count each run (visibility; only fails if the corpus can't be read)."""
    cur.execute("SELECT count(*) AS earned FROM documents WHERE model_used IS NOT NULL")
    r = cur.fetchone()
    if r is None:
        raise TruthFailure("provenance count query returned no rows — schema/read problem")
    print(f"      [provenance] {r['earned']} documents carry an earned model_used stamp (A42)")


TESTS = [
    ("provenance.earned_stamp_traces_to_run", provenance_traces_to_extraction_run),
    ("provenance.earned_count_reported", provenance_count_reported),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
