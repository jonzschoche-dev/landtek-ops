import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_329','Telegram strict rails + efficiency report: report_publisher.py centralizes the publish-report-then-push-link pattern; case_forward_digest + leo_improvement_proposer + evidence_trail_proposer all refactored to use push_strict (headline + report URL, never a dump). Reports served at https://leo.hayuma.org/reports/ behind basic auth (LandTek Files credentials). system_efficiency_report.py exposes per-exec cost, total daily spend, bloat suspects, and ranked cuts; weekly cron 22:00 UTC Sunday.') ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary")
