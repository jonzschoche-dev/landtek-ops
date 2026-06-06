import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_327', 'Perpetual operation hardening: (1) auto-verifier tolerates retired probes + partial data, verifies on active subset >=2 probes; (2) cron_health_sentinel cron every 10min alerts on stale logs with 6h re-alert dedup; (3) apply_evidence_trail_proposals now auto-applies confidence >=0.90 in addition to manual-approved; (4) bonafide engagement chain validated end-to-end with proposal 7 verification (delta +0.083).') ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary")
