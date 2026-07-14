-- deploy_915: Property readiness axes — what "prepare a property" means.
--
-- To prepare a property for profitability the continuous cycle must always work these six:
--   1. documents   — secure the paper (CTC, deeds, SPA, tax, court)
--   2. status      — understand operative status (active/cancelled/clouded/use)
--   3. occupants   — who is on the land / in the unit
--   4. ownership   — who owns / claims / has authority
--   5. title_issues— defects, liens, void chain, CARP, contest
--   6. mapping     — geometry, plot, area, boundaries
--
-- Matter is optional context. Prep never waits for a prompt.
-- Writer: scripts/profitability_prep_cycle.py

\set ON_ERROR_STOP on
BEGIN;

CREATE TABLE IF NOT EXISTS property_readiness (
  asset_code         text PRIMARY KEY REFERENCES property_assets(asset_code) ON DELETE CASCADE,
  client_code        text REFERENCES clients(client_code),
  -- Each axis: unknown | thin | partial | solid  (never invents "solid" without signal)
  documents          text NOT NULL DEFAULT 'unknown'
    CHECK (documents IN ('unknown','thin','partial','solid')),
  status_axis        text NOT NULL DEFAULT 'unknown'
    CHECK (status_axis IN ('unknown','thin','partial','solid')),
  occupants          text NOT NULL DEFAULT 'unknown'
    CHECK (occupants IN ('unknown','thin','partial','solid')),
  ownership          text NOT NULL DEFAULT 'unknown'
    CHECK (ownership IN ('unknown','thin','partial','solid')),
  title_issues       text NOT NULL DEFAULT 'unknown'
    CHECK (title_issues IN ('unknown','thin','partial','solid')),
  mapping            text NOT NULL DEFAULT 'unknown'
    CHECK (mapping IN ('unknown','thin','partial','solid')),
  -- Free-text snapshot (one line per axis for operators)
  documents_note     text,
  status_note        text,
  occupants_note     text,
  ownership_note     text,
  title_issues_note  text,
  mapping_note       text,
  readiness_score    numeric(5,4),   -- solid=1 partial=0.5 thin=0.25 unknown=0 average
  weakest_axis       text,
  next_prep_action   text,          -- single highest-priority prep from cycle
  assessed_at        timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_property_readiness_client ON property_readiness (client_code);
CREATE INDEX IF NOT EXISTS idx_property_readiness_weak ON property_readiness (weakest_axis, readiness_score);

-- Prep moves gain an axis column (nullable for back-compat with deploy_914 rows)
ALTER TABLE profitability_prep_moves
  ADD COLUMN IF NOT EXISTS axis text
  CHECK (axis IS NULL OR axis IN (
    'documents','status','occupants','ownership','title_issues','mapping','deal'
  ));

CREATE INDEX IF NOT EXISTS idx_prep_moves_axis
  ON profitability_prep_moves (axis) WHERE status = 'open';

CREATE OR REPLACE VIEW v_property_readiness_board AS
SELECT
  r.asset_code,
  r.client_code,
  a.label,
  a.origin,
  a.tier,
  a.title_ref,
  a.title_status,
  a.possession,
  r.documents,
  r.status_axis,
  r.occupants,
  r.ownership,
  r.title_issues,
  r.mapping,
  r.readiness_score,
  r.weakest_axis,
  r.next_prep_action,
  r.documents_note,
  r.status_note,
  r.occupants_note,
  r.ownership_note,
  r.title_issues_note,
  r.mapping_note,
  r.assessed_at
FROM property_readiness r
JOIN property_assets a ON a.asset_code = r.asset_code
ORDER BY r.readiness_score ASC NULLS FIRST, a.tier NULLS LAST, r.asset_code;

COMMIT;
