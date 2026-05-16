#!/usr/bin/env python3
"""Deploy 113-B — Asset risk + evolving-assessment schema.

Adds:
  asset_risks                — per-asset risk rows (append-only, versioned)
  risk_change_events         — what triggered each risk re-eval
  valuation_change_events    — what triggered each valuation re-eval
  next_review_due on existing asset_valuations
  helper view: asset_current_risks (latest row per (asset,risk_type))
  helper view: asset_current_valuation (latest snapshot per asset)
"""
import psycopg2
DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SQL = r"""
CREATE TABLE IF NOT EXISTS asset_risks (
  id                serial PRIMARY KEY,
  asset_title       text NOT NULL,
  case_file         text,
  assessed_at       timestamptz DEFAULT now(),
  risk_type         text NOT NULL,
  severity          text NOT NULL,        -- 'critical','high','medium','low'
  likelihood_pct    numeric(5,2),         -- 0..100
  expected_loss_php numeric(14,2),
  mitigation_strategy text,
  mitigation_status text DEFAULT 'unaddressed',  -- 'unaddressed','planning','in_progress','partial','eliminated'
  mitigation_cost   numeric(14,2),
  learned_from_case text,
  evidence_doc_ids  integer[],
  internal_only     boolean DEFAULT true,
  next_review_due   date,
  notes             text,
  provenance_level  text DEFAULT 'inferred_strong'
);
CREATE INDEX IF NOT EXISTS idx_ar_asset ON asset_risks(asset_title, assessed_at DESC);
CREATE INDEX IF NOT EXISTS idx_ar_review_due ON asset_risks(next_review_due) WHERE mitigation_status != 'eliminated';

CREATE TABLE IF NOT EXISTS risk_change_events (
  id              serial PRIMARY KEY,
  asset_title     text NOT NULL,
  case_file       text,
  risk_type       text,
  event_type      text NOT NULL,    -- 'new_doc','court_order','heir_dispute','spa_revoked','tax_delinquency','market_signal','review_cycle','manual'
  source_doc_id   integer REFERENCES documents(id) ON DELETE SET NULL,
  old_severity    text,
  new_severity    text,
  old_expected_loss numeric(14,2),
  new_expected_loss numeric(14,2),
  delta_php       numeric(14,2),
  triggered_at    timestamptz DEFAULT now(),
  notes           text
);
CREATE INDEX IF NOT EXISTS idx_rce_asset ON risk_change_events(asset_title, triggered_at DESC);

CREATE TABLE IF NOT EXISTS valuation_change_events (
  id              serial PRIMARY KEY,
  asset_title     text NOT NULL,
  case_file       text,
  event_type      text NOT NULL,    -- 'new_tax_dec','zonal_update','appraisal','market_observation','review_cycle','manual'
  source_doc_id   integer REFERENCES documents(id) ON DELETE SET NULL,
  old_mpv         numeric(14,2),
  new_mpv         numeric(14,2),
  old_assessed    numeric(14,2),
  new_assessed    numeric(14,2),
  delta_php       numeric(14,2),
  delta_pct       numeric(7,2),
  triggered_at    timestamptz DEFAULT now(),
  notes           text
);
CREATE INDEX IF NOT EXISTS idx_vce_asset ON valuation_change_events(asset_title, triggered_at DESC);

ALTER TABLE asset_valuations
  ADD COLUMN IF NOT EXISTS next_review_due date,
  ADD COLUMN IF NOT EXISTS intrinsic_value numeric(14,2),  -- mpv - sum(risk-weighted losses)
  ADD COLUMN IF NOT EXISTS opportunity_score real;          -- 0..1, low_hanging_fruit indicator

CREATE OR REPLACE VIEW asset_current_risks AS
SELECT DISTINCT ON (asset_title, risk_type)
       asset_title, risk_type, severity, likelihood_pct, expected_loss_php,
       mitigation_strategy, mitigation_status, mitigation_cost,
       next_review_due, evidence_doc_ids, assessed_at
  FROM asset_risks
 ORDER BY asset_title, risk_type, assessed_at DESC;

CREATE OR REPLACE VIEW asset_current_valuation AS
SELECT DISTINCT ON (asset_title)
       asset_title, case_file, snapshot_date, tax_dec_no,
       assessed_value, zonal_value, market_price_value, appraised_value,
       acquisition_cost, current_use, highest_best_use,
       intrinsic_value, opportunity_score, next_review_due
  FROM asset_valuations
 ORDER BY asset_title, snapshot_date DESC;

CREATE OR REPLACE VIEW asset_opportunity_signals AS
SELECT
  v.asset_title, v.case_file,
  v.market_price_value, v.intrinsic_value, v.opportunity_score,
  (v.intrinsic_value - v.market_price_value) AS upside_php,
  CASE WHEN v.market_price_value > 0 THEN
    round(((v.intrinsic_value - v.market_price_value) / v.market_price_value) * 100, 1)
  END AS upside_pct,
  v.next_review_due
FROM asset_current_valuation v
WHERE v.intrinsic_value IS NOT NULL
  AND v.market_price_value IS NOT NULL
  AND v.intrinsic_value > v.market_price_value
ORDER BY v.opportunity_score DESC NULLS LAST;
"""


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    print("  → applying risk + evolving-assessment schema …")
    cur.execute(SQL)
    for tbl in ("asset_risks","risk_change_events","valuation_change_events"):
        cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name=%s",(tbl,))
        print(f"    {'✓' if cur.fetchone() else '✗'} {tbl}")
    for v in ("asset_current_risks","asset_current_valuation","asset_opportunity_signals"):
        cur.execute("SELECT 1 FROM information_schema.views WHERE table_name=%s",(v,))
        print(f"    {'✓' if cur.fetchone() else '✗'} view {v}")
    cur.close(); conn.close()
    print("  ✓ deploy_113-B schema complete")


if __name__ == "__main__":
    main()
