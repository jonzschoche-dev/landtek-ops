#!/usr/bin/env python3
"""Deploy 247 audit-trigger fix.

The truth_audit() trigger hardcodes jsonb_build_object('id', NEW.id) which
breaks for tables whose PK isn't 'id':
  - titles (PK = tct_number)
  - title_chain (composite PK = parent_title + child_title)

This patch rewrites truth_audit to dynamically pick row_pk per table.

Idempotent (CREATE OR REPLACE).
"""
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

PATCH_SQL = r"""
CREATE OR REPLACE FUNCTION truth_audit() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    actor TEXT := current_setting('app.actor', TRUE);
    override_on TEXT := COALESCE(current_setting('app.truth_override', TRUE), '');
    override_reason TEXT := current_setting('app.truth_override_reason', TRUE);
    op TEXT;
    before_json JSONB;
    after_json JSONB;
    hash_before TEXT;
    hash_after TEXT;
    row_pk JSONB;
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

    -- Build row_pk dynamically per table's actual PK.
    -- For unknown tables, fall back to attempting NEW.id / OLD.id; if neither
    -- exists the row is logged with an empty pk (preferable to crashing the
    -- write — audit is supplementary, not enforcement).
    row_pk := CASE TG_TABLE_NAME
        WHEN 'titles' THEN
            jsonb_build_object('tct_number',
                COALESCE(after_json->>'tct_number', before_json->>'tct_number'))
        WHEN 'title_chain' THEN
            jsonb_build_object(
                'parent_title', COALESCE(after_json->>'parent_title', before_json->>'parent_title'),
                'child_title',  COALESCE(after_json->>'child_title',  before_json->>'child_title'))
        WHEN 'subdivision_plans' THEN
            jsonb_build_object('id',
                COALESCE((after_json->>'id')::int, (before_json->>'id')::int))
        WHEN 'instruments_on_title' THEN
            jsonb_build_object('id',
                COALESCE((after_json->>'id')::int, (before_json->>'id')::int))
        WHEN 'entities' THEN
            jsonb_build_object('id',
                COALESCE((after_json->>'id')::int, (before_json->>'id')::int))
        WHEN 'title_transfers' THEN
            jsonb_build_object('id',
                COALESCE((after_json->>'id')::int, (before_json->>'id')::int))
        ELSE
            -- Unknown table: try id then leave empty
            COALESCE(
                jsonb_build_object('id',
                    COALESCE((after_json->>'id')::int, (before_json->>'id')::int)),
                '{}'::jsonb)
    END;

    INSERT INTO truth_audit_log
        (table_name, row_pk, operation, before_state, after_state,
         content_hash_before, content_hash_after, db_user, app_actor,
         override_authorized, override_reason)
    VALUES
        (TG_TABLE_NAME, row_pk, op, before_json, after_json,
         hash_before, hash_after,
         current_user, actor,
         (override_on = 'on'),
         override_reason);

    RETURN COALESCE(NEW, OLD);
END;
$$;
"""


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()
    print("Deploy 247 — truth_audit trigger fix (dynamic PK per table)")
    print("=" * 60)
    cur.execute(PATCH_SQL)
    print("  ✓ truth_audit() rewritten with per-table PK extraction")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
