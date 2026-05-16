#!/usr/bin/env python3
"""Deploy 113 — Financial planning + asset valuation schema.

Two ledgers + per-asset valuation + market modeling, all under the same
truth-graded discipline (every figure cites a doc).

Tables:
  accounts                   — chart of accounts (revenue/expense/asset/liability)
  transactions               — every money event with source doc citation
  monthly_overhead           — recurring obligations per case + firm
  value_extraction_events    — sale, lease, settlement, recovery (per client)
  asset_valuations           — per-title time-series (tax_dec/assessed/zonal/MPV)
  asset_development_plans    — playbook per asset
  market_observations        — comparables + distressed-sale signals
  financial_projections      — runway, cash-flow, scenario models
  expense_ledger             — Leo's own operational costs (API, server, etc.)

Idempotent.
"""
import psycopg2
DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SQL = r"""
-- ============================================================
-- Chart of accounts (per client + per firm)
-- ============================================================
CREATE TABLE IF NOT EXISTS accounts (
  id              serial PRIMARY KEY,
  account_code    text UNIQUE NOT NULL,
  account_name    text NOT NULL,
  account_type    text NOT NULL,  -- 'revenue' | 'expense' | 'asset' | 'liability' | 'equity'
  owner           text NOT NULL,  -- 'landtek' | client_code (e.g., 'MWK-001')
  case_file       text,           -- nullable; if null, account is firm-level
  currency        text DEFAULT 'PHP',
  is_active       boolean DEFAULT true,
  notes           text,
  created_at      timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_accounts_owner ON accounts(owner, account_type);

-- ============================================================
-- Transactions — every money event needs a source doc
-- ============================================================
CREATE TABLE IF NOT EXISTS transactions (
  id              serial PRIMARY KEY,
  tx_date         date NOT NULL,
  account_id      integer REFERENCES accounts(id),
  case_file       text,
  matter_code     text,
  amount          numeric(14,2) NOT NULL,
  direction       text NOT NULL,   -- 'debit' | 'credit'
  category        text,            -- 'retainer','filing_fee','notary','sheriff','transport','salary','api_spend','rent','utility','revenue','refund','other'
  description     text,
  source_doc_id   integer REFERENCES documents(id) ON DELETE SET NULL,
  source_tx_ref   text,            -- OR number, invoice no, bank-ref
  provenance_level text DEFAULT 'inferred_strong',  -- 'verified' if cited to executed doc
  counterparty    text,
  payment_method  text,            -- 'cash' | 'bank' | 'gcash' | 'check' | 'wire'
  notes           text,
  created_at      timestamptz DEFAULT now(),
  created_by      text DEFAULT 'system'
);
CREATE INDEX IF NOT EXISTS idx_tx_date_case ON transactions(tx_date DESC, case_file);
CREATE INDEX IF NOT EXISTS idx_tx_account ON transactions(account_id, tx_date DESC);
CREATE INDEX IF NOT EXISTS idx_tx_source_doc ON transactions(source_doc_id) WHERE source_doc_id IS NOT NULL;

-- ============================================================
-- Monthly overhead — recurring obligations
-- ============================================================
CREATE TABLE IF NOT EXISTS monthly_overhead (
  id              serial PRIMARY KEY,
  owner           text NOT NULL,   -- 'landtek' | client_code
  case_file       text,
  category        text NOT NULL,   -- 'rent','utility','salary','server','api_anthropic','api_gemini','software','retainer_obligation','rpt','other'
  description     text,
  monthly_amount  numeric(14,2) NOT NULL,
  start_date      date NOT NULL,
  end_date        date,
  source_doc_id   integer REFERENCES documents(id) ON DELETE SET NULL,
  is_active       boolean DEFAULT true,
  created_at      timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_overhead_owner ON monthly_overhead(owner, is_active);

-- ============================================================
-- Value extraction events — sale, lease, settlement, recovery
-- ============================================================
CREATE TABLE IF NOT EXISTS value_extraction_events (
  id              serial PRIMARY KEY,
  event_date      date NOT NULL,
  case_file       text,
  asset_title     text,            -- TCT/OCT number if asset-tied
  event_type      text NOT NULL,   -- 'sale','lease','settlement','recovery','damages','tax_refund','eminent_domain','rent'
  gross_amount    numeric(14,2),
  net_to_client   numeric(14,2),
  landtek_share   numeric(14,2),   -- success fee / share
  currency        text DEFAULT 'PHP',
  counterparty    text,
  source_doc_id   integer REFERENCES documents(id) ON DELETE SET NULL,
  provenance_level text DEFAULT 'inferred_strong',
  description     text,
  created_at      timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_vee_case ON value_extraction_events(case_file, event_date DESC);

-- ============================================================
-- Asset valuations — per-title time-series
-- ============================================================
CREATE TABLE IF NOT EXISTS asset_valuations (
  id                 serial PRIMARY KEY,
  asset_title        text NOT NULL,           -- TCT/OCT number
  case_file          text,
  snapshot_date      date NOT NULL,
  tax_dec_no         text,
  assessed_value     numeric(14,2),
  zonal_value        numeric(14,2),
  market_price_value numeric(14,2),
  appraised_value    numeric(14,2),
  acquisition_cost   numeric(14,2),
  current_use        text,                    -- 'agricultural','residential','commercial','idle','mixed'
  highest_best_use   text,
  liens_encumbrances text,
  tax_status         text,                    -- 'current','delinquent','under_protest','exempt'
  area_sqm           numeric(12,2),
  per_sqm_assessed   numeric(14,2),
  per_sqm_market     numeric(14,2),
  source_docs        integer[],               -- backing docs
  provenance_level   text DEFAULT 'inferred_strong',
  notes              text,
  created_at         timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_av_title_date ON asset_valuations(asset_title, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_av_case ON asset_valuations(case_file);

-- ============================================================
-- Asset development plans — playbook per asset
-- ============================================================
CREATE TABLE IF NOT EXISTS asset_development_plans (
  id                serial PRIMARY KEY,
  asset_title       text NOT NULL,
  case_file         text,
  plan_name         text NOT NULL,
  plan_goal         text NOT NULL,             -- per client + per Landtek role
  client_goal_id    integer REFERENCES client_goals(id) ON DELETE SET NULL,
  firm_goal_id      integer REFERENCES firm_goals(id) ON DELETE SET NULL,
  horizon           text DEFAULT 'mid_term',   -- 'short_term' | 'mid_term' | 'long_term'
  required_investment numeric(14,2),
  expected_revenue  numeric(14,2),
  expected_roi_pct  numeric(6,2),
  expected_timeline_months integer,
  risk_factors      text,
  status            text DEFAULT 'proposed',   -- 'proposed' | 'active' | 'on_hold' | 'completed' | 'abandoned'
  next_milestone    text,
  next_milestone_date date,
  notes             text,
  created_at        timestamptz DEFAULT now(),
  updated_at        timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_adp_asset ON asset_development_plans(asset_title, status);
CREATE INDEX IF NOT EXISTS idx_adp_case ON asset_development_plans(case_file, status);

-- ============================================================
-- Market observations — comparables + distressed signals
-- ============================================================
CREATE TABLE IF NOT EXISTS market_observations (
  id              serial PRIMARY KEY,
  observed_at     date NOT NULL,
  area_code       text,                  -- e.g., 'Camarines Norte', 'Brgy San Roque, Daet'
  observation_type text NOT NULL,        -- 'comparable_sale','distressed_sale','foreclosure','tax_auction','listing','zonal_update','market_rumor'
  asset_title     text,                  -- if tied to specific title
  area_sqm        numeric(12,2),
  price           numeric(14,2),
  per_sqm         numeric(14,2),
  source          text,                  -- 'BIR zonal table','newspaper','RD listing','word_of_mouth','MLS','assessor_records'
  source_doc_id   integer REFERENCES documents(id) ON DELETE SET NULL,
  is_depressed_signal boolean DEFAULT false,
  confidence      real DEFAULT 0.5,
  notes           text,
  created_at      timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mo_area_type ON market_observations(area_code, observation_type, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_mo_depressed ON market_observations(is_depressed_signal) WHERE is_depressed_signal;

-- ============================================================
-- Financial projections — runway + scenarios
-- ============================================================
CREATE TABLE IF NOT EXISTS financial_projections (
  id              serial PRIMARY KEY,
  owner           text NOT NULL,         -- 'landtek' | client_code
  projection_date date NOT NULL,
  horizon_months  integer NOT NULL,
  scenario        text NOT NULL,         -- 'base','optimistic','pessimistic','runway'
  starting_cash   numeric(14,2),
  monthly_burn    numeric(14,2),
  monthly_revenue numeric(14,2),
  runway_months   numeric(6,1),
  ending_cash     numeric(14,2),
  assumptions     text,
  created_at      timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fp_owner ON financial_projections(owner, projection_date DESC);

-- ============================================================
-- Expense ledger — Leo's own operational costs (API spend, server, etc.)
-- ============================================================
CREATE TABLE IF NOT EXISTS leo_operational_costs (
  id              serial PRIMARY KEY,
  cost_date       date NOT NULL,
  category        text NOT NULL,         -- 'anthropic_api','gemini_api','openai_api','vps_server','storage','domain','telegram','other'
  amount_usd      numeric(10,4),
  amount_php      numeric(14,2),
  units           numeric(14,4),         -- tokens, requests, GB
  notes           text,
  source          text DEFAULT 'manual', -- 'manual' | 'api_billing' | 'estimate'
  created_at      timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_loc_date ON leo_operational_costs(cost_date DESC, category);
"""


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    print("  → applying financial schema …")
    cur.execute(SQL)
    checks = [
        "accounts", "transactions", "monthly_overhead",
        "value_extraction_events", "asset_valuations",
        "asset_development_plans", "market_observations",
        "financial_projections", "leo_operational_costs",
    ]
    for tbl in checks:
        cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name=%s", (tbl,))
        ok = cur.fetchone() is not None
        print(f"    {'✓' if ok else '✗'} {tbl}")
    cur.close(); conn.close()
    print("  ✓ deploy_113 schema complete")


if __name__ == "__main__":
    main()
