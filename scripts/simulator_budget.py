#!/usr/bin/env python3
"""simulator_budget.py — circuit breaker for the lean simulator (deploy_337).

Hard cap: $1/day token spend on simulator activity.
Tracker stores per-day spend; budget_check() returns False when ceiling hit
so callers skip further LLM-using probes that day.

Used by: micro_probe_runner.py, trigger_check.py, shadow_real_traffic.py
(though shadow doesn't call LLM, it still logs $0 calls for accounting).

Pricing (Anthropic, late 2025):
  claude-sonnet-4-5    $3.00/MT input + $15/MT output
  claude-haiku-4-5     $0.80/MT input +  $4/MT output

Usage:
  from simulator_budget import ensure_schema, can_afford, record_call, daily_total

  ensure_schema(cur)
  if can_afford(cur, est_input_tokens=10000, est_output_tokens=500, model='claude-sonnet-4-5'):
      # ... call API ...
      record_call(cur, model='claude-sonnet-4-5',
                  input_tokens=actual_in, output_tokens=actual_out,
                  source='micro_probe', detail='probe_name=...')
"""
from __future__ import annotations
import os
from datetime import date
import psycopg2, psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
DAILY_BUDGET_USD = 1.00

PRICES = {
    "claude-sonnet-4-5": {"in": 3.00, "out": 15.00},
    "claude-sonnet-4-5-20251022": {"in": 3.00, "out": 15.00},
    "claude-haiku-4-5":  {"in": 0.80, "out":  4.00},
    "claude-opus-4-5":   {"in": 15.00, "out": 75.00},
    "claude-opus-4-5-20251101": {"in": 15.00, "out": 75.00},
}


def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    p = PRICES.get(model) or PRICES["claude-sonnet-4-5"]
    return (input_tokens / 1_000_000) * p["in"] + (output_tokens / 1_000_000) * p["out"]


def ensure_schema(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS simulator_budget_log (
            id            BIGSERIAL PRIMARY KEY,
            spent_on      date NOT NULL DEFAULT current_date,
            recorded_at   timestamptz NOT NULL DEFAULT now(),
            source        text NOT NULL,
            detail        text,
            model         text NOT NULL,
            input_tokens  integer NOT NULL DEFAULT 0,
            output_tokens integer NOT NULL DEFAULT 0,
            cost_usd      numeric(8,5) NOT NULL DEFAULT 0
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sim_budget_day ON simulator_budget_log(spent_on)")


def daily_total(cur, day: date | None = None) -> float:
    if day is None:
        day = date.today()
    cur.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM simulator_budget_log WHERE spent_on = %s", (day,))
    r = cur.fetchone()
    return float(r[0] if not isinstance(r, dict) else r.get("coalesce", 0))


def can_afford(cur, est_input_tokens: int, est_output_tokens: int, model: str) -> tuple[bool, float, float]:
    """Return (can_afford, projected_total_after, daily_budget)."""
    today_spend = daily_total(cur)
    projected = estimate_cost(est_input_tokens, est_output_tokens, model)
    return (today_spend + projected <= DAILY_BUDGET_USD,
            today_spend + projected,
            DAILY_BUDGET_USD)


def record_call(cur, model: str, input_tokens: int, output_tokens: int,
                source: str, detail: str | None = None):
    cost = estimate_cost(input_tokens, output_tokens, model)
    cur.execute("""
        INSERT INTO simulator_budget_log (source, detail, model, input_tokens, output_tokens, cost_usd)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (source, detail, model, input_tokens, output_tokens, cost))
    return cost


if __name__ == "__main__":
    # CLI: show today's spend
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    ensure_schema(cur)
    today = daily_total(cur)
    print(f"Today's simulator budget: ${today:.4f} / ${DAILY_BUDGET_USD:.2f}")
    cur.execute("""
        SELECT source, COUNT(*) AS calls, SUM(cost_usd) AS cost
          FROM simulator_budget_log
         WHERE spent_on = current_date
         GROUP BY source ORDER BY cost DESC
    """)
    for r in cur.fetchall():
        print(f"  {r[0]:25s} {r[1]:4d} calls  ${float(r[2]):.4f}")
    cur.close(); conn.close()
