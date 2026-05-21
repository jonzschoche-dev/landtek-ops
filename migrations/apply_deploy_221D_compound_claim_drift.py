#!/usr/bin/env python3
"""Deploy 221D — Compound claim drift detection + verified_claims triggers.

Per design Q2: component drift policy is AUTO-UNLOCK + ALERT.

Adds:
  1. Triggers on verified_claims (reject_locked_write + truth_audit) — closes
     the gap from 221A where verified_claims wasn't in CRITICAL_TABLES.
  2. check_compound_claim_drift() function — walks all locked compound claims,
     re-hashes each component, auto-unlocks any with drift, returns the list
     of drifted claims (for alerting / next steps).

verified_claims rows are inert until Phase 222 (the locking ceremony) creates
the first compound claim. The infrastructure ships now so 222 has the drift
detection ready.
"""
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


SCHEMA_SQL = """
-- Triggers on verified_claims (missed in 221A — verified_claims wasn't in
-- CRITICAL_TABLES list there).
DROP TRIGGER IF EXISTS tg_verified_claims_reject_locked ON verified_claims;
CREATE TRIGGER tg_verified_claims_reject_locked
    BEFORE UPDATE OR DELETE ON verified_claims
    FOR EACH ROW EXECUTE FUNCTION reject_locked_write();

DROP TRIGGER IF EXISTS tg_verified_claims_audit ON verified_claims;
CREATE TRIGGER tg_verified_claims_audit
    AFTER INSERT OR UPDATE OR DELETE ON verified_claims
    FOR EACH ROW EXECUTE FUNCTION truth_audit();


-- check_compound_claim_drift — re-hashes every component of every locked
-- compound claim. If any component's current hash differs from the recorded
-- content_hash_at_verify, auto-unlocks that compound claim and returns it.
--
-- Operationally: nightly cron calls this. Any returned row is an alert.
-- Per Q2: auto-unlock + alert is the policy.
CREATE OR REPLACE FUNCTION check_compound_claim_drift()
RETURNS TABLE(
    claim_id TEXT,
    claim_text TEXT,
    drifted_components JSONB,
    auto_unlocked BOOLEAN
) AS $func$
DECLARE
    v_claim record;
    v_component JSONB;
    v_table TEXT;
    v_row_id INTEGER;
    v_recorded_hash TEXT;
    v_current_hash TEXT;
    v_current_row JSONB;
    drift_list JSONB;
BEGIN
    FOR v_claim IN
        SELECT id, claim_id AS cid, claim_text AS ctext, component_rows
          FROM verified_claims
         WHERE verification_lock = 'hard' AND auto_unlocked_at IS NULL
    LOOP
        drift_list := '[]'::jsonb;

        FOR v_component IN SELECT * FROM jsonb_array_elements(v_claim.component_rows)
        LOOP
            v_table := v_component->>'table';
            v_row_id := (v_component->'row_pk'->>'id')::int;
            v_recorded_hash := v_component->>'content_hash_at_verify';

            BEGIN
                EXECUTE format(
                    'SELECT to_jsonb(t) FROM %I t WHERE id = $1',
                    v_table
                ) INTO v_current_row USING v_row_id;
            EXCEPTION WHEN OTHERS THEN
                v_current_row := NULL;
            END;

            IF v_current_row IS NULL THEN
                -- Row was deleted
                drift_list := drift_list || jsonb_build_object(
                    'table', v_table,
                    'row_id', v_row_id,
                    'reason', 'row deleted'
                );
                CONTINUE;
            END IF;

            v_current_hash := compute_content_hash(v_current_row);
            IF v_current_hash IS DISTINCT FROM v_recorded_hash THEN
                drift_list := drift_list || jsonb_build_object(
                    'table', v_table,
                    'row_id', v_row_id,
                    'reason', 'hash mismatch',
                    'recorded_hash', v_recorded_hash,
                    'current_hash', v_current_hash
                );
            END IF;
        END LOOP;

        IF jsonb_array_length(drift_list) > 0 THEN
            -- Auto-unlock per Q2 policy
            PERFORM 1 FROM pg_settings WHERE name = 'app.truth_override' AND setting = 'on';
            -- Set override for our own auto-unlock write (transaction-scoped)
            PERFORM set_config('app.truth_override', 'on', TRUE);
            PERFORM set_config('app.truth_override_actor', 'manual_review', TRUE);
            PERFORM set_config('app.truth_override_reason',
                'auto-unlock by check_compound_claim_drift: component drift detected', TRUE);
            PERFORM set_config('app.actor', 'system_drift_check', TRUE);

            UPDATE verified_claims
               SET auto_unlocked_at = NOW(),
                   auto_unlocked_reason =
                       'drift detected in ' || jsonb_array_length(drift_list) ||
                       ' component(s); see truth_audit_log for details'
             WHERE id = v_claim.id;

            -- Log the drift event explicitly
            INSERT INTO truth_audit_log
                (table_name, row_pk, operation, before_state, after_state,
                 db_user, app_actor, notes)
            VALUES
                ('verified_claims', jsonb_build_object('id', v_claim.id),
                 'COMPOUND_AUTO_UNLOCK', NULL, drift_list,
                 current_user, 'system_drift_check',
                 'claim_id=' || v_claim.cid);

            claim_id := v_claim.cid;
            claim_text := v_claim.ctext;
            drifted_components := drift_list;
            auto_unlocked := TRUE;
            RETURN NEXT;
        END IF;
    END LOOP;
END;
$func$ LANGUAGE plpgsql;
"""


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()
    print("Adding triggers to verified_claims + installing drift detection…")
    cur.execute(SCHEMA_SQL)
    print("✓ tg_verified_claims_reject_locked installed")
    print("✓ tg_verified_claims_audit installed")
    print("✓ check_compound_claim_drift() function installed")

    # Sanity check
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.triggers
         WHERE event_object_table = 'verified_claims'
    """)
    n = cur.fetchone()[0]
    print(f"  verified_claims triggers active: {n}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
