"""_harness.py — Tiny test harness for truth_tests.

Each test file imports `assert_*` helpers and the `run` driver. Tests are
assertions about the bulletproof data layer. They run pre-deploy and nightly.

Failure = potential corruption. Exit non-zero.

Per design Q7: full suite on every deploy.
"""
import os
import sys
import traceback

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


class TruthFailure(AssertionError):
    """Raised when a truth assertion fails."""


def get_cursor():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def query_one(cur, sql, *params):
    # Only pass params if non-empty — otherwise psycopg2 misreads '%' chars
    # in SQL (e.g. inside LIKE patterns) as parameter placeholders.
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    return cur.fetchone()


def query_all(cur, sql, *params):
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    return cur.fetchall()


def assert_eq(label, actual, expected):
    if actual != expected:
        raise TruthFailure(f"{label}: expected {expected!r}, got {actual!r}")


def assert_in(label, value, allowed_set):
    if value not in allowed_set:
        raise TruthFailure(f"{label}: value {value!r} not in {allowed_set}")


def assert_truthy(label, value):
    if not value:
        raise TruthFailure(f"{label}: expected truthy, got {value!r}")


def assert_row_exists(cur, label, sql, *params):
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    r = cur.fetchone()
    if not r:
        raise TruthFailure(f"{label}: no row found for query: {sql} {params}")
    return r


def run(tests):
    """Run a list of (label, callable) tests. Returns (passed, failed)."""
    conn, cur = get_cursor()
    passed = []
    failed = []
    try:
        for label, fn in tests:
            try:
                fn(cur)
                passed.append(label)
                print(f"  ✓ {label}")
            except TruthFailure as e:
                failed.append((label, str(e)))
                print(f"  ✗ {label}: {e}")
            except Exception as e:
                failed.append((label, f"{type(e).__name__}: {e}"))
                print(f"  ✗ {label}: {type(e).__name__}: {e}")
                if os.environ.get("TRUTH_TESTS_VERBOSE"):
                    traceback.print_exc()
    finally:
        cur.close()
        conn.close()
    return passed, failed
