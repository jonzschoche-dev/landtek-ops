-- deploy_914: Continuous profitability preparation cycle (doctrine).
--
-- The engine prepares EVERY property for profitability on a standing loop —
-- not only when prompted, and not only when a controlling_matter is set.
-- Matter/forum attaches when the schedule calls for it; prep never waits on that.
--
-- Tables:
--   profitability_prep_moves  — open prep actions per asset/mode/precond (durable queue)
--   profitability_prep_cycles — cycle run log (heartbeat that the loop is alive)
--
-- Writer: scripts/profitability_prep_cycle.py (+ timer landtek-profitability-prep)
-- Reader: path-to-cash / digest / ops (later)
--
-- Respects: A5 (client_code), A74 (recheck_condition), A81–A84 (spine), A71 (metabolizable dose
-- via priority + caps). Does NOT auto-execute deals or outward actions (A21).

\set ON_ERROR_STOP on
BEGIN;

CREATE TABLE IF NOT EXISTS profitability_prep_moves (
  id                 bigserial PRIMARY KEY,
  client_code        text REFERENCES clients(client_code),
  asset_code         text NOT NULL REFERENCES property_assets(asset_code) ON DELETE CASCADE,
  -- matter_code is OPTIONAL context when a schedule/obligation attaches — never required to prep
  matter_code        text,
  mode               text,
  precond_code       text,
  action             text NOT NULL,
  why                text,
  recheck_condition  text,
  evidence_ref       text,
  priority           int NOT NULL DEFAULT 100,   -- lower = sooner
  status             text NOT NULL DEFAULT 'open'
    CHECK (status IN ('open','done','superseded','held')),
  origin             text NOT NULL DEFAULT 'prep_cycle',
  -- Stable identity for upsert: asset|mode|precond|action (matter NOT in key — optional context)
  move_key           text NOT NULL,
  last_seen_at       timestamptz NOT NULL DEFAULT now(),
  closed_at          timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (move_key)
);

CREATE INDEX IF NOT EXISTS idx_prep_moves_open
  ON profitability_prep_moves (status, priority, last_seen_at)
  WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_prep_moves_client
  ON profitability_prep_moves (client_code) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_prep_moves_asset
  ON profitability_prep_moves (asset_code) WHERE status = 'open';

CREATE TABLE IF NOT EXISTS profitability_prep_cycles (
  id              bigserial PRIMARY KEY,
  started_at      timestamptz NOT NULL DEFAULT now(),
  finished_at     timestamptz,
  assets_seen     int,
  moves_open      int,
  moves_upserted  int,
  moves_closed    int,
  note            text
);

CREATE OR REPLACE VIEW v_profitability_momentum AS
SELECT
  m.priority,
  m.client_code,
  m.asset_code,
  a.label AS asset_label,
  a.origin,
  a.tier,
  a.title_status,
  m.mode,
  m.precond_code,
  m.action,
  m.why,
  m.recheck_condition,
  m.matter_code,
  m.last_seen_at
FROM profitability_prep_moves m
JOIN property_assets a ON a.asset_code = m.asset_code
WHERE m.status = 'open'
ORDER BY m.priority ASC, m.last_seen_at DESC;

COMMIT;
