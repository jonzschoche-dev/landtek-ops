#!/usr/bin/env python3
"""deploy_121 — LLM cost-logging schema.

Creates llm_calls table + daily_llm_costs view + per-script-cost view.
Zero LLM cost. Pure SQL.
"""
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SQL = """
CREATE TABLE IF NOT EXISTS llm_calls (
  id                 bigserial PRIMARY KEY,
  called_at          timestamptz NOT NULL DEFAULT now(),
  vendor             text NOT NULL,           -- 'anthropic' | 'gemini' | 'openai'
  model              text NOT NULL,           -- 'claude-sonnet-4-6', 'gemini-2.5-flash', etc.
  called_from        text,                    -- script or function name
  purpose            text,                    -- 'truth_negotiator_challenger', 'tct_sweep', etc.
  input_tokens       integer,                 -- prompt tokens charged at input rate
  cached_input_tokens integer,                -- prompt-cache hits (cheaper rate)
  output_tokens      integer,                 -- response tokens
  cost_usd           numeric(10,6) NOT NULL,  -- computed at insert time
  duration_ms        integer,
  success            boolean NOT NULL DEFAULT true,
  prompt_hash        text,                    -- sha256 of system+user prompt for dedup analysis
  call_metadata      jsonb,                   -- vendor-specific extras
  case_file          text                     -- 'MWK-001' etc. for per-matter billing
);

CREATE INDEX IF NOT EXISTS idx_llm_calls_called_at      ON llm_calls(called_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_calls_model          ON llm_calls(model, called_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_calls_called_from    ON llm_calls(called_from, called_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_calls_case_file      ON llm_calls(case_file, called_at DESC);

-- Daily cost roll-up (UTC days)
CREATE OR REPLACE VIEW daily_llm_costs AS
SELECT
  date_trunc('day', called_at AT TIME ZONE 'UTC')::date AS day,
  vendor, model,
  COUNT(*) AS calls,
  SUM(input_tokens) AS in_tok,
  SUM(cached_input_tokens) AS cached_tok,
  SUM(output_tokens) AS out_tok,
  SUM(cost_usd) AS cost_usd
FROM llm_calls
GROUP BY 1,2,3
ORDER BY 1 DESC, cost_usd DESC;

-- Per-script roll-up
CREATE OR REPLACE VIEW script_llm_costs AS
SELECT
  date_trunc('day', called_at AT TIME ZONE 'UTC')::date AS day,
  called_from, purpose,
  COUNT(*) AS calls,
  SUM(input_tokens + COALESCE(cached_input_tokens,0)) AS in_tok,
  SUM(output_tokens) AS out_tok,
  SUM(cost_usd) AS cost_usd,
  AVG(duration_ms)::int AS avg_ms,
  SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) AS failures
FROM llm_calls
GROUP BY 1,2,3
ORDER BY 1 DESC, cost_usd DESC;

-- Today's summary
CREATE OR REPLACE VIEW today_llm_summary AS
SELECT
  vendor, model,
  COUNT(*) AS calls,
  SUM(cost_usd) AS cost_usd,
  SUM(input_tokens) AS in_tok,
  SUM(output_tokens) AS out_tok
FROM llm_calls
WHERE called_at >= date_trunc('day', NOW())
GROUP BY 1,2
ORDER BY cost_usd DESC;
"""

if __name__ == "__main__":
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SQL)
    cur.execute("SELECT COUNT(*) FROM llm_calls")
    n = cur.fetchone()[0]
    print(f"deploy_121: llm_calls + 3 views ready (current rows: {n})")
    cur.close(); conn.close()
