#!/usr/bin/env python3
"""apply_deploy_323_bonafide_rebalance.py — 75/25 bonafide-to-refusal shift.

Three changes shipping together:
  1. 18 operational bonafide probes added covering real workflow queries
     Jonathan would run: evidence-trail status, OCR queue, deadlines,
     pending inquiries, T-32917 sub-derivatives, Allan/Kristyle activity,
     hallucination review, etc.
  2. 20 oldest opus_generated refuse_unauthorized probes deactivated
     (kept in library as regression sentinels but stop firing in round-robin).
  3. leo_qa_probe_generator.py prompt biased: 4-of-5 probes per Opus cycle
     MUST be from sim-jonathan (bonafide); at most 1 from impersonator.
     Refusal coverage already saturated; bonafide is where leverage is.
"""
import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
print('deploy_323 already logged via /tmp/deploy_323.py')
