#!/usr/bin/env python3
"""verify_compound_drift.py — Behavioral test for 221D drift detection.

End-to-end:
  1. Create a test entity row, lock it, capture its content_hash
  2. Create a compound claim in verified_claims citing the entity
  3. Run check_compound_claim_drift() — must return zero drifts (clean state)
  4. Modify the entity row (with override) — its content_hash changes
  5. Re-run check_compound_claim_drift() — must detect drift + auto-unlock
  6. Cleanup
"""
import json
import sys

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def set_override(cur, actor, reason):
    cur.execute("SET LOCAL app.actor = %s", (actor,))
    cur.execute("SET LOCAL app.truth_override = 'on'")
    cur.execute("SET LOCAL app.truth_override_actor = %s", (actor,))
    cur.execute("SET LOCAL app.truth_override_reason = %s", (reason,))


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    entity_id = None
    claim_id = None
    failures = []

    try:
        print("=" * 60)
        print("Compound-claim drift detection verification (deploy_221D)")
        print("=" * 60)

        # [1] Create + lock test entity
        print("\n[1] Create + lock a test entity (for use as compound component)")
        cur.execute("""
            INSERT INTO entities (type, canonical_name, aliases, provenance_level, notes)
            VALUES ('person', 'TEST_DRIFT_FIXTURE', ARRAY['drift-test'],
                    'inferred_strong', 'Throwaway row for verify_compound_drift.py')
            RETURNING id
        """)
        entity_id = cur.fetchone()['id']
        conn.commit()

        set_override(cur, 'manual_review', 'drift-test: initial lock')
        cur.execute("""
            UPDATE entities
               SET verification_lock = 'hard',
                   locked_at = NOW(),
                   locked_by = 'manual_review',
                   lock_reason = 'drift test',
                   content_hash = compute_content_hash(
                       to_jsonb(entities.*)
                       - 'verification_lock' - 'locked_at' - 'locked_by'
                       - 'lock_reason' - 'content_hash' - 'created_at'
                       - 'updated_at' - 'cited_by_compound_claims'
                       - 'external_state_last_verified'
                   )
             WHERE id = %s
        """, (entity_id,))
        conn.commit()
        cur.execute("SELECT content_hash FROM entities WHERE id = %s", (entity_id,))
        original_hash = cur.fetchone()['content_hash']
        print(f"  ✓ entity {entity_id} locked, content_hash={original_hash[:16]}…")

        # [2] Create a verified_claim citing this entity
        print("\n[2] Create a compound claim citing the entity")
        component_rows = json.dumps([
            {
                "table": "entities",
                "row_pk": {"id": entity_id},
                "content_hash_at_verify": original_hash,
            }
        ])
        cur.execute("""
            INSERT INTO verified_claims
                (claim_id, claim_text, matter_code, citation_tier,
                 component_rows, verified_by)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            RETURNING id
        """, (
            'TEST_DRIFT_CLAIM',
            'Drift-test compound claim',
            'MWK-001',
            'compound',
            component_rows,
            'manual_review',
        ))
        claim_id = cur.fetchone()['id']
        conn.commit()
        print(f"  ✓ compound claim id={claim_id} created")

        # [3] Drift check — should return nothing (clean state)
        print("\n[3] check_compound_claim_drift() — expect 0 drifts")
        cur.execute("SELECT * FROM check_compound_claim_drift()")
        rows = cur.fetchall()
        conn.commit()
        if rows:
            failures.append(f"clean state but drift detected: {rows}")
        else:
            print("  ✓ clean — no drift")

        # [4] Mutate entity (with override) — content_hash will change
        print("\n[4] UPDATE the entity (legitimate override) — hash will change")
        set_override(cur, 'manual_review', 'drift-test: intentional mutation to trigger drift')
        cur.execute("UPDATE entities SET notes = 'mutated' WHERE id = %s", (entity_id,))
        # The content_hash column itself isn't auto-updated by the trigger — that's intentional.
        # The OLD content_hash remains; the recompute by check_compound_claim_drift() will
        # detect that to_jsonb(NEW) hash ≠ stored hash.
        # Actually wait — the content_hash column IS in the row. After UPDATE, what's the
        # stored hash? It's the SAME as before because we didn't touch the column. But the
        # other columns changed. So the row's `content_hash` is now stale relative to its
        # actual content — the drift function recomputes and compares.
        conn.commit()
        print(f"  ✓ entity mutated (notes changed)")

        # [5] Drift check — should detect mismatch + auto-unlock
        print("\n[5] check_compound_claim_drift() — expect drift + auto-unlock")
        cur.execute("SELECT * FROM check_compound_claim_drift()")
        rows = cur.fetchall()
        conn.commit()
        if not rows:
            failures.append("drift not detected after entity mutation")
        else:
            for r in rows:
                if r['claim_id'] == 'TEST_DRIFT_CLAIM':
                    print(f"  ✓ drift detected on TEST_DRIFT_CLAIM, auto_unlocked={r['auto_unlocked']}")
                    print(f"    drifted_components: {r['drifted_components']}")
                    break
            else:
                failures.append("our test claim not in drift results")

        # Verify the auto_unlock stuck
        cur.execute("SELECT auto_unlocked_at, auto_unlocked_reason FROM verified_claims WHERE id = %s",
                    (claim_id,))
        r = cur.fetchone()
        if not r['auto_unlocked_at']:
            failures.append("verified_claims.auto_unlocked_at not set")
        else:
            print(f"  ✓ verified_claims.auto_unlocked_at = {r['auto_unlocked_at']}")

        # And confirm the audit log has the COMPOUND_AUTO_UNLOCK entry
        cur.execute("""
            SELECT operation, notes FROM truth_audit_log
             WHERE table_name = 'verified_claims' AND (row_pk->>'id')::int = %s
               AND operation = 'COMPOUND_AUTO_UNLOCK'
             ORDER BY id DESC LIMIT 1
        """, (claim_id,))
        a = cur.fetchone()
        if not a:
            failures.append("COMPOUND_AUTO_UNLOCK not in audit log")
        else:
            print(f"  ✓ COMPOUND_AUTO_UNLOCK recorded: {a['notes']}")

    finally:
        # Cleanup
        print("\n[Cleanup]")
        try:
            if claim_id:
                # The claim is now auto_unlocked. Need to unlock the verification_lock first
                # — wait, after auto_unlock, auto_unlocked_at is set but verification_lock is still 'hard'.
                # We need override to delete.
                set_override(cur, 'manual_review', 'cleanup drift test claim')
                cur.execute("DELETE FROM verified_claims WHERE id = %s", (claim_id,))
            if entity_id:
                set_override(cur, 'manual_review', 'cleanup drift test entity')
                cur.execute("UPDATE entities SET verification_lock = NULL WHERE id = %s", (entity_id,))
                cur.execute("DELETE FROM entities WHERE id = %s", (entity_id,))
            conn.commit()
            print("  ✓ cleaned up")
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
        print("✓ Compound-claim drift detection verified.")
        sys.exit(0)


if __name__ == "__main__":
    main()
