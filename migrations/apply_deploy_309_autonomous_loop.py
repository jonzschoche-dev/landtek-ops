#!/usr/bin/env python3
"""apply_deploy_309_autonomous_loop.py — make the smartness loop self-driving.

Closes the last manual links in the simulator architecture:

  Loop D (improvement proposer)  — was: manual run-on-demand
                                   now: cron every 4 hours
  Loop F (verifier)              — was: Jonathan-triggered after apply
                                   now: cron every 30 min, auto-runs verify
                                        on any proposal with status='applied'
                                        that has sat ≥30 min AND has ≥3 sim
                                        runs per target probe since applied_at

Apply step (E) stays manual. Jonathan retains the only decision point: which
proposals get applied. Everything else is autonomous.

New: scripts/sim_daily_digest.py — 24h state push to Jonathan at 23:00 UTC
(7am Manila). One-message overview of throughput, learning score, mandate
invariants, worst probes, pending proposals, leak count, library size.

Cron entries installed in root crontab:
  0 */4 * * *   leo_improvement_proposer.py
  */30 * * * *  leo_proposal_auto_verify.py
  0 23 * * *    sim_daily_digest.py
"""
import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS deploy_log (deploy_id text PRIMARY KEY, summary text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())")
cur.execute("""INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_309',
 'Autonomous learning loop: Opus improvement proposer cron every 4h; auto-verifier cron every 30 min (runs verify on applied proposals with sufficient post-apply data); daily sim digest cron at 23:00 UTC. Loop now self-driving except Jonathan still manually applies proposals. Test send confirmed.')
 ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary""")
print('deploy_309 logged')
