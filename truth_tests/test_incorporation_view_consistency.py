#!/usr/bin/env python3
"""test_incorporation_view_consistency.py — the Phase-3 incorporation views MUST reconcile with A41.

`v_incorporation_status` / `v_doc_connectivity` (migrations/deploy_766) surface connectivity for operators
(scripts/incorporation_status.py, the nightly snapshot). If their 5-signal predicates ever drift from
truth_tests/test_connected_document_count.py (A41 / ONTOLOGY §2.17), the operator-facing numbers would
LIE while the gate stays green. This asserts the view's corpus-wide TOTAL row equals the A41 5-signal
count computed INDEPENDENTLY here — so the visibility layer can never silently diverge from the gate.
Deterministic, read-only, creditless. (Skips cleanly if the view isn't present yet.)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure

# Independent recomputation of the EXACT A41 signals (mirrors test_connected_document_count.py).
_A41 = """
  SELECT count(*) FILTER (WHERE txt AND prov AND typ AND qual AND emb) AS connected,
         count(*) FILTER (WHERE prov)                                  AS provenance,
         count(*)                                                      AS total
  FROM (
    SELECT (coalesce(length(d.extracted_text),0) >= 50) txt, (d.model_used IS NOT NULL) prov,
           (d.document_type IS NOT NULL) typ,
           EXISTS(SELECT 1 FROM ocr_quality q WHERE q.doc_id=d.id) qual,
           EXISTS(SELECT 1 FROM corpus_backfill_state c WHERE c.doc_id=d.id AND c.embedded IS TRUE) emb
    FROM documents d) s"""


def view_reconciles_with_a41(cur):
    """v_incorporation_status TOTAL row must equal the independently-computed A41 count."""
    cur.execute("SELECT to_regclass('public.v_incorporation_status') IS NOT NULL AS present")
    if not cur.fetchone()["present"]:
        print("      [incorporation] view not present yet (migration deploy_766 unapplied) — skipping")
        return
    cur.execute("SELECT connected, provenance_earned, total FROM v_incorporation_status WHERE is_total = 1")
    v = cur.fetchone()
    cur.execute(_A41)
    a = cur.fetchone()
    if (v["connected"], v["provenance_earned"], v["total"]) != (a["connected"], a["provenance"], a["total"]):
        raise TruthFailure(
            f"incorporation view DRIFTED from A41: view(connected={v['connected']}, prov={v['provenance_earned']}, "
            f"total={v['total']}) != A41(connected={a['connected']}, prov={a['provenance']}, total={a['total']}). "
            f"Operator-facing numbers would lie — realign v_doc_connectivity predicates with "
            f"truth_tests/test_connected_document_count.py.")
    print(f"      [incorporation] view reconciles with A41: {v['connected']}/{v['total']} connected, "
          f"{v['provenance_earned']} provenance")


TESTS = [
    ("incorporation.view_reconciles_with_a41", view_reconciles_with_a41),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
