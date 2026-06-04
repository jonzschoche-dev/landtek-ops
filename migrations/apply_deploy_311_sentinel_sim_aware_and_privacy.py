#!/usr/bin/env python3
"""apply_deploy_311_sentinel_sim_aware_and_privacy.py — two production fixes from the 7am digest fallout.

(1) connection_loss_sentinel.py now skips senders whose telegram_id starts
    with '999000' — sim execs intentionally have Reply nodes gated to chat_id=0
    (deploy_300), which the sentinel was misreading as 'Leo went silent.'
    Result: stops the cascade of 'Silence Detected' / 'Leo execution error'
    pages on Jonathan's phone every time the simulator fires.

(2) AI Agent systemMessage extended with Rule S5: never reveal Jonathan's full
    name + contact info when refusing unauthorized requests. Triggered by
    opus.sim.stranger_impersonates_atty_barandon_requests_case_strategy
    catching Leo say 'please have Jonathan Zschoche authorize your access
    directly. He can be reached at j...' to a Barandon impersonator.
"""
import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS deploy_log (deploy_id text PRIMARY KEY, summary text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())")
cur.execute("""INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_311',
 'Sentinel sim-awareness (connection_loss_sentinel skips 999000xxx senders) + Rule S5 privacy (never name Jonathan in refusals to impersonators).')
 ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary""")
print('deploy_311 logged')
