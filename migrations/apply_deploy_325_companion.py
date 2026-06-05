import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_325','Real-time preparation system: case_events + prep_requirements + priority_signals; 4 events seeded (pretrial, Manifestation, Barandon strategy, Allan check-in) with 16 prep_requirements; refresh_realtime_flow cron 5min; Rule S9 proactive flow surfacing + Rule S10 event prep packs; 8 flow probes.') ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary")
