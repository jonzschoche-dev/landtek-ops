#!/usr/bin/env python3
"""test_lockdown_infrastructure.py — Confirms deploy_221A triggers + audit log
are still installed and functional.

Detects:
  - Trigger drop (#16 in threat model)
  - Audit log permission drift
  - Event trigger drop (TRUNCATE protection)

Does NOT exercise behavior (verify_truth_lockdown.py does that with a test
fixture). This test just asserts the infrastructure objects exist.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import assert_eq, assert_truthy, query_all, run


CRITICAL_TABLES = [
    "titles", "title_chain", "subdivision_plans",
    "instruments_on_title", "entities", "title_transfers",
]


def triggers_installed(cur):
    rows = query_all(cur, """
        SELECT DISTINCT event_object_table, trigger_name
          FROM information_schema.triggers
         WHERE trigger_name LIKE 'tg_%_reject_locked'
            OR trigger_name LIKE 'tg_%_audit'
    """)
    seen = set((r["event_object_table"], r["trigger_name"]) for r in rows)
    for tbl in CRITICAL_TABLES:
        for suffix in ("reject_locked", "audit"):
            tg_name = f"tg_{tbl}_{suffix}"
            assert_truthy(f"trigger {tg_name} on {tbl}", (tbl, tg_name) in seen)


def event_trigger_installed(cur):
    rows = query_all(cur,
                     "SELECT evtname FROM pg_event_trigger WHERE evtname = 'block_truncate_critical'")
    assert_truthy("event trigger block_truncate_critical", len(rows) == 1)


def audit_log_append_only(cur):
    rows = query_all(cur, """
        SELECT grantee, privilege_type FROM information_schema.table_privileges
         WHERE table_name = 'truth_audit_log' AND grantee = 'n8n'
    """)
    privs = sorted(r["privilege_type"] for r in rows)
    assert_truthy("n8n has INSERT on truth_audit_log", "INSERT" in privs)
    assert_truthy("n8n has SELECT on truth_audit_log", "SELECT" in privs)
    assert_truthy("n8n DOES NOT have DELETE on truth_audit_log", "DELETE" not in privs)
    assert_truthy("n8n DOES NOT have UPDATE on truth_audit_log", "UPDATE" not in privs)


def functions_installed(cur):
    rows = query_all(cur, """
        SELECT proname FROM pg_proc
         WHERE proname IN ('compute_content_hash', 'validate_truth_override',
                           'reject_locked_write', 'truth_audit',
                           'block_truncate_with_locks', 'verify_content_hashes')
    """)
    names = set(r["proname"] for r in rows)
    for expected in ("compute_content_hash", "validate_truth_override",
                     "reject_locked_write", "truth_audit",
                     "block_truncate_with_locks", "verify_content_hashes"):
        assert_truthy(f"function {expected} installed", expected in names)


TESTS = [
    ("lockdown.triggers_installed", triggers_installed),
    ("lockdown.event_trigger_installed", event_trigger_installed),
    ("lockdown.audit_log_append_only_perms", audit_log_append_only),
    ("lockdown.functions_installed", functions_installed),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
