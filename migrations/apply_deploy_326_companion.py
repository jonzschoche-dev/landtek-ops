import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("""INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_326', 'Obligation-aware flow: landtek_obligations + project_phases + client_needs + 4 views. Seeded 7 obligations (representation, Manifestation filing, pretrial readiness, evidence integrity, Barandon relay, Allan monthly updates, mining-partnership awareness), 7 project_phases (MWK-001 phases 1-6 + Paracale advisory), 4 client_needs. Rules S11 (client briefing) + S12 (obligation integrity). 6 client/obligation probes.') ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary""")
print('deploy_326 logged')
