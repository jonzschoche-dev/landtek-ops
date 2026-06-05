#!/usr/bin/env python3
"""apply_deploy_320_evidence_population.py — auto-populate Evidence Trail.

Three pieces shipped:

(1) auto_assign_doc_role.py — heuristic filename + summary classification.
    First run: 240 of 977 docs classified across 8 roles; 737 'not_yet_assessed'
    (no filename hit any heuristic — Jonathan can refine later).

(2) evidence_trail_proposer.py — Opus reads claims + docs, proposes mappings.
    First run on the 6 seeded claims: 16 proposals across 3 of 6 claims
    (Balane void chain, Cesar SPA, MMK!=MWK). Daily cron 07:00 UTC.

(3) apply_evidence_trail_proposals.py — moves status='approved' rows into
    canonical evidence_trail table. Hourly cron.

Workflow: Jonathan reviews Telegram digest → approves via
  UPDATE evidence_trail_proposals SET status='approved' WHERE id IN (...)
  → next hourly cron applies them → refresh_evidence_facts (10-min cron)
  rebuilds Context Builder const → Leo sees the linked exhibits.

Closes the gap between deploy_317 schema and operational evidence trail.
"""
import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_320', 'Evidence Trail population: auto_assign_doc_role + evidence_trail_proposer + apply_evidence_trail_proposals. 240/977 docs heuristically classified. 16 Opus proposals for review.') ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary")
print('deploy_320 logged')
