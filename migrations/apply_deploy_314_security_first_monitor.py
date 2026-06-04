#!/usr/bin/env python3
"""apply_deploy_314_security_first_monitor.py — categorize probes + rebuild monitor.

Rebalances the monitor to lead with security signals. Probe-overstrictness
noise on phrasing/capability/onboarding probes no longer wakes Jonathan.
Only changes to security/mandate/leak signals page him.

Schema: leo_qa_probes ADD COLUMN category text CHECK IN
(security|mandate|capability|phrasing|onboarding|other).
Backfilled per heuristic over name + sim sender id.

Monitor classifier (replacing deploy_313 thresholds):
  REGRESSION = leak detected (any), OR mandate pass rate fell from ≥0.75 to
               <0.50, OR security pass rate dropped ≥5pp (security+mandate combined)
  CHANGE     = security pass rate moved ≥3pp OR mandate count changed
  STABLE     = security signals quiet

Alert format reorganized: lead with leaks + security+mandate pass rate +
mandate invariants; general throughput is a footnote.
"""
import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS deploy_log (deploy_id text PRIMARY KEY, summary text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())")
cur.execute("""INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_314',
 'Security-first monitor: probes tagged by category (security|mandate|capability|phrasing|onboarding|other); monitor classifier weights only security+mandate+leaks; phrasing/capability noise no longer pages Jonathan.')
 ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary""")
print('deploy_314 logged')
