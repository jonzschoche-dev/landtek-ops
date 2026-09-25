-- Improvement Lab — config-versioned Leo + A/B promotion ledger (docs/TRUTH_LAYER_FITNESS_SPEC.md Part II).
-- Additive, idempotent. Builds on the v1 foundation (eval_scenario / eval_result / compounding_metric) with NO
-- change to the foundation schema (A9). Floors are enforced HERE, in the DB — not by code convention:
--   * leo_config.body is content-addressed + immutable; a body naming a constitutional floor is refused.
--   * exactly one active config (partial unique index); rollback = flip to prev_config_id.
--   * the A/B report, the promotion audit and the experience ledger are append-only (tlfh_append_only trigger).
BEGIN;

-- ── A1: leo_config@N — the versioned assistant ─────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION leo_config_key_count(b jsonb) RETURNS int
  LANGUAGE sql IMMUTABLE AS $$ SELECT count(*)::int FROM jsonb_object_keys(b) $$;

CREATE TABLE IF NOT EXISTS leo_config (
  id               BIGSERIAL PRIMARY KEY,
  config_hash      TEXT NOT NULL UNIQUE,            -- sha256 of canonical JSON body (content address)
  body             JSONB NOT NULL,
  status           TEXT NOT NULL DEFAULT 'candidate'
                   CHECK (status IN ('candidate','active','retired','rejected')),
  active           BOOLEAN NOT NULL DEFAULT false,
  parent_config_id BIGINT REFERENCES leo_config(id), -- the config a candidate was derived from
  prev_config_id   BIGINT REFERENCES leo_config(id), -- rollback pointer, set when this row is activated
  note             TEXT,
  created_by       TEXT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  activated_at     TIMESTAMPTZ,
  CONSTRAINT leo_config_active_matches_status CHECK (active = (status = 'active')),
  -- A1: exactly the seven versioned sections, nothing else at the top level
  CONSTRAINT leo_config_sections CHECK (
    body ?& ARRAY['prompt_set','tool_manifest','retrieval_params','routing','model_selection',
                  'memory_context_assembly','recipient_projection']
    AND leo_config_key_count(body) = 7),
  -- A2: a candidate cannot even NAME a constitutional floor (truth / isolation / outward / role clamp)
  CONSTRAINT leo_config_no_floor_keys CHECK (
    body::text !~* '"(answer_gate|outward_guard|client_of|provenance[a-z_]*|send[a-z_]*|test_identities|inquiry_gate|stack_first|role_clamp|channel_mode|a5|a21|a25|a79)"\s*:')
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_leo_config_one_active ON leo_config ((true)) WHERE active;

-- body + hash are immutable (content-addressed); rows are never deleted (the rollback chain must survive)
CREATE OR REPLACE FUNCTION leo_config_guard() RETURNS trigger AS $fn$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'leo_config rows are never deleted (rollback chain)';
  END IF;
  IF NEW.body IS DISTINCT FROM OLD.body OR NEW.config_hash IS DISTINCT FROM OLD.config_hash THEN
    RAISE EXCEPTION 'leo_config body/config_hash are immutable — create a new candidate instead';
  END IF;
  RETURN NEW;
END; $fn$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_leo_config_guard ON leo_config;
CREATE TRIGGER trg_leo_config_guard BEFORE UPDATE OR DELETE ON leo_config
  FOR EACH ROW EXECUTE FUNCTION leo_config_guard();

-- ── A3/A4/A5: the A/B report (append-only, content-hashed) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lab_ab_report (
  id             BIGSERIAL PRIMARY KEY,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  config_a_id    BIGINT NOT NULL REFERENCES leo_config(id),
  config_b_id    BIGINT NOT NULL REFERENCES leo_config(id),
  config_a_hash  TEXT NOT NULL,
  config_b_hash  TEXT NOT NULL,
  cohorts        TEXT[] NOT NULL,
  n_scenarios    INT NOT NULL,
  summary        JSONB NOT NULL,      -- per-config, per-cohort axis rollup + deltas
  new_critical   JSONB NOT NULL,      -- [(scenario, axis)] that passed on A and fail on B — any row rejects
  preexisting    JSONB NOT NULL,      -- critical failures present on BOTH (not caused by B; reported, not blocking)
  improvements   JSONB NOT NULL,
  verdict        TEXT NOT NULL CHECK (verdict IN ('promotable','rejected','no_improvement','not_comparable')),
  reasons        JSONB NOT NULL,
  fingerprint_a  JSONB NOT NULL,
  fingerprint_b  JSONB NOT NULL,
  config_diff    JSONB NOT NULL,
  report_hash    TEXT NOT NULL,       -- sha256 over the canonical report content (tamper-evident)
  run_by         TEXT NOT NULL
);

-- ── A5: promotion / rollback audit (append-only) ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS leo_config_audit (
  id             BIGSERIAL PRIMARY KEY,
  at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  action         TEXT NOT NULL CHECK (action IN ('seed','promote','rollback','reject')),
  from_config_id BIGINT REFERENCES leo_config(id),
  to_config_id   BIGINT REFERENCES leo_config(id),
  report_id      BIGINT REFERENCES lab_ab_report(id),
  actor          TEXT NOT NULL,
  fingerprints   JSONB,
  config_diff    JSONB,
  reason         TEXT
);

-- ── A6: experience ledger — what ACTUALLY worked, measured + attributable (append-only) ─────────────
CREATE TABLE IF NOT EXISTS lab_experience (
  id             BIGSERIAL PRIMARY KEY,
  at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  report_id      BIGINT REFERENCES lab_ab_report(id),
  from_config_id BIGINT REFERENCES leo_config(id),
  to_config_id   BIGINT REFERENCES leo_config(id),
  outcome        TEXT NOT NULL CHECK (outcome IN ('promoted','rejected','rolled_back')),
  config_diff    JSONB,
  measured       JSONB,               -- the report's measured deltas (never a prediction)
  note           TEXT
);

DROP TRIGGER IF EXISTS trg_lab_report_append_only ON lab_ab_report;
CREATE TRIGGER trg_lab_report_append_only BEFORE UPDATE OR DELETE ON lab_ab_report
  FOR EACH ROW EXECUTE FUNCTION tlfh_append_only();
DROP TRIGGER IF EXISTS trg_leo_config_audit_append_only ON leo_config_audit;
CREATE TRIGGER trg_leo_config_audit_append_only BEFORE UPDATE OR DELETE ON leo_config_audit
  FOR EACH ROW EXECUTE FUNCTION tlfh_append_only();
DROP TRIGGER IF EXISTS trg_lab_experience_append_only ON lab_experience;
CREATE TRIGGER trg_lab_experience_append_only BEFORE UPDATE OR DELETE ON lab_experience
  FOR EACH ROW EXECUTE FUNCTION tlfh_append_only();

-- ── a broken scenario is retired with its reason, never deleted (eval_result rows reference it) ───────
ALTER TABLE eval_scenario ADD COLUMN IF NOT EXISTS retired_reason TEXT;

-- ── attribution: which config produced each live Leo reply ─────────────────────────────────────────
ALTER TABLE leo_shadow_replies ADD COLUMN IF NOT EXISTS leo_config_hash TEXT;

-- ── A7: re-point the existing proposal ledger at leo_config (reuse the contract, retire the n8n runtime) ─
ALTER TABLE leo_improvement_proposals ADD COLUMN IF NOT EXISTS leo_config_id BIGINT REFERENCES leo_config(id);
ALTER TABLE leo_improvement_proposals ADD COLUMN IF NOT EXISTS lab_report_id BIGINT REFERENCES lab_ab_report(id);
ALTER TABLE leo_improvement_proposals DROP CONSTRAINT IF EXISTS lip_kind_check;
ALTER TABLE leo_improvement_proposals ADD CONSTRAINT lip_kind_check CHECK (patch_kind = ANY (ARRAY[
  'system_prompt_add','system_prompt_replace','context_builder_add','tool_description','rule_clause',
  'leo_config']));

-- ── privileges: the A/B runner writes its ledger as the read-only harness role ─────────────────────
-- (promotion/rollback run as the owner role and are human-gated in improvement_lab.py)
-- the harness is SELECT-everywhere by spec; tables created since the July grant (e.g. document_fields) had
-- drifted out of reach. Read-only — fact-table writes stay REVOKEd.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO tlfh_harness;
GRANT UPDATE (retired_reason) ON eval_scenario TO tlfh_harness;
GRANT INSERT ON lab_ab_report TO tlfh_harness;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO tlfh_harness;

COMMIT;
