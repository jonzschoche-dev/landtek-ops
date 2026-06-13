-- Pillar 3 (Finance & Accounting) scaffold — ledger + per-matter P&L / ROI.
-- Additive, creditless. Bill/receipt EXTRACTION (LLM) and QuickBooks sync layer on later;
-- this is the durable structure so financial facts have a home + per-matter economics are queryable.
BEGIN;

CREATE TABLE IF NOT EXISTS finance_transactions (
    id           serial PRIMARY KEY,
    client_code  text,
    matter_code  text,
    txn_date     date,
    direction    text CHECK (direction IN ('debit','credit')),  -- debit=expense/outflow · credit=income/inflow
    amount       numeric(14,2),
    currency     text DEFAULT 'PHP',
    category     text,            -- filing_fee · professional_fee · transfer_tax · retainer · survey · BIR · ...
    counterparty text,
    description  text,
    source_doc_id int,            -- the bill/receipt/invoice row in documents (provenance)
    provenance_level text DEFAULT 'inferred_strong',
    created_at   timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fin_txn_matter ON finance_transactions(matter_code);
CREATE INDEX IF NOT EXISTS idx_fin_txn_date   ON finance_transactions(txn_date);

-- Per-matter profit & loss
CREATE OR REPLACE VIEW v_matter_pnl AS
SELECT coalesce(matter_code,'(unassigned)') AS matter_code,
       coalesce(client_code,'?')            AS client_code,
       coalesce(sum(amount) FILTER (WHERE direction='credit'),0) AS income,
       coalesce(sum(amount) FILTER (WHERE direction='debit'),0)  AS expense,
       coalesce(sum(amount) FILTER (WHERE direction='credit'),0)
         - coalesce(sum(amount) FILTER (WHERE direction='debit'),0) AS net,
       count(*)        AS txns,
       max(txn_date)   AS last_txn
  FROM finance_transactions
 GROUP BY 1,2;

-- Per-matter ROI (net return on spend)
CREATE OR REPLACE VIEW v_matter_roi AS
SELECT matter_code, client_code, income, expense, net,
       CASE WHEN expense > 0 THEN round(net / expense * 100, 1) END AS roi_pct
  FROM v_matter_pnl;

COMMIT;

SELECT 'finance scaffold ready: ' || count(*) || ' txns' FROM finance_transactions;
