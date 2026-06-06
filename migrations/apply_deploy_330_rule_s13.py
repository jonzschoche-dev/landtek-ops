import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_330','Rule S13 — no guardrails for real Jonathan (6513067717). All defensive gating off; he is the operator, not a regulated user. Verified-fact discipline + identity integrity + LT citation still apply.') ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary")
