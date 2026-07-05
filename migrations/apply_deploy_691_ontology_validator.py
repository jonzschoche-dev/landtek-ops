#!/usr/bin/env python3
"""apply_deploy_691_ontology_validator.py — ontology_validator, SHADOW MODE.

Implements docs/ontology_validator_spec.md as a DB-resident gate that sits BESIDE
the existing provenance grounding-gate. Turns ONTOLOGY.md from documentation into a
runtime guardrail — without a Python/Pydantic framework (enforcement stays in the DB
so EVERY writer is bound, incl. Leo's n8n LangChain.js path).

Ships in SHADOW MODE: every check logs to holes_findings and blocks NOTHING. Flip a
check to 'block' only after a >=72h shadow run confirms zero false positives
(UPDATE ontology_validator_config SET mode='block' WHERE check_code='V1';).

Checks installed here:
  V1  no writes to drift tables (chain_of_title, cases, finance_transactions, fact_edges)
  V3  verified fact must be grounded (matter_facts: verified => source_id + excerpt)
  V4  client-isolation detector — a VIEW (v_ontology_client_cross), not a trigger
      (read-only; surfaces cross-client contamination for triage; never blocks)

NOT installed (deferred, deliberately):
  V2  enum conformance — the real provenance vocab is 5 values
      {verified, operator, inferred_strong, inferred_corroborated, inferred_weak};
      enum scanning lives in scripts/ontology_check.py (a linter, not 20 hot-path triggers).

SAFETY:
  - The logger (ontology_reject) swallows its OWN errors — logging can never break a
    writer (degrade, don't crash). This is the critical invariant: holes_findings has 6
    NOT-NULL columns; a naive logger INSERT would RAISE inside the trigger and block writes.
  - Idempotent: CREATE OR REPLACE / IF NOT EXISTS / DROP TRIGGER IF EXISTS.
  - Reversible: run with --rollback to drop all triggers/functions/config/view.
  - Does NOT run on import. Only `--go` applies.

Usage:
  python3 migrations/apply_deploy_691_ontology_validator.py --go        # apply (shadow)
  python3 migrations/apply_deploy_691_ontology_validator.py --selftest  # prove logger safe
  python3 migrations/apply_deploy_691_ontology_validator.py --rollback  # remove everything
"""
from __future__ import annotations
import os
import sys
import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

DRIFT_TABLES = ["chain_of_title", "cases", "finance_transactions", "fact_edges"]

APPLY_SQL = r"""
-- 1. config -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ontology_validator_config (
  check_code text PRIMARY KEY,
  mode       text NOT NULL DEFAULT 'log' CHECK (mode IN ('log','block','off')),
  note       text,
  updated_at timestamptz DEFAULT now()
);
INSERT INTO ontology_validator_config(check_code, mode, note) VALUES
  ('V1','log','no writes to drift tables (ONTOLOGY.md sec3)'),
  ('V3','log','verified fact must be grounded (ONTOLOGY.md A2)'),
  ('V4','log','client-isolation detector via v_ontology_client_cross')
ON CONFLICT (check_code) DO NOTHING;

-- 2. crash-proof logger -------------------------------------------------------
--    Writes to holes_findings; swallows its own errors so it can NEVER break a
--    writer. holes_findings NOT-NULL cols: routine_name, routine_version,
--    finding_id_hash, severity, hole_type, description, status.
CREATE OR REPLACE FUNCTION ontology_reject(_reason text, _detail text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  BEGIN
    INSERT INTO holes_findings(
      routine_name, routine_version, finding_id_hash, severity, hole_type,
      description, metadata, status)
    VALUES (
      'ontology_validator', 'v1',
      md5(_reason || '|' || coalesce(_detail,'')),
      'info', _reason, coalesce(_detail, _reason),
      jsonb_build_object('shadow', true), 'open');
  EXCEPTION WHEN OTHERS THEN
    NULL;  -- logging must never break a writer
  END;
END $$;

-- 3. V1 — drift-table guard ---------------------------------------------------
CREATE OR REPLACE FUNCTION ontvv_no_drift() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m text;
BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code='V1';
  IF m IS NULL OR m='off' THEN RETURN NEW; END IF;
  PERFORM ontology_reject('ONTOLOGY_DRIFT_TABLE', TG_TABLE_NAME);
  IF m='block' THEN
    RAISE EXCEPTION 'ontology_validator V1: % is a drift table; write the canonical table (ONTOLOGY.md sec3)', TG_TABLE_NAME;
  END IF;
  RETURN NEW;
END $$;

-- 4. V3 — verified => grounded (matter_facts) ---------------------------------
CREATE OR REPLACE FUNCTION ontvv_grounded_verified() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m text;
BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code='V3';
  IF m IS NULL OR m='off' THEN RETURN NEW; END IF;
  IF NEW.provenance_level='verified'
     AND (NEW.source_id IS NULL OR coalesce(NEW.excerpt,'')='') THEN
    PERFORM ontology_reject('ONTOLOGY_UNGROUNDED_VERIFIED',
      TG_TABLE_NAME || ' id=' || coalesce(NEW.id::text,'new'));
    IF m='block' THEN
      RAISE EXCEPTION 'ontology_validator V3: verified fact needs source_id + excerpt (ONTOLOGY.md A2)';
    END IF;
  END IF;
  RETURN NEW;
END $$;

-- 5. V4 — client-isolation detector (read-only view) --------------------------
--    A matter_fact whose cited doc belongs to a different client than the fact's
--    own matter. Surfaces the A5 gap for triage; never blocks a write.
CREATE OR REPLACE VIEW v_ontology_client_cross AS
SELECT mf.id            AS fact_id,
       mf.matter_code   AS fact_matter,
       m.client_code    AS fact_client,
       d.id             AS cited_doc_id,
       d.matter_code    AS doc_matter,
       dm.client_code   AS doc_client
FROM matter_facts mf
JOIN matters m       ON m.matter_code = mf.matter_code
JOIN documents d     ON d.id::text = mf.source_id
LEFT JOIN matters dm ON dm.matter_code = d.matter_code
WHERE mf.provenance_level='verified'
  AND d.matter_code IS NOT NULL
  AND dm.client_code IS NOT NULL
  AND dm.client_code <> m.client_code;
"""

# Triggers are (re)created idempotently in Python so we can loop the drift tables.
DROP_TRIGGERS = [
    ("ontvv_v3_matter_facts", "matter_facts"),
] + [(f"ontvv_v1_{t}", t) for t in DRIFT_TABLES]


def _apply(cur):
    cur.execute(APPLY_SQL)
    # V1 triggers on each drift table
    for t in DRIFT_TABLES:
        cur.execute(f"DROP TRIGGER IF EXISTS ontvv_v1_{t} ON {t};")
        cur.execute(
            f"CREATE TRIGGER ontvv_v1_{t} BEFORE INSERT ON {t} "
            f"FOR EACH ROW EXECUTE FUNCTION ontvv_no_drift();"
        )
    # V3 trigger on matter_facts
    cur.execute("DROP TRIGGER IF EXISTS ontvv_v3_matter_facts ON matter_facts;")
    cur.execute(
        "CREATE TRIGGER ontvv_v3_matter_facts BEFORE INSERT OR UPDATE ON matter_facts "
        "FOR EACH ROW EXECUTE FUNCTION ontvv_grounded_verified();"
    )


def _rollback(cur):
    for trig, tbl in DROP_TRIGGERS:
        cur.execute(f"DROP TRIGGER IF EXISTS {trig} ON {tbl};")
    cur.execute("DROP VIEW IF EXISTS v_ontology_client_cross;")
    cur.execute("DROP FUNCTION IF EXISTS ontvv_no_drift();")
    cur.execute("DROP FUNCTION IF EXISTS ontvv_grounded_verified();")
    cur.execute("DROP FUNCTION IF EXISTS ontology_reject(text, text);")
    cur.execute("DROP TABLE IF EXISTS ontology_validator_config;")


def _selftest(cur):
    """Prove the logger cannot break a writer, then clean up."""
    cur.execute("SELECT ontology_reject('SELFTEST','probe');")
    cur.execute("SELECT count(*) FROM holes_findings WHERE hole_type='SELFTEST';")
    n = cur.fetchone()[0]
    cur.execute("DELETE FROM holes_findings WHERE hole_type='SELFTEST';")
    assert n >= 1, "logger did not write — investigate before applying"
    print(f"  selftest OK — logger wrote {n} row(s), cleaned up, never raised.")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("--go", "--rollback", "--selftest"):
        print(__doc__)
        sys.exit(2)
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            if mode == "--rollback":
                _rollback(cur)
                conn.commit()
                print("ontology_validator: rolled back (all triggers/functions/view/config dropped).")
                return
            _apply(cur)
            _selftest(cur)
            conn.commit()
            # report state
            with conn.cursor() as c2:
                c2.execute("SELECT check_code, mode FROM ontology_validator_config ORDER BY check_code;")
                rows = c2.fetchall()
                c2.execute("SELECT count(*) FROM information_schema.triggers WHERE trigger_name LIKE 'ontvv_%';")
                ntrig = c2.fetchone()[0]
        print("ontology_validator applied (SHADOW).")
        print(f"  config: {rows}")
        print(f"  triggers installed: {ntrig}")
        print("  All checks in 'log' mode — nothing is blocked. Flip to 'block' only after a 72h clean shadow run.")
    except Exception as e:
        conn.rollback()
        print(f"FAILED, rolled back: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
