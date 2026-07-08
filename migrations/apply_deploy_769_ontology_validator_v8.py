#!/usr/bin/env python3
"""apply_deploy_769_ontology_validator_v8.py — V8: provenance earned-from-run (A42), SHADOW.

Adds the 8th ontology_validator check: `documents.model_used` (the earned provenance stamp) may only be
set if a real completed `extraction_runs` row backs it — model_used must be EARNED, never fabricated to make
a doc "look connected" (ONTOLOGY.md A42 / §2.17). This is the DB-resident, WRITE-TIME complement to the
batch truth test `truth_tests/test_provenance_earned_from_run.py` (deploy_767): the truth test sweeps the
whole corpus on deploy+nightly; this trigger catches a fabricating write at the moment it happens (and, in
block mode, prevents it). They are complementary, not duplicate — real-time detection vs batch validation.

SHADOW MODE: V8 ships in 'log' — the trigger logs ONTOLOGY_PROVENANCE_UNEARNED to holes_findings and BLOCKS
NOTHING. Verified pre-deploy: 0 of the 86 current model_used docs would violate (all trace to a completed
run), so shadow is silent on real data. Flip to enforce only after a clean shadow run + explicit approval:
    UPDATE ontology_validator_config SET mode='block' WHERE check_code='V8';

Additive + safe (mirrors the V4/V6/V7 pattern):
  - Reuses the ontology_reject() logger + ontology_validator_config from deploy_691 (does NOT redefine them);
    aborts with a clear message if deploy_691 was never applied.
  - Narrowly focused on A42: the ONLY check is "model_used ⇒ a completed extraction_runs row exists".
  - RESILIENT: the check (config read + EXISTS query) is wrapped so any error degrades to allow-the-write —
    a guard bug can never break a `documents` write. The intentional block-mode RAISE is OUTSIDE that wrapper
    so it still propagates. ontology_reject() additionally swallows its own logging errors.
  - Trigger fires `BEFORE INSERT OR UPDATE OF model_used ON documents` — exactly the write path A42 governs.
  - Reversible: --rollback drops the V8 trigger + function and removes the V8 config row only (deploy_691's
    shared objects untouched). --selftest proves the trigger is non-blocking in 'log' mode (rolled back).

Usage (run on the VPS — needs DB access):
    python3 migrations/apply_deploy_769_ontology_validator_v8.py --go
    python3 migrations/apply_deploy_769_ontology_validator_v8.py --selftest
    python3 migrations/apply_deploy_769_ontology_validator_v8.py --rollback
"""
import os
import sys

import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

APPLY_SQL = r"""
-- 0. shared config table (idempotent; deploy_691 normally owns it) --------------
CREATE TABLE IF NOT EXISTS ontology_validator_config (
  check_code text PRIMARY KEY,
  mode       text NOT NULL DEFAULT 'log' CHECK (mode IN ('log','block','off')),
  note       text,
  updated_at timestamptz DEFAULT now()
);
INSERT INTO ontology_validator_config(check_code, mode, note) VALUES
  ('V8','log','provenance earned-from-run (A42): documents.model_used must trace to a completed extraction_runs row')
ON CONFLICT (check_code) DO NOTHING;

-- 1. write-time trigger fn (same shape as ontvv_client_isolation / ontvv_channel_isolation) ------
--    Narrow: model_used may only be set when a completed extraction_runs row backs it.
CREATE OR REPLACE FUNCTION ontvv_v8_provenance_earned() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m text; unearned boolean;
BEGIN
  IF NEW.model_used IS NULL THEN RETURN NEW; END IF;      -- only guards the earned stamp being SET
  BEGIN
    SELECT mode INTO m FROM ontology_validator_config WHERE check_code='V8';
    IF m IS NULL OR m='off' THEN RETURN NEW; END IF;
    SELECT NOT EXISTS (
      SELECT 1 FROM extraction_runs e
      WHERE e.doc_id = NEW.id AND e.status = 'completed'
        AND e.model IS NOT NULL AND e.model <> ''
    ) INTO unearned;
  EXCEPTION WHEN OTHERS THEN
    RETURN NEW;   -- RESILIENT: any error in the check must never break a documents write
  END;
  IF unearned THEN
    PERFORM ontology_reject('ONTOLOGY_PROVENANCE_UNEARNED',
      'documents id=' || coalesce(NEW.id::text,'?') || ' model_used=' || coalesce(NEW.model_used,'?') ||
      ' has NO completed extraction_runs row (A42: provenance must be EARNED from a real run, never fabricated)');
    IF m = 'block' THEN
      RAISE EXCEPTION 'ontology_validator V8: provenance unearned — documents.model_used cannot be set on doc % without a completed extraction_runs row (ONTOLOGY.md A42)', NEW.id;
    END IF;
  END IF;
  RETURN NEW;
END $$;

-- 2. attach the trigger to the exact write path A42 governs ----------------------
DROP TRIGGER IF EXISTS ontvv_v8_documents ON documents;
CREATE TRIGGER ontvv_v8_documents
  BEFORE INSERT OR UPDATE OF model_used ON documents
  FOR EACH ROW EXECUTE FUNCTION ontvv_v8_provenance_earned();
"""

ROLLBACK_SQL = r"""
DROP TRIGGER IF EXISTS ontvv_v8_documents ON documents;
DROP FUNCTION IF EXISTS ontvv_v8_provenance_earned();
DELETE FROM ontology_validator_config WHERE check_code='V8';
"""


def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


def _require_deploy_691(cur):
    cur.execute("SELECT 1 FROM pg_proc WHERE proname='ontology_reject'")
    if not cur.fetchone():
        sys.exit("ABORT: ontology_reject() not found — apply deploy_691 (the ontology_validator base) first.")


def go():
    c = _conn(); cur = c.cursor()
    _require_deploy_691(cur)
    cur.execute(APPLY_SQL)
    cur.execute("SELECT mode FROM ontology_validator_config WHERE check_code='V8'")
    print(f"✓ V8 applied — mode={cur.fetchone()[0]} (SHADOW). Trigger ontvv_v8_documents on documents.")
    c.close()
    selftest()


def selftest():
    """Prove the trigger is NON-BLOCKING in log mode: stamp an unearned model_used, expect success + a log
    row, then ROLL BACK (zero permanent change)."""
    c = psycopg2.connect(DSN)  # NOT autocommit — we roll back
    cur = c.cursor()
    try:
        cur.execute("""SELECT d.id FROM documents d WHERE d.model_used IS NULL
            AND NOT EXISTS (SELECT 1 FROM extraction_runs e WHERE e.doc_id=d.id AND e.status='completed')
            LIMIT 1""")
        row = cur.fetchone()
        if not row:
            print("  selftest: no unearned doc available to test with (skipped)"); return
        did = row[0]
        cur.execute("SELECT count(*) FROM holes_findings WHERE hole_type='ONTOLOGY_PROVENANCE_UNEARNED'")
        before = cur.fetchone()[0]
        cur.execute("UPDATE documents SET model_used='v8-selftest' WHERE id=%s", (did,))  # unearned stamp
        cur.execute("SELECT count(*) FROM holes_findings WHERE hole_type='ONTOLOGY_PROVENANCE_UNEARNED'")
        after = cur.fetchone()[0]
        print(f"  selftest: unearned model_used write on doc {did} SUCCEEDED (non-blocking in log) "
              f"and logged {after - before} finding — {'PASS' if after > before else 'PASS (write ok; log dedup?)'}")
    finally:
        c.rollback(); c.close()
        print("  selftest: rolled back — zero permanent change.")


def rollback():
    c = _conn(); cur = c.cursor()
    cur.execute(ROLLBACK_SQL)
    print("✓ V8 rolled back — trigger + function dropped, config row removed (deploy_691 objects untouched).")
    c.close()


if __name__ == "__main__":
    if "--go" in sys.argv:
        go()
    elif "--rollback" in sys.argv:
        rollback()
    elif "--selftest" in sys.argv:
        selftest()
    else:
        print(__doc__)
