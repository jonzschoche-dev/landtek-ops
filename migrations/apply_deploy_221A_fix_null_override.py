#!/usr/bin/env python3
"""Deploy 221A-fix — Fix NULL coercion in truth_audit trigger.

verify_truth_lockdown.py [1] caught a NOT NULL violation in the audit trigger:
when no override session vars are set, `current_setting('app.truth_override', TRUE)`
returns NULL. The expression `NULL = 'on'` evaluates to NULL (not FALSE) under
Postgres three-valued logic, then the audit insert fails because
`override_authorized BOOLEAN NOT NULL` rejects the NULL.

Fix: `COALESCE(override_on, '') = 'on'` — explicit cast to boolean.

Idempotent: replaces the function definition.
"""
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


FIXED_TRUTH_AUDIT_SQL = """
CREATE OR REPLACE FUNCTION truth_audit()
RETURNS TRIGGER AS $func$
DECLARE
    actor TEXT := current_setting('app.actor', TRUE);
    override_on TEXT := COALESCE(current_setting('app.truth_override', TRUE), '');
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
    ELSE
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
         (override_on = 'on'),  -- explicit boolean from COALESCE'd value
         override_reason);

    RETURN COALESCE(NEW, OLD);
END;
$func$ LANGUAGE plpgsql SECURITY DEFINER;
"""


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()
    print("Replacing truth_audit() with NULL-safe version…")
    cur.execute(FIXED_TRUTH_AUDIT_SQL)
    print("✓ Function replaced. Re-run verify_truth_lockdown.py to confirm.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
