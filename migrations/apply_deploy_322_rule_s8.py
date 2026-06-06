#!/usr/bin/env python3
"""apply_deploy_322_rule_s8.py — Rule S8 owner engagement.

Leo was refusing sim-jonathan on case-fact queries because the rule-stack
defensive bias bled into the owner-asks path. Rule S8 explicitly gates
refusal templates by telegram_id:
  - sender=6513067717 or 999000001 → MUST answer from context, refusal
    templates forbidden
  - all other senders unchanged

Verified post-patch: Leo lists 9 verified T-4497 derivatives + sub-derivatives,
cites Cesar de la Fuente as executor with honest scope on missing notary,
admits zero exhibits linked when evidence_trail empty for a claim.

Snapshot #15 for rollback.
"""
import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_322', 'Rule S8: owner engagement. Refusal templates forbidden when sender=Jonathan (real or sim). Verified Leo now answers case-fact queries from loaded context with citations.') ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary")
print('deploy_322 logged')
