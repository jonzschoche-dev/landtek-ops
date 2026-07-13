-- Truth-Layer Fitness Harness — v1 foundation ledger (docs/TRUTH_LAYER_FITNESS_SPEC.md, Part I).
-- Additive, idempotent. Read-only on facts (enforced by a restricted role), append-only on the ledgers
-- (enforced by a guard trigger — not by code convention). NOT the dead §6A simulator: mechanical, $0.
BEGIN;

-- ── object registry: any truth-layer object under test (domain-agnostic) ────────────────────────────
CREATE TABLE IF NOT EXISTS fitness_object (
  id          BIGSERIAL PRIMARY KEY,
  domain      TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_id   TEXT NOT NULL,
  client_code TEXT,
  first_seen  TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_graded TIMESTAMPTZ,
  UNIQUE (domain, object_type, object_id)
);

-- ── per-cycle rollup + fingerprint + self-reported kill-criteria ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS fitness_cycle (
  id            BIGSERIAL PRIMARY KEY,
  domain        TEXT NOT NULL,
  cohort        TEXT,
  cycle_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  n_objects     INT,
  per_dimension JSONB,
  fingerprint   JSONB,
  kill_criteria JSONB,
  notes         TEXT
);

-- ── APPEND-ONLY: one row per object × dimension × sub-measure × cycle ────────────────────────────────
CREATE TABLE IF NOT EXISTS fitness_measurement (
  id              BIGSERIAL PRIMARY KEY,
  cycle_id        BIGINT REFERENCES fitness_cycle(id),
  object_pk       BIGINT NOT NULL REFERENCES fitness_object(id),
  dimension       TEXT NOT NULL,
  submeasure      TEXT NOT NULL,
  value           TEXT NOT NULL,
  numeric_val     NUMERIC,
  basis           JSONB,
  weakness_target JSONB,          -- named remediation when the submeasure fails; NULL = clean, no noise
  prev_value      TEXT,           -- prior value for this (object,dim,submeasure) → regression/stale signal
  cycle_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fitmeas_obj   ON fitness_measurement(object_pk, dimension, submeasure);
CREATE INDEX IF NOT EXISTS idx_fitmeas_cycle ON fitness_measurement(cycle_id);

-- ── the grounded evaluation set (four cohorts; scored by the Lab, scaffolded here) ───────────────────
CREATE TABLE IF NOT EXISTS eval_scenario (
  id              BIGSERIAL PRIMARY KEY,
  scenario_key    TEXT UNIQUE,
  cohort          TEXT NOT NULL,   -- frozen_core | sealed_holdout | rolling_real_failures | adversarial_mutation
  domain          TEXT NOT NULL,
  object_ref      TEXT,
  prompt          TEXT NOT NULL,
  expected        JSONB NOT NULL,  -- typed props: evidence_docs, exact_values, required_holds, prohibited, provenance
  human_review    BOOLEAN NOT NULL DEFAULT false,
  ruleset_version TEXT,
  created_from    TEXT,
  sealed          BOOLEAN NOT NULL DEFAULT false,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── APPEND-ONLY: one row per scenario × assistant-config × run (Lab consumes this) ───────────────────
CREATE TABLE IF NOT EXISTS eval_result (
  id                BIGSERIAL PRIMARY KEY,
  scenario_id       BIGINT NOT NULL REFERENCES eval_scenario(id),
  assistant_config  TEXT NOT NULL,
  run_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  per_axis          JSONB,
  passed_mechanical BOOLEAN,
  human_verdict     TEXT,
  fingerprint       JSONB
);

-- ── measured proof of compounding leverage (never a claim without a row) ─────────────────────────────
CREATE TABLE IF NOT EXISTS compounding_metric (
  id            BIGSERIAL PRIMARY KEY,
  metric        TEXT NOT NULL,   -- docs_improved_per_fix | attributable_improvement | recurrence_reduction | time_to_usable_data
  numeric_val   NUMERIC,
  metric_window TEXT,
  attributed_to TEXT,
  fingerprint   JSONB,
  measured_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── append-only guard on the two ledgers (block UPDATE/DELETE at the DB, not in code) ────────────────
CREATE OR REPLACE FUNCTION tlfh_append_only() RETURNS trigger AS $fn$
BEGIN
  RAISE EXCEPTION 'append-only ledger: % on % is forbidden', TG_OP, TG_TABLE_NAME;
END; $fn$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_fitmeas_append_only ON fitness_measurement;
CREATE TRIGGER trg_fitmeas_append_only BEFORE UPDATE OR DELETE ON fitness_measurement
  FOR EACH ROW EXECUTE FUNCTION tlfh_append_only();
DROP TRIGGER IF EXISTS trg_evalresult_append_only ON eval_result;
CREATE TRIGGER trg_evalresult_append_only BEFORE UPDATE OR DELETE ON eval_result
  FOR EACH ROW EXECUTE FUNCTION tlfh_append_only();

-- ── restricted role: SELECT everywhere + INSERT on the ledger; NO writes to fact tables ──────────────
-- The harness connects as n8n then `SET ROLE tlfh_harness`, so every statement runs under these limits.
DO $role$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='tlfh_harness') THEN
    CREATE ROLE tlfh_harness NOLOGIN;
  END IF;
END $role$;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO tlfh_harness;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO tlfh_harness;
GRANT INSERT ON fitness_object, fitness_measurement, fitness_cycle,
                eval_scenario, eval_result, compounding_metric TO tlfh_harness;
GRANT UPDATE ON fitness_object TO tlfh_harness;   -- registry last_graded only (not a ledger, not a fact)
GRANT UPDATE ON eval_scenario  TO tlfh_harness;   -- scenario scaffolding refresh (not a fact; not append-only)
GRANT tlfh_harness TO n8n;                         -- let the harness SET ROLE into it

COMMIT;
