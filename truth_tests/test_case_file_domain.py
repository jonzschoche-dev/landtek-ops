#!/usr/bin/env python3
"""test_case_file_domain.py — documents.case_file must live in the known domain.

Filed deploy_256 after the audit script (deploy_255) surfaced data-quality
drift in case_file. The recognized domain is:
  - Any case_file registered in case_theories._clients.CLIENTS
  - NULL (transitional; ok at ingest time)
  - 'unknown' / 'Unknown' / '' (ingest-transient; tolerated but trackable)

Anything else is platform corruption.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure
from case_theories._clients import CLIENTS

REGISTERED = {c["case_file"] for c in CLIENTS.values() if c.get("case_file")}
TOLERATED = {"unknown", "Unknown", ""}


def case_file_domain_invariant(cur):
    """No doc may carry a case_file outside the recognized domain."""
    cur.execute("""
        SELECT case_file, COUNT(*) AS n
          FROM documents
         WHERE case_file IS NOT NULL
         GROUP BY case_file
    """)
    bad = []
    for r in cur.fetchall():
        cf = r["case_file"]
        if cf in REGISTERED or cf in TOLERATED:
            continue
        bad.append((cf, r["n"]))
    if bad:
        raise TruthFailure(
            f"case_file values outside recognized domain "
            f"(REGISTERED={sorted(REGISTERED)} TOLERATED={sorted(TOLERATED)}): {bad}"
        )


def owner_case_file_recognized(cur):
    """'Owner' must be in the registered set (deploy_256 added it)."""
    if "Owner" not in REGISTERED:
        raise TruthFailure(
            f"'Owner' not in REGISTERED set ({sorted(REGISTERED)}). "
            "Deploy_256 was supposed to add OWNER to case_theories._clients."
        )


TESTS = [
    ("case_file_domain.owner_registered", owner_case_file_recognized),
    ("case_file_domain.no_unknown_values", case_file_domain_invariant),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
