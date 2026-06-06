#!/usr/bin/env python3
"""apply_deploy_324_opus_doc_role_classifier.py — semantic doc_role for 737 docs.

The filename-heuristic classifier (auto_assign_doc_role.py from deploy_320)
handled 240/977 docs; 737 were left 'not_yet_assessed' because filenames
were ambiguous (scanner numbers, vague titles, etc.).

opus_doc_role_classifier.py batches 20 docs at a time to Opus (~37 batches).
For each doc Opus emits {doc_role, confidence} with the same enum as
deploy_317. Proposals land in doc_role_proposals; ≥0.90 confidence
auto-applies to documents.doc_role immediately, lower confidence sits
for Jonathan review.

First-run stats (n=580 docs as of commit, still completing):
  - title_instrument:    121 (115 auto-applicable)
  - background:           47
  - correspondence:       44
  - not_yet_assessed:    252 (Opus declined when genuinely ambiguous)
  - tax_declaration:      19 (6 auto-applicable)
  - pleading:             20
  - prime_evidence:       18
  - chain_proof:          10
  - transfer_instrument:   6
  - order_resolution:      3 (2 auto-applicable)
"""
import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_324', 'Opus batch doc_role classifier — 737 not_yet_assessed docs categorized by Opus in batches of 20. >=0.90 confidence auto-applies. Run mid-completion at commit time.') ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary")
print('deploy_324 logged')
