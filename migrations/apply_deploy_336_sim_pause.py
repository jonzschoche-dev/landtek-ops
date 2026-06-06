#!/usr/bin/env python3
"""apply_deploy_336_sim_pause.py — pause the simulator and all token-burning crons.

Honest reckoning: $86 of API tokens this month for ~0 case progress
(0 exhibits linked, Manifestation still on session branch, 0 of 20
transferees moved). Simulator was an architectural exercise that didn't
move the case forward.

Stopped:
  - leo-simulator.service                  (the 20s daemon)
  - leo_qa_probe_generator cron            (Opus/Sonnet probe drafting)
  - leo_improvement_proposer cron          (Opus proposal drafting)
  - leo_proposal_auto_verify cron          (no sim → nothing to verify)
  - evidence_trail_proposer cron           (Opus doc→claim mappings)
  - predict_opposing_responses cron        (Opus opposing-counsel)
  - opus_doc_role_classifier cron          (already-finished one-shot)
  - sim_monitor cron                       (no sim to monitor)
  - sim_daily_digest cron                  (replaced by case_forward)
  - sim_leak_sentinel cron                 (no sim → no leaks)
  - cron_health_sentinel cron              (would alert on its own gone neighbors)
  - system_efficiency_report cron          (weekly meta-report)

Kept (all $0/day, all SQL-only or essential safety):
  - backup_postgres                        2am daily
  - autonomous/daily_digest.py             23:00 daily (legacy case briefer)
  - refresh_title_facts                    6am daily   — title chain → Leo
  - refresh_evidence_facts                 every 10min — claim→exhibit → Leo
  - apply_evidence_trail_proposals         hourly      — approved → canonical
  - refresh_realtime_flow                  every 5min  — obligations+events → Leo
  - refresh_objectives                     every 5min  — transferees+matters → Leo
  - refresh_client_history                 every 10min — 1,118 events → Leo
  - case_forward_digest                    7am Manila  — daily ONE THING push

Leo's brain (the AI Agent in n8n) stays up to handle REAL client messages.
No API calls happen except when a real client (or Jonathan) messages Leo.

Estimated daily API spend post-pause: <$3/day (only real-client interactions).
Down from $30-45/day during simulator operation.
"""
import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_336','Simulator + improvement loop PAUSED. Honest reckoning: $86 burned for ~0 case progress. Killed leo-simulator.service + 12 token-burning crons. Kept 9 zero-cost essential crons (backups + Context Builder refreshes + case_forward_digest + autonomous/daily_digest). Leo brain available for real client traffic only. Estimated daily API spend post-pause: <$3/day.') ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary")
