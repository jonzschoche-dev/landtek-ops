#!/usr/bin/env python3
"""apply_deploy_316_regression_gate.py — pre/post-apply regression detection.

regression_gate.py captures a 'protected set' (top-10 currently-passing probes
in last 24h with ≥5 runs each) and records their baseline pass rates in
proposal_regression_gates. The post-apply auto-verifier then re-checks the
SAME protected set; if any regress, alerts Jonathan with rollback command.

This is a compromise between true pre-apply gating (which requires scratch
workflow infrastructure n8n credential bindings make impractical) and no
protection. The post-apply window is short (30 min) and the snapshot
mechanism (deploy_305) means recovery is one command.

Run by Jonathan before apply:
    python3 scripts/regression_gate.py <proposal_id>
    python3 scripts/leo_proposal_apply.py <proposal_id>
"""
import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS deploy_log (deploy_id text PRIMARY KEY, summary text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())")
cur.execute("""INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_316',
 'Regression gate: captures top-10 currently-passing probes as baseline before apply; post-apply check via auto-verifier alerts on regression. Trades pre-apply guarantee for fast post-apply detect.')
 ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary""")
print('deploy_316 logged')
