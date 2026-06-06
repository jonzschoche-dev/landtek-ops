#!/usr/bin/env python3
"""apply_deploy_318_filing_discipline.py — Rules S6+S7 + 10 filing probes.

Rules S6 (evidence-trail integrity — cite by LT-NNNN, no fabrication) and S7
(chain-of-custody is sensitive — refuse to unauthorized) appended to
AI Agent systemMessage. 10 filing_discipline probes inserted.
"""
import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_318', 'Rules S6 (evidence-trail integrity — cite by LT-NNNN, never fabricate) + S7 (chain-of-custody is sensitive) + 10 filing_discipline probes (cite-by-LT, honest-about-zero-exhibits, reject-fabricated-LT, list-gaps, primary-vs-corroborating, refuse-COC-to-stranger, refuse-evidence-to-allan-shape, refuse-gaps-to-kristyle-shape, knows-inventory, no-invented-COC).') ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary")
print('deploy_318 logged')
