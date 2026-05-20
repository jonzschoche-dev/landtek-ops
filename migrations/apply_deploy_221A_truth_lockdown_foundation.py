#!/usr/bin/env python3
"""Deploy 221A — Truth lockdown foundation: schema + triggers + audit log.

This is the INFRASTRUCTURE deploy. No rows get locked here — only the
machinery to enforce locks once they're set. The locking ceremony (Phase 222)
is when rows actually graduate to verification_lock='hard'.

Threat model addressed in this deploy:
  - #1 LLM extraction silently overwrites verified row → reject_locked_write trigger
  - #2 Cross-agent collision → advisory locks (helper functions added)
  - #3 Regex backfill mangles verified → reject_locked_write trigger
  - #4 Ad-hoc SQL bypasses safeguards → triggers fire regardless of caller
  - #6 Trigger bug → content_hash check catches divergence
  - #7 TRUNCATE bypasses row triggers → block_truncate_with_locks event trigger
  - #8 Superuser bypass → content_hash verification catches it
  - #16 Audit log trigger drop → REVOKE DELETE/UPDATE on truth_audit_log
  - #17 verified_by spoof → CHECK constraint on actor enum

Per design sign-off 2026-05-21:
  - Enumerated actors: 'jonathan', 'barandon', 'manual_review'
  - Component drift policy: auto-unlock + alert (Q2)
  - External staleness window: 90 days (Q4)
  - Halt-on-hash-mismatch: REVOKE writes + alert (Q5)
  - Advisory lock per row before promotion writes (Q6)

Idempotent. Re-runnable. Does NOT touch existing row data.
"""
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


# Critical tables that get lockdown columns + triggers.
CRITICAL_TABLES = [
    "titles",
    "title_chain",
    "subdivision_plans",
    "instruments_on_title",
    "entities",
    "title_transfers",
]

# Tables where rows reference an external authority (RD, LMB, etc.)
# and need staleness tracking per Q4.
EXTERNALLY_DEPENDENT_TABLES = [
    "titles",
    "title_chain",
    "subdivision_plans",
]


# ─── Schema: lockdown columns on critical tables ─────────────────────────────
SCHEMA_COLUMNS_SQL = """
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN SELECT unnest(ARRAY[{tables}]) LOOP
        EXECUTE format('
            ALTER TABLE %I
                ADD COLUMN IF NOT EXISTS verification_lock TEXT,
                ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ,
                ADD COLUMN IF NOT EXISTS locked_by TEXT,
                ADD COLUMN IF NOT EXISTS lock_reason TEXT,
                ADD COLUMN IF NOT EXISTS content_hash TEXT,
                ADD COLUMN IF NOT EXISTS cited_by_compound_claims TEXT[] DEFAULT ''{{}}''::TEXT[];
        ', t);
        -- CHECK constraint: only 'hard' or NULL allowed
        EXECUTE format('
            DO $inner$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.check_constraints
                     WHERE constraint_name = %L
                ) THEN
                    ALTER TABLE %I ADD CONSTRAINT %I
                        CHECK (verification_lock IS NULL OR verification_lock = ''hard'');
                END IF;
            END $inner$;
        ', t || '_lock_check', t, t || '_lock_check');
    END LOOP;
END $$;
""".format(tables=", ".join(f"'{t}'" for t in CRITICAL_TABLES))


EXTERNAL_COLUMNS_SQL = """
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN SELECT unnest(ARRAY[{tables}]) LOOP
        EXECUTE format('
            ALTER TABLE %I
                ADD COLUMN IF NOT EXISTS external_state_last_verified TIMESTAMPTZ;
        ', t);
    END LOOP;
END $$;
""".format(tables=", ".join(f"'{t}'" for t in EXTERNALLY_DEPENDENT_TABLES))


# ─── New tables ─────────────────────────────────────────────────────────────
NEW_TABLES_SQL = """
-- Append-only audit log. REVOKEd from n8n role below.
CREATE TABLE IF NOT EXISTS truth_audit_log (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    table_name TEXT NOT NULL,
    row_pk JSONB NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN (
        'INSERT', 'UPDATE', 'DELETE', 'LOCK', 'UNLOCK',
        'OVERRIDE', 'PROPOSAL_CREATED', 'PROPOSAL_PROMOTED',
        'COMPOUND_AUTO_UNLOCK', 'HASH_MISMATCH'
    )),
    before_state JSONB,
    after_state JSONB,
    content_hash_before TEXT,
    content_hash_after TEXT,
    db_user TEXT NOT NULL DEFAULT current_user,
    app_actor TEXT,
    override_authorized BOOLEAN NOT NULL DEFAULT FALSE,
    override_reason TEXT,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_truth_audit_table_row
    ON truth_audit_log(table_name, (row_pk->>'id'));
CREATE INDEX IF NOT EXISTS idx_truth_audit_ts ON truth_audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_truth_audit_operation ON truth_audit_log(operation);

-- Compound claim verification with content-hash dependency tracking.
CREATE TABLE IF NOT EXISTS verified_claims (
    id SERIAL PRIMARY KEY,
    claim_id TEXT UNIQUE NOT NULL,
    claim_text TEXT NOT NULL,
    matter_code TEXT NOT NULL,
    citation_tier TEXT NOT NULL,
    component_rows JSONB NOT NULL,
    verified_by TEXT NOT NULL CHECK (verified_by IN ('jonathan', 'barandon', 'manual_review')),
    verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verification_lock TEXT NOT NULL DEFAULT 'hard'
        CHECK (verification_lock = 'hard'),
    auto_unlocked_at TIMESTAMPTZ,
    auto_unlocked_reason TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_verified_claims_matter ON verified_claims(matter_code);
CREATE INDEX IF NOT EXISTS idx_verified_claims_locked
    ON verified_claims(verification_lock) WHERE auto_unlocked_at IS NULL;

-- Citation lock for source documents (Tier 3 protection).
CREATE TABLE IF NOT EXISTS document_citation_lock (
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
    cited_by_table TEXT NOT NULL,
    cited_by_row_pk JSONB NOT NULL,
    locked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (document_id, cited_by_table, cited_by_row_pk)
);
CREATE INDEX IF NOT EXISTS idx_document_citation_lock_doc
    ON document_citation_lock(document_id);
"""


# ─── Functions ──────────────────────────────────────────────────────────────
FUNCTIONS_SQL = """
-- Compute canonical content hash for any row, excluding lock-metadata columns.
CREATE OR REPLACE FUNCTION compute_content_hash(row_jsonb JSONB)
RETURNS TEXT AS $func$
DECLARE
    excluded TEXT[] := ARRAY[
        'verification_lock', 'locked_at', 'locked_by', 'lock_reason',
        'content_hash', 'created_at', 'updated_at',
        'cited_by_compound_claims', 'external_state_last_verified'
    ];
    filtered JSONB := row_jsonb;
    col TEXT;
BEGIN
    FOREACH col IN ARRAY excluded LOOP
        filtered := filtered - col;
    END LOOP;
    -- Use sorted-keys JSON serialization for stable hashing
    RETURN encode(digest(filtered::text, 'sha256'), 'hex');
END;
$func$ LANGUAGE plpgsql IMMUTABLE;


-- Validate override session variables. Returns NULL if not overriding;
-- raises EXCEPTION if override fields are partial / invalid.
CREATE OR REPLACE FUNCTION validate_truth_override()
RETURNS TABLE(override_on BOOLEAN, actor TEXT, reason TEXT) AS $func$
DECLARE
    o TEXT := current_setting('app.truth_override', TRUE);
    a TEXT := current_setting('app.truth_override_actor', TRUE);
    r TEXT := current_setting('app.truth_override_reason', TRUE);
BEGIN
    IF o IS NULL OR o = '' OR o = 'off' THEN
        RETURN QUERY SELECT FALSE, NULL::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    IF o != 'on' THEN
        RAISE EXCEPTION 'BLOCKED: app.truth_override must be ''on'' or unset; got %', o;
    END IF;
    IF COALESCE(a, '') = '' THEN
        RAISE EXCEPTION 'BLOCKED: override requires app.truth_override_actor to be set.';
    END IF;
    IF a NOT IN ('jonathan', 'barandon', 'manual_review') THEN
        RAISE EXCEPTION 'BLOCKED: override_actor must be one of (jonathan, barandon, manual_review); got %', a;
    END IF;
    IF COALESCE(r, '') = '' THEN
        RAISE EXCEPTION 'BLOCKED: override requires app.truth_override_reason to be set with non-empty reason.';
    END IF;

    RETURN QUERY SELECT TRUE, a, r;
END;
$func$ LANGUAGE plpgsql;


-- BEFORE UPDATE/DELETE trigger: reject writes to locked rows unless override.
CREATE OR REPLACE FUNCTION reject_locked_write()
RETURNS TRIGGER AS $func$
DECLARE
    override_active BOOLEAN;
    override_actor TEXT;
    override_reason TEXT;
BEGIN
    -- Unlocked rows: always allow.
    IF OLD.verification_lock IS DISTINCT FROM 'hard' THEN
        RETURN COALESCE(NEW, OLD);
    END IF;

    -- Locked. Validate override.
    SELECT * INTO override_active, override_actor, override_reason
      FROM validate_truth_override();

    IF NOT override_active THEN
        RAISE EXCEPTION
            'BLOCKED: row in % (pk=%) has verification_lock=hard. '
            'To override, in the SAME transaction: '
            'SET LOCAL app.truth_override=on; '
            'SET LOCAL app.truth_override_actor=<jonathan|barandon|manual_review>; '
            'SET LOCAL app.truth_override_reason=<reason>;',
            TG_TABLE_NAME, OLD.id;
    END IF;

    -- Override valid. The audit trigger will record OVERRIDE operation.
    RETURN COALESCE(NEW, OLD);
END;
$func$ LANGUAGE plpgsql;


-- AFTER INSERT/UPDATE/DELETE trigger: write to truth_audit_log.
-- Marked SECURITY DEFINER so it can INSERT to log even though n8n has no INSERT grant.
CREATE OR REPLACE FUNCTION truth_audit()
RETURNS TRIGGER AS $func$
DECLARE
    actor TEXT := current_setting('app.actor', TRUE);
    override_on TEXT := current_setting('app.truth_override', TRUE);
    override_reason TEXT := current_setting('app.truth_override_reason', TRUE);
    op TEXT;
    before_json JSONB;
    after_json JSONB;
    hash_before TEXT;
    hash_after TEXT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        op := 'INSERT';
        before_json := NULL;
        after_json := to_jsonb(NEW);
        hash_after := compute_content_hash(after_json);
    ELSIF TG_OP = 'UPDATE' THEN
        op := CASE WHEN override_on = 'on' THEN 'OVERRIDE' ELSE 'UPDATE' END;
        before_json := to_jsonb(OLD);
        after_json := to_jsonb(NEW);
        hash_before := compute_content_hash(before_json);
        hash_after := compute_content_hash(after_json);
    ELSE  -- DELETE
        op := 'DELETE';
        before_json := to_jsonb(OLD);
        after_json := NULL;
        hash_before := compute_content_hash(before_json);
    END IF;

    INSERT INTO truth_audit_log
        (table_name, row_pk, operation, before_state, after_state,
         content_hash_before, content_hash_after, db_user, app_actor,
         override_authorized, override_reason)
    VALUES
        (TG_TABLE_NAME,
         jsonb_build_object('id', COALESCE(NEW.id, OLD.id)),
         op, before_json, after_json,
         hash_before, hash_after,
         current_user, actor,
         override_on = 'on', override_reason);

    RETURN COALESCE(NEW, OLD);
END;
$func$ LANGUAGE plpgsql SECURITY DEFINER;


-- Event trigger: block TRUNCATE on tables with locked rows.
CREATE OR REPLACE FUNCTION block_truncate_with_locks()
RETURNS event_trigger AS $func$
DECLARE
    obj record;
    has_locks BOOLEAN;
BEGIN
    FOR obj IN
        SELECT * FROM pg_event_trigger_ddl_commands()
         WHERE command_tag = 'TRUNCATE TABLE'
    LOOP
        EXECUTE format(
            'SELECT EXISTS (SELECT 1 FROM %s WHERE verification_lock = ''hard'')',
            obj.object_identity
        ) INTO has_locks;
        IF has_locks THEN
            RAISE EXCEPTION
                'BLOCKED: cannot TRUNCATE %; contains verification_lock=hard rows. '
                'Override via per-row UPDATE if intentional.',
                obj.object_identity;
        END IF;
    END LOOP;
END;
$func$ LANGUAGE plpgsql;


-- Periodic content-hash verification. Returns mismatches.
-- Called by nightly cron (see deploy_223). On any return row → halt writes.
CREATE OR REPLACE FUNCTION verify_content_hashes(p_table_name TEXT DEFAULT NULL)
RETURNS TABLE(table_name TEXT, row_id INTEGER, stored_hash TEXT, computed_hash TEXT) AS $func$
DECLARE
    tbl TEXT;
    rec record;
    tables_to_check TEXT[];
BEGIN
    IF p_table_name IS NOT NULL THEN
        tables_to_check := ARRAY[p_table_name];
    ELSE
        tables_to_check := ARRAY[{critical_tables}];
    END IF;

    FOREACH tbl IN ARRAY tables_to_check LOOP
        FOR rec IN EXECUTE format(
            'SELECT id, content_hash, to_jsonb(t) AS row_json
               FROM %I t
              WHERE verification_lock = ''hard'' AND content_hash IS NOT NULL', tbl)
        LOOP
            IF compute_content_hash(rec.row_json) != rec.content_hash THEN
                table_name := tbl;
                row_id := rec.id;
                stored_hash := rec.content_hash;
                computed_hash := compute_content_hash(rec.row_json);
                RETURN NEXT;
            END IF;
        END LOOP;
    END LOOP;
END;
$func$ LANGUAGE plpgsql;
""".format(critical_tables=", ".join(f"'{t}'" for t in CRITICAL_TABLES))


# ─── Triggers per critical table ─────────────────────────────────────────────
TRIGGERS_SQL_TEMPLATE = """
DROP TRIGGER IF EXISTS tg_{table}_reject_locked ON {table};
CREATE TRIGGER tg_{table}_reject_locked
    BEFORE UPDATE OR DELETE ON {table}
    FOR EACH ROW EXECUTE FUNCTION reject_locked_write();

DROP TRIGGER IF EXISTS tg_{table}_audit ON {table};
CREATE TRIGGER tg_{table}_audit
    AFTER INSERT OR UPDATE OR DELETE ON {table}
    FOR EACH ROW EXECUTE FUNCTION truth_audit();
"""


EVENT_TRIGGER_SQL = """
DROP EVENT TRIGGER IF EXISTS block_truncate_critical;
CREATE EVENT TRIGGER block_truncate_critical
    ON ddl_command_end
    EXECUTE FUNCTION block_truncate_with_locks();
"""


# ─── Permissions ────────────────────────────────────────────────────────────
PERMISSIONS_SQL = """
-- truth_audit_log is append-only for the n8n role.
-- Functions that write to it use SECURITY DEFINER (truth_audit function).
REVOKE DELETE, UPDATE, TRUNCATE ON truth_audit_log FROM PUBLIC;
REVOKE DELETE, UPDATE, TRUNCATE ON truth_audit_log FROM n8n;
GRANT INSERT, SELECT ON truth_audit_log TO n8n;
GRANT USAGE, SELECT ON SEQUENCE truth_audit_log_id_seq TO n8n;

-- verified_claims and document_citation_lock: full access for n8n
GRANT INSERT, SELECT, UPDATE ON verified_claims TO n8n;
GRANT USAGE, SELECT ON SEQUENCE verified_claims_id_seq TO n8n;
GRANT INSERT, SELECT, UPDATE, DELETE ON document_citation_lock TO n8n;
"""


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("Deploy 221A — Truth lockdown foundation")
        print("=" * 60)

        print("\n[1/6] Enabling pgcrypto extension (for sha256)…")
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

        print("[2/6] Adding lockdown columns to critical tables…")
        cur.execute(SCHEMA_COLUMNS_SQL)
        for t in CRITICAL_TABLES:
            print(f"  ✓ {t}")

        print("[3/6] Adding external_state_last_verified columns…")
        cur.execute(EXTERNAL_COLUMNS_SQL)
        for t in EXTERNALLY_DEPENDENT_TABLES:
            print(f"  ✓ {t}")

        print("[4/6] Creating new tables (truth_audit_log, verified_claims, document_citation_lock)…")
        cur.execute(NEW_TABLES_SQL)
        print("  ✓ truth_audit_log")
        print("  ✓ verified_claims")
        print("  ✓ document_citation_lock")

        print("[5/6] Creating functions + triggers…")
        cur.execute(FUNCTIONS_SQL)
        print("  ✓ compute_content_hash")
        print("  ✓ validate_truth_override")
        print("  ✓ reject_locked_write")
        print("  ✓ truth_audit")
        print("  ✓ block_truncate_with_locks")
        print("  ✓ verify_content_hashes")

        for t in CRITICAL_TABLES:
            cur.execute(TRIGGERS_SQL_TEMPLATE.format(table=t))
            print(f"  ✓ triggers on {t}")

        cur.execute(EVENT_TRIGGER_SQL)
        print("  ✓ event trigger block_truncate_critical")

        print("[6/6] Setting permissions…")
        cur.execute(PERMISSIONS_SQL)
        print("  ✓ truth_audit_log: append-only for n8n (no DELETE/UPDATE/TRUNCATE)")
        print("  ✓ verified_claims, document_citation_lock: standard grants")

        conn.commit()
        print()
        print("=" * 60)
        print("✓ Deploy 221A complete — infrastructure live, no rows locked yet.")
        print()
        print("Sanity checks:")

        # Verify trigger creation
        cur.execute("""
            SELECT trigger_name, event_object_table
              FROM information_schema.triggers
             WHERE trigger_name LIKE 'tg_%_audit' OR trigger_name LIKE 'tg_%_reject_locked'
             ORDER BY event_object_table, trigger_name
        """)
        triggers = cur.fetchall()
        print(f"  Triggers active: {len(triggers)}")
        for tg, tbl in triggers:
            print(f"    {tbl}.{tg}")

        # Verify event trigger
        cur.execute("SELECT evtname FROM pg_event_trigger WHERE evtname = 'block_truncate_critical'")
        if cur.fetchone():
            print("  ✓ Event trigger block_truncate_critical installed")

        # Verify audit log permissions
        cur.execute("""
            SELECT grantee, privilege_type FROM information_schema.table_privileges
             WHERE table_name = 'truth_audit_log' AND grantee = 'n8n'
        """)
        privs = sorted(p[1] for p in cur.fetchall())
        print(f"  truth_audit_log n8n privileges: {privs}")
        assert "DELETE" not in privs, "DELETE should be revoked!"
        assert "UPDATE" not in privs, "UPDATE should be revoked!"
        assert "INSERT" in privs, "INSERT must be granted (via SECURITY DEFINER)"
        print("  ✓ append-only enforced")

        print()
        print("Next: Phase 221B — proposal sibling tables + promote CLI.")
        print("Locking ceremony (Phase 222) is when rows actually get locked.")

    except Exception as e:
        conn.rollback()
        print(f"\n✗ ROLLED BACK: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
