#!/usr/bin/env python3
"""apply_deploy_313_sim_monitor.py — adaptive-cadence simulator monitor.

Cron fires sim_monitor.py every 5 min unconditionally. Script self-throttles
via sim_monitor_state.next_check_at — exits cheap if not due.

Classifies each read as regression / change / stable and pushes a Telegram
update only on the first two. Stable reads accumulate; after 3 consecutive
stable reads, the interval doubles (cap 60 min). Any regression snaps the
interval back to 5 min.

Result: Jonathan sees tight visibility (5-min) while the simulator is
unstable; quiet (up to 60-min) when steady; immediate alerts when
something regresses.

Source='watchdog' so push bypasses rate limits.
"""
import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS deploy_log (deploy_id text PRIMARY KEY, summary text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())")
cur.execute("""INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_313',
 'Adaptive-cadence simulator monitor: cron every 5 min, classifies regression/change/stable, push only on first two, doubles interval after 3 stable reads (cap 60), snaps to 5 min on regression. Stored state in sim_monitor_state singleton.')
 ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary""")
print('deploy_313 logged')
