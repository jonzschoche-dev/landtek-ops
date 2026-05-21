#!/usr/bin/env python3
"""test_locked_data_integrity.py — Lockdown invariants.

Tables with verification_lock + content_hash columns must satisfy:
  - Every row where verification_lock='hard' has content_hash IS NOT NULL.
  - Every row where verification_lock='hard' has locked_at IS NOT NULL.
  - Every row where verification_lock='hard' has locked_by IS NOT NULL.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, TruthFailure

LOCKED_TABLES = [
    "titles",
    "title_chain",
    "subdivision_plans",
    "instruments_on_title",
    "entities",
    "title_transfers",
]


def make_test(table):
    def fn(cur):
        cur.execute(f"""
            SELECT COUNT(*) FILTER (WHERE content_hash IS NULL) AS no_hash,
                   COUNT(*) FILTER (WHERE locked_at IS NULL) AS no_locked_at,
                   COUNT(*) FILTER (WHERE locked_by IS NULL) AS no_locked_by,
                   COUNT(*) AS total
              FROM {table}
             WHERE verification_lock = 'hard'
        """)
        r = cur.fetchone()
        problems = []
        if r["no_hash"] > 0:
            problems.append(f"{r['no_hash']} rows hard-locked but no content_hash")
        if r["no_locked_at"] > 0:
            problems.append(f"{r['no_locked_at']} rows hard-locked but no locked_at")
        if r["no_locked_by"] > 0:
            problems.append(f"{r['no_locked_by']} rows hard-locked but no locked_by")
        if problems:
            raise TruthFailure(f"{table} ({r['total']} hard-locked): " + "; ".join(problems))
    return fn


TESTS = [(f"locked.{t}.metadata_complete", make_test(t)) for t in LOCKED_TABLES]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
