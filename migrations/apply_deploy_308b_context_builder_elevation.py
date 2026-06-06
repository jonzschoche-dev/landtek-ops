#!/usr/bin/env python3
"""apply_deploy_308b_context_builder_elevation.py — make sim_target_role visible.

deploy_308 added the sim_target_role column + Rule S4 in the system prompt,
but Leo still refused sim-jonathan because the Context Builder pre-computed
isJonathan = (senderId === '6513067717') — hardcoded to the real telegram_id —
and downstream auth gating used that flag.

This patch updates the Context Builder JS to:
  - Look up sim_target_role per the lookup table
  - Define isSimulation, effectiveRole, isJonathanLike
  - Override isJonathan = isJonathanLike so downstream owner-gating engages
    for sim-jonathan
  - Append a SIMULATION CONTEXT block to agentInput so the AI Agent sees the
    elevation in its prompt context

Also extends the authorized_users_directory SELECT to include sim_target_role
column so the agent sees it for all sim rows.

Verified behavior change immediately post-restart:
  sim-jonathan empty_promise_attachment_fetch probe → Leo now ENGAGES
  ("I can't pull Gmail attachments... here's how to get them") instead of
  refusing ("you don't appear to be a registered client").
  Stranger probes still refused correctly.
"""
import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS deploy_log (deploy_id text PRIMARY KEY, summary text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())")
cur.execute("""INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_308b',
 'Context Builder sim awareness: lookup table for sim_target_role, isSimulation/effectiveRole/isJonathanLike computed and exposed. isJonathan overridden to isJonathanLike so downstream owner-gating fires for sim-jonathan. authorized_users SELECT extended with sim_target_role column. SIMULATION CONTEXT block injected into agentInput. Verified: sim-jonathan now engages probes instead of blanket refusal.')
 ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary""")
print('deploy_308b logged')
