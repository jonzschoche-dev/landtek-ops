#!/usr/bin/env python3
"""apply_deploy_299_opus_probe_generator.py

Adds the Opus-driven continuous probe generator to LandTek's simulator stack.

Background:
  deploy_298c shipped the leo_simulator daemon that constantly drives Leo
  with synthetic Telegram webhooks. It worked, but only against 21
  hand-authored sim probes — and once Leo passes those, they teach us
  nothing new. We needed a generative source of fresh probes.

This migration:
  1. Records the deploy in deploy_log (idempotent).
  2. Does NOT create new schema — the generator writes to the existing
     leo_qa_probes table with rail='sim' and `definition->>'origin' =
     'opus_generated'`, distinguishable from hand-authored sim probes.

The actual moving parts ship as files (not SQL):
  - scripts/leo_qa_probe_generator.py
  - infra/systemd/leo-qa-probe-generator.service  (oneshot)
  - infra/systemd/leo-qa-probe-generator.timer    (every 30 minutes)

Operational shape:
  Every 30 min, Opus reads (a) the LandTek mandate (CLAUDE.md, DIRECTIVE.md),
  (b) Leo's current system prompt, (c) the active client + matter inventory,
  (d) the last 24h of fishy Leo replies, (e) recent sim-rail violations, and
  (f) the existing probe-name list — then proposes 5 fresh probes targeting
  hallucination resistance, mandate adherence (Rule J pacing, Rule L Field
  Mode, MMK vs MWK invariant, inference vs verified provenance), and
  client-isolation. Probes are inserted into leo_qa_probes; the simulator
  exercises them automatically on its round-robin cycle. When active
  opus-generated probes exceed 300, the oldest are auto-deactivated to keep
  the pool focused.

Verification:
  After this deploy you should see, within ~30 minutes:
    SELECT COUNT(*) FROM leo_qa_probes
     WHERE definition->>'origin' = 'opus_generated';
  go up by 5 every cycle, with simulator runs accumulating against those new
  probes within the same hour.
"""
from __future__ import annotations
import os
import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()

    # deploy_log convention: (deploy_id, summary, applied_at)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deploy_log (
            deploy_id text PRIMARY KEY,
            summary   text NOT NULL,
            applied_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    cur.execute("""
        INSERT INTO deploy_log (deploy_id, summary)
        VALUES (
            'deploy_299',
            'Opus-driven continuous probe generator: every 30min Opus reads mandate + Leos prompt + recent fishy replies and proposes 5 new sim-rail probes (rail=sim, origin=opus_generated); auto-prunes at 300 active. Simulator daemon exercises them automatically.'
        )
        ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
    """)

    cur.execute("SELECT deploy_id, applied_at FROM deploy_log WHERE deploy_id='deploy_299'")
    row = cur.fetchone()
    print(f"deploy_log: {row[0]} applied_at {row[1]}")

    cur.execute("""
        SELECT
          COUNT(*) FILTER (WHERE rail='sim' AND active) AS sim_active,
          COUNT(*) FILTER (WHERE definition->>'origin' = 'opus_generated') AS opus_generated
          FROM leo_qa_probes
    """)
    a, b = cur.fetchone()
    print(f"sim_active={a}  opus_generated={b}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
