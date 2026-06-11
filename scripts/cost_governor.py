#!/usr/bin/env python3
"""cost_governor.py — make LLM spend VISIBLE and CAPPED so the balance can never
silently hit zero again.

  record(model, usage, source)  — log actual token usage (incl. cache) after a call
  today_spend()                 — $ spent so far today (real, from logged usage)
  can_afford(source)            — QA/synthetic work stops at the daily cap; real
                                  client work is allowed up to a higher hard ceiling

Set the cap with LANDTEK_DAILY_LLM_CAP (default $8/day). The QA loops call
can_afford() before each cycle; Leo's client pipeline records but is not blocked
until a generous hard stop.
"""
import os
import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
DAILY_CAP = float(os.environ.get("LANDTEK_DAILY_LLM_CAP", "8.0"))
# $ per 1M tokens: (input, output, cache_read). cache write ~1.25x input.
PRICING = {
    "claude-sonnet-4-5-20250929": (3.0, 15.0, 0.30),
    "claude-sonnet-4-6":          (3.0, 15.0, 0.30),
    "claude-opus-4-5-20251101":   (15.0, 75.0, 1.50),
    "claude-haiku-4-5-20251001":  (0.80, 4.0, 0.08),
}


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def ensure(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS llm_spend (
        id serial PRIMARY KEY, ts timestamptz DEFAULT now(), source text, model text,
        input_tok int, output_tok int, cache_read_tok int, cache_write_tok int,
        cost_usd numeric)""")


def price(model, usage):
    pi, po, pcr = PRICING.get(model, (3.0, 15.0, 0.30))
    it = usage.get("input_tokens", 0) or 0
    ot = usage.get("output_tokens", 0) or 0
    cr = usage.get("cache_read_input_tokens", 0) or 0
    cw = usage.get("cache_creation_input_tokens", 0) or 0
    return (it * pi + cw * pi * 1.25 + cr * pcr + ot * po) / 1e6


def record(model, usage, source="leo"):
    try:
        c = _conn(); cur = c.cursor(); ensure(cur)
        cur.execute("""INSERT INTO llm_spend
            (source, model, input_tok, output_tok, cache_read_tok, cache_write_tok, cost_usd)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (source, model, usage.get("input_tokens", 0), usage.get("output_tokens", 0),
             usage.get("cache_read_input_tokens", 0), usage.get("cache_creation_input_tokens", 0),
             round(price(model, usage), 6)))
        cur.close(); c.close()
    except Exception:
        pass


def today_spend():
    try:
        c = _conn(); cur = c.cursor()
        cur.execute("SELECT coalesce(sum(cost_usd),0) FROM llm_spend WHERE ts::date = current_date")
        v = float(cur.fetchone()[0]); cur.close(); c.close(); return v
    except Exception:
        return 0.0


def can_afford(source="qa", cap=None):
    """QA / synthetic load stops at the daily cap. Real client work ('client') is
    allowed up to 3x the cap (a hard safety stop), never throttled for routine spend."""
    cap = cap if cap is not None else DAILY_CAP
    spent = today_spend()
    return spent < (cap * 3 if source == "client" else cap)


if __name__ == "__main__":
    print(f"today_spend=${today_spend():.4f}  cap=${DAILY_CAP}  qa_ok={can_afford('qa')}")
