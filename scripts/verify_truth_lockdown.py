#!/usr/bin/env python3
"""verify_truth_lockdown.py — End-to-end behavioral tests for deploy_221A.

Exercises every lockdown path on a throwaway entity row to confirm the
infrastructure actually does what the design requires:

  1. INSERT on unlocked row → audit log captures it
  2. UPDATE on unlocked row → audit log captures it
  3. LOCK a row (set verification_lock='hard' + content_hash)
  4. UPDATE on locked row WITHOUT override → must raise BLOCKED exception
  5. UPDATE on locked row WITH partial override (missing actor) → must raise
  6. UPDATE on locked row WITH bad actor name → must raise
  7. UPDATE on locked row WITH valid override → allowed; audit log shows OVERRIDE
  8. Override is transaction-scoped (next txn without SET LOCAL → blocked again)
  9. Cleanup: unlock + delete the test row

Run this before declaring 221A done. Run again any time the trigger code
changes.
"""
import sys
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


class TestFail(Exception):
    pass


def expect_exception(cur, sql, args, expected_msg_part, label):
    """Execute SQL; expect a Postgres exception containing expected_msg_part."""
    try:
        cur.execute(sql, args)
        raise TestFail(f"[{label}] expected exception containing '{expected_msg_part}', "
                       f"but SQL succeeded")
    except psycopg2.errors.RaiseException as e:
        if expected_msg_part.lower() not in str(e).lower():
            raise TestFail(f"[{label}] expected exception with '{expected_msg_part}', "
                           f"got: {e}")
        print(f"  ✓ {label}: blocked as expected")
        return e
    except psycopg2.Error as e:
        if expected_msg_part.lower() not in str(e).lower():
            raise TestFail(f"[{label}] expected error with '{expected_msg_part}', got: {e}")
        print(f"  ✓ {label}: blocked as expected")
        return e


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    test_entity_id = None
    failures = []

    try:
        print("=" * 60)
        print("Truth lockdown behavioral verification (deploy_221A)")
        print("=" * 60)

        # ─── Test 1: INSERT logged to audit ────────────────────────────────
        print("\n[1] INSERT into entities → audit log captures")
        cur.execute("""
            INSERT INTO entities (type, canonical_name, aliases, provenance_level, notes)
            VALUES ('person', 'TEST_LOCKDOWN_FIXTURE', ARRAY['test'], 'inferred_weak',
                    'Throwaway row for verify_truth_lockdown.py — safe to delete')
            RETURNING id
        """)
        test_entity_id = cur.fetchone()["id"]
        conn.commit()

        cur.execute("""
            SELECT operation, app_actor FROM truth_audit_log
             WHERE table_name = 'entities'
               AND (row_pk->>'id')::int = %s
             ORDER BY id DESC LIMIT 1
        """, (test_entity_id,))
        row = cur.fetchone()
        if not row or row["operation"] != "INSERT":
            failures.append("INSERT not logged")
        else:
            print(f"  ✓ audit log captured INSERT (entity id={test_entity_id})")

        # ─── Test 2: UPDATE on unlocked row → audit logged ─────────────────
        print("\n[2] UPDATE on unlocked row → audit log captures UPDATE")
        cur.execute("UPDATE entities SET notes = 'updated #1' WHERE id = %s", (test_entity_id,))
        conn.commit()
        cur.execute("""
            SELECT operation FROM truth_audit_log
             WHERE table_name = 'entities' AND (row_pk->>'id')::int = %s
             ORDER BY id DESC LIMIT 1
        """, (test_entity_id,))
        row = cur.fetchone()
        if not row or row["operation"] != "UPDATE":
            failures.append(f"UPDATE not logged (got: {row})")
        else:
            print(f"  ✓ audit log captured UPDATE")

        # ─── Test 3: LOCK the row (set verification_lock='hard') ───────────
        print("\n[3] LOCK row (set verification_lock='hard' + content_hash)")
        cur.execute("""
            UPDATE entities
               SET verification_lock = 'hard',
                   locked_at = NOW(),
                   locked_by = 'manual_review',
                   lock_reason = 'verify_truth_lockdown.py test fixture lock',
                   content_hash = compute_content_hash(to_jsonb(entities.*) - 'verification_lock'
                                                       - 'locked_at' - 'locked_by' - 'lock_reason'
                                                       - 'content_hash' - 'created_at'
                                                       - 'updated_at' - 'cited_by_compound_claims')
             WHERE id = %s
        """, (test_entity_id,))
        conn.commit()
        cur.execute("SELECT verification_lock, content_hash FROM entities WHERE id = %s",
                    (test_entity_id,))
        row = cur.fetchone()
        if row["verification_lock"] != "hard" or not row["content_hash"]:
            failures.append("LOCK did not stick")
        else:
            print(f"  ✓ row locked, hash={row['content_hash'][:16]}…")

        # ─── Test 4: UPDATE on locked row WITHOUT override → BLOCKED ──────
        print("\n[4] UPDATE on locked row WITHOUT override → must be blocked")
        try:
            expect_exception(
                cur,
                "UPDATE entities SET notes = 'should fail' WHERE id = %s",
                (test_entity_id,),
                "verification_lock=hard",
                "no-override block",
            )
            conn.rollback()
        except TestFail as e:
            failures.append(str(e))
            conn.rollback()

        # ─── Test 5: partial override (missing actor) → BLOCKED ────────────
        print("\n[5] UPDATE with override=on but missing actor → must be blocked")
        try:
            cur.execute("SET LOCAL app.truth_override = 'on'")
            expect_exception(
                cur,
                "UPDATE entities SET notes = 'should fail' WHERE id = %s",
                (test_entity_id,),
                "truth_override_actor",
                "missing-actor block",
            )
            conn.rollback()
        except TestFail as e:
            failures.append(str(e))
            conn.rollback()

        # ─── Test 6: invalid actor → BLOCKED ────────────────────────────────
        print("\n[6] UPDATE with override but bad actor name → must be blocked")
        try:
            cur.execute("SET LOCAL app.truth_override = 'on'")
            cur.execute("SET LOCAL app.truth_override_actor = 'random_attacker'")
            cur.execute("SET LOCAL app.truth_override_reason = 'malicious'")
            expect_exception(
                cur,
                "UPDATE entities SET notes = 'should fail' WHERE id = %s",
                (test_entity_id,),
                "override_actor must be one of",
                "bad-actor block",
            )
            conn.rollback()
        except TestFail as e:
            failures.append(str(e))
            conn.rollback()

        # ─── Test 7: VALID override → allowed, audit logs OVERRIDE ─────────
        print("\n[7] UPDATE with full valid override → allowed; audit log shows OVERRIDE")
        cur.execute("SET LOCAL app.truth_override = 'on'")
        cur.execute("SET LOCAL app.truth_override_actor = 'manual_review'")
        cur.execute("SET LOCAL app.truth_override_reason = "
                    "'test_7: legitimate update with full override path'")
        cur.execute("UPDATE entities SET notes = 'overridden by manual_review' WHERE id = %s",
                    (test_entity_id,))
        conn.commit()
        cur.execute("""
            SELECT operation, override_authorized, override_reason FROM truth_audit_log
             WHERE table_name = 'entities' AND (row_pk->>'id')::int = %s
             ORDER BY id DESC LIMIT 1
        """, (test_entity_id,))
        row = cur.fetchone()
        if not row or row["operation"] != "OVERRIDE" or not row["override_authorized"]:
            failures.append(f"OVERRIDE not recorded properly: {row}")
        else:
            print(f"  ✓ OVERRIDE logged: actor={row.get('override_reason', '')[:50]}…")

        # ─── Test 8: next txn without SET LOCAL → blocked again ────────────
        print("\n[8] Override is transaction-scoped — next txn without SET LOCAL is blocked")
        try:
            expect_exception(
                cur,
                "UPDATE entities SET notes = 'should fail again' WHERE id = %s",
                (test_entity_id,),
                "verification_lock=hard",
                "post-commit re-block",
            )
            conn.rollback()
        except TestFail as e:
            failures.append(str(e))
            conn.rollback()

        # ─── Test 9: TRUNCATE block ────────────────────────────────────────
        print("\n[9] TRUNCATE on a table with locked rows → must be blocked")
        try:
            expect_exception(
                cur,
                "TRUNCATE TABLE entities",
                None,
                "cannot truncate",
                "truncate block",
            )
            conn.rollback()
        except TestFail as e:
            failures.append(str(e))
            conn.rollback()

    finally:
        # ─── Cleanup: unlock + delete the test row ─────────────────────────
        if test_entity_id:
            print("\n[Cleanup] Unlocking + deleting test fixture")
            try:
                cur.execute("SET LOCAL app.truth_override = 'on'")
                cur.execute("SET LOCAL app.truth_override_actor = 'manual_review'")
                cur.execute("SET LOCAL app.truth_override_reason = "
                            "'cleanup test fixture from verify_truth_lockdown.py'")
                cur.execute("UPDATE entities SET verification_lock = NULL WHERE id = %s",
                            (test_entity_id,))
                cur.execute("DELETE FROM entities WHERE id = %s", (test_entity_id,))
                conn.commit()
                print(f"  ✓ test entity {test_entity_id} cleaned up")
            except Exception as e:
                conn.rollback()
                print(f"  ⚠ cleanup failed: {e}")
                print(f"  → manual cleanup: "
                      f"DELETE FROM entities WHERE canonical_name = 'TEST_LOCKDOWN_FIXTURE';")

        cur.close()
        conn.close()

    print()
    print("=" * 60)
    if failures:
        print(f"✗ {len(failures)} FAILURE(S):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("✓ All lockdown behavioral tests passed.")
        print("  Infrastructure is functioning as designed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
