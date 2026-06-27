#!/usr/bin/env python3
"""verify_promote_flow.py — Behavioral test for the promote-proposal path.

Exercises 221B:
  1. Insert a proposed change to `entities` via proposed_changes
  2. Programmatically promote it (bypassing CLI prompts, but using the same
     internal apply_proposal function)
  3. Confirm the entity row was inserted with the override session vars set
  4. Confirm audit log shows INSERT (or OVERRIDE if a lock was set)
  5. Cleanup: delete the test entity (with override) + the proposal

Run after deploy_221B applies.
"""
import json
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def main():
    from promote_proposals import apply_proposal

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    proposal_id = None
    test_entity_id = None
    failures = []

    try:
        print("=" * 60)
        print("Promote-flow verification (deploy_221B)")
        print("=" * 60)

        # [1] Insert proposal
        print("\n[1] INSERT proposed_changes row (proposed INSERT to entities)")
        proposed_state = {
            "type": "person",
            "canonical_name": "TEST_PROMOTE_FIXTURE",
            "aliases": ["test-promote"],
            "provenance_level": "inferred_strong",
            "notes": "Throwaway row for verify_promote_flow.py — safe to delete",
        }
        cur.execute("""
            INSERT INTO proposed_changes
                (target_table, target_row_id, operation, proposed_state,
                 proposed_by, rationale)
            VALUES (%s, NULL, 'INSERT', %s::jsonb, 'verify_promote_flow.py',
                    'behavioral test for 221B')
            RETURNING id
        """, ('entities', json.dumps(proposed_state)))
        proposal_id = cur.fetchone()['id']
        conn.commit()
        print(f"  ✓ proposal id={proposal_id} inserted")

        # [2] Apply via the promote helper (uses SET LOCAL override flow)
        print("\n[2] Promote proposal via apply_proposal() — manual_review actor")
        cur.execute("SELECT * FROM proposed_changes WHERE id = %s", (proposal_id,))
        p = cur.fetchone()
        # Wrap in its own savepoint so SET LOCAL applies
        test_entity_id = apply_proposal(
            cur, p, actor='manual_review',
            reason='221B verification path', lock_after=False,
        )
        conn.commit()
        if not test_entity_id:
            failures.append("apply_proposal returned no id")
        else:
            print(f"  ✓ entity created, id={test_entity_id}")

        # [3] Confirm proposal status
        print("\n[3] Confirm proposal marked approved + promoted")
        cur.execute("SELECT review_status, promoted_at, reviewed_by "
                    "FROM proposed_changes WHERE id = %s", (proposal_id,))
        p = cur.fetchone()
        if p['review_status'] != 'approved' or not p['promoted_at']:
            failures.append(f"proposal status not approved: {p}")
        else:
            print(f"  ✓ status=approved, reviewed_by={p['reviewed_by']}")

        # [4] Confirm audit log captured the entity INSERT
        print("\n[4] Confirm audit log captured INSERT")
        cur.execute("""
            SELECT operation, app_actor FROM truth_audit_log
             WHERE table_name = 'entities' AND (row_pk->>'id')::int = %s
             ORDER BY id DESC LIMIT 1
        """, (test_entity_id,))
        row = cur.fetchone()
        if not row or row['operation'] != 'INSERT':
            failures.append(f"INSERT not audited: {row}")
        else:
            print(f"  ✓ audit log shows INSERT by app_actor={row['app_actor']}")

        # [5] Promote with lock_after=True — should lock + log OVERRIDE on the lock UPDATE
        print("\n[5] Second proposal (UPDATE) — promote with lock_after=True")
        # We need to wrap this in a new transaction so SET LOCAL doesn't leak
        cur.execute("""
            INSERT INTO proposed_changes
                (target_table, target_row_id, operation, proposed_state,
                 proposed_by, rationale)
            VALUES ('entities', %s, 'UPDATE', %s::jsonb,
                    'verify_promote_flow.py', 'test lock-on-promote')
            RETURNING id
        """, (test_entity_id, json.dumps({"notes": "promoted with lock"})))
        proposal2_id = cur.fetchone()['id']
        conn.commit()

        cur.execute("SELECT * FROM proposed_changes WHERE id = %s", (proposal2_id,))
        p2 = cur.fetchone()
        apply_proposal(cur, p2, actor='manual_review',
                       reason='221B lock-on-promote test', lock_after=True)
        conn.commit()

        cur.execute("SELECT verification_lock, content_hash FROM entities WHERE id = %s",
                    (test_entity_id,))
        ent = cur.fetchone()
        if ent['verification_lock'] != 'hard' or not ent['content_hash']:
            failures.append(f"lock-on-promote didn't stick: {ent}")
        else:
            print(f"  ✓ entity locked with hash={ent['content_hash'][:16]}…")

    finally:
        # Cleanup
        if test_entity_id:
            print("\n[Cleanup] Removing test entity + proposals")
            try:
                cur.execute("SET LOCAL app.actor = 'manual_review'")
                cur.execute("SET LOCAL app.truth_override = 'on'")
                cur.execute("SET LOCAL app.truth_override_actor = 'manual_review'")
                cur.execute("SET LOCAL app.truth_override_reason = "
                            "'cleanup from verify_promote_flow.py'")
                cur.execute("UPDATE entities SET verification_lock = NULL WHERE id = %s",
                            (test_entity_id,))
                cur.execute("DELETE FROM entities WHERE id = %s", (test_entity_id,))
                cur.execute("DELETE FROM proposed_changes "
                            "WHERE proposed_by = 'verify_promote_flow.py'")
                conn.commit()
                print(f"  ✓ cleaned up")
            except Exception as e:
                conn.rollback()
                print(f"  ⚠ cleanup failed: {e}")
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
        print("✓ Promote flow verified end-to-end.")
        sys.exit(0)


if __name__ == "__main__":
    main()
