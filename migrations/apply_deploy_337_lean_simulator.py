#!/usr/bin/env python3
"""apply_deploy_337_lean_simulator.py — establish the dirt-cheap simulator.

After deploy_336 paused the heavy simulator, this deploy installs the
lean version Jonathan approved:

  Mode 1 (validate_static.py)         $0/day · runs on deploy hooks
  Mode 2 (shadow_real_traffic.py)     $0/day · runs every 5 min cron
  Mode 3 (micro_probe_runner.py)      ~$0.10/day · runs daily 03:00 UTC
  Mode 4 (trigger_check.py)           ~$0.20 per trigger · max 3/day

Hard budget cap: $1/day (simulator_budget.py circuit breaker).

Tables:
  simulator_budget_log         — every LLM call cost tracked per day
  real_traffic_violations      — Mode 2 detections (dedup by interaction+kind)

Schema is created lazily by each script's ensure_schema(); this migration
just logs the deploy and prepares the env.

Cost-discipline target: <$1/day all-in vs $30-45/day pre-pause.
"""
from __future__ import annotations
import os
import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    # Lazy schema creation matches what each script does on first run.
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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS real_traffic_violations (
            id              BIGSERIAL PRIMARY KEY,
            detected_at     timestamptz NOT NULL DEFAULT now(),
            interaction_id  integer NOT NULL,
            sender_id       text NOT NULL,
            violation_kind  text NOT NULL,
            evidence        text NOT NULL,
            alerted         boolean NOT NULL DEFAULT false,
            UNIQUE (interaction_id, violation_kind)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rtv_recent ON real_traffic_violations(detected_at DESC)")
    cur.execute("""
        INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_337',
         'Lean simulator: 4 modes (static validate, real-traffic shadow, micro-probes daily 03:00 UTC, trigger-based). 10 hand-authored probes (lean_probe_library.yaml). Hardcoded substring graders (no LLM grading). Circuit breaker $1/day. Total expected: <$1/day vs $30-45/day pre-pause. Crons: shadow every 5min, micro-probe daily 03:00 UTC.')
        ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary
    """)
    print("✓ simulator_budget_log + real_traffic_violations tables")
    print("✓ deploy_337 logged")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
