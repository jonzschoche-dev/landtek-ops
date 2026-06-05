import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_328', 'Substance over noise: (1) case_forward_digest replaces sim_daily_digest — leads with THE ONE THING TODAY + what moved yesterday + stalled items; suppresses entirely if nothing actionable. (2) sim_monitor fires Telegram only on REGRESSION; CHANGE/STABLE silent. (3) leo_simulator picks 20%% random + 80%% oldest-quartile (was strict oldest) so probe variety appears in digests instead of same names cycling.') ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary")
