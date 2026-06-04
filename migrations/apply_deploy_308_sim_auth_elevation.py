#!/usr/bin/env python3
"""apply_deploy_308_sim_auth_elevation.py — schema + rule for sim auth elevation.

Schema:
  ALTER authorized_users ADD sim_target_role text
  Populated: 999000001→'owner', 999000002→'unauthorized',
             999000005→'new_prospect'; shape impersonators stay NULL.

Workflow patch (see scripts/apply_deploy_308_sim_auth_elevation.py):
  - AI Agent systemMessage extended with Rule S4 (auth elevation logic).
  - Qdrant Write onError already continueRegularOutput.
  - Context Builder SQL not auto-patched (no raw SQL nodes matched).

Known gap (to be addressed by deploy_308b): the Context Builder does not
yet surface sim_target_role in the authorized_users_directory passed to the
AI Agent, so Leo can't actually read the elevation flag at decision time —
he falls back to his standard auth check and refuses sim-jonathan despite
Rule S4. Visible in sim_status: sim.who_is_allan still fails with refusal
text after deploy_308. Fix: extend the Context Builder query to compute an
effective_role column (COALESCE(sim_target_role, role)) and have Leo read
that.
"""
import os, psycopg2
DSN = os.environ.get('PG_DSN', 'postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn = psycopg2.connect(DSN); conn.autocommit=True
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS deploy_log (deploy_id text PRIMARY KEY, summary text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())")
cur.execute("""INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_308',
 'Sim auth elevation: authorized_users.sim_target_role column populated (sim-jonathan=owner, sim-stranger=unauthorized, sim-jane-doe=new_prospect; shape impersonators stay NULL). AI Agent Rule S4 added to systemMessage describing elevation logic. KNOWN GAP: Context Builder must be extended (deploy_308b) to surface sim_target_role so Leo can actually read the flag.')
 ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary""")
print('deploy_308 logged')
