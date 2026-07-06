#!/usr/bin/env python3
"""test_superseded_tables_empty.py — lock the SUPERSEDED tables at empty (deploy_729/730).

ONTOLOGY §3 names tables that were superseded by a canonical successor but not dropped
(kept for lineage). Each must stay EMPTY — the successor holds the live data. A row
appearing here means a writer regressed to the old table (drift), which silently splits
the source of truth.

  audit_log        -> truth_audit_log   (successor has 2360 rows; 3 worker/ scripts still
                                          reference the old table — currently 0 rows, so the
                                          write path is dead/swallowed. This assertion turns
                                          RED the moment one of them actually writes.)
  audit_events     -> truth_audit_log
  document_entities-> doc_entities       (successor has 8928 rows)

Deterministic + creditless. This is the SAFE half of the Tier-2 audit_log item: it detects
drift without a write-block. Adding these to ontology_validator V1 (block-at-write) is the
other half — it needs the 3 protected worker/ writers migrated first (flagged, human-gated).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure

# superseded table -> its canonical successor (for the failure message)
SUPERSEDED = {
    "audit_log": "truth_audit_log",
    "audit_events": "truth_audit_log",
    "document_entities": "doc_entities",
}


def _empty(table, successor):
    def check(cur):
        cur.execute(f"SELECT count(*) AS n FROM {table}")
        n = cur.fetchone()["n"]
        if n:
            raise TruthFailure(
                f"{table} has {n} row(s) — it is SUPERSEDED by {successor} (ONTOLOGY §3) and must "
                f"stay empty. A writer regressed to the old table, splitting the source of truth. "
                f"Redirect the write to {successor} (find it: grep -rn 'INSERT INTO {table}' scripts worker).")
    return check


TESTS = [(f"superseded.{t}_stays_empty", _empty(t, s)) for t, s in SUPERSEDED.items()]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
