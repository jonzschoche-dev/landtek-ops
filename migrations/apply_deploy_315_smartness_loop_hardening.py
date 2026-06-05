#!/usr/bin/env python3
"""apply_deploy_315_smartness_loop_hardening.py — closes 3 short-term gaps.

(1) refresh_title_facts.py — regenerates Context Builder TITLE_CHAIN_FACTS_TEXT
    const from live title_chain table; cron daily 06:00 UTC. Closes the latent
    rot where new verified derivatives (via heightened OCR) wouldn't reach Leo.
    First run pulled 46 parents, 94 verified edges — significantly expanded
    from the hand-rolled deploy_312c const (OCT T-106 has 19 verified children
    that were missing).

(2) Probe recategorization — expanded leo_qa_probes.category enum to include
    'infrastructure', 'business', 'evidence_trail', 'filing_discipline'.
    Recategorized 134 probes by rail + name pattern:
      security        40   (impersonator, stranger, privacy, isolation)
      business        39   (business_health rail)
      evidence_trail  32   (case-fact probes: titles, chains, encumbrances)
      phrasing         7   (recognition / refusal wording)
      mandate          6   (deploy_307 invariants + 2 mandate-rail)
      onboarding       4
      infrastructure   3   (conn / health / hygiene)
      capability       3
    Zero probes now in 'other'.

(3) Cron schedule:
      0 6 * * *   refresh_title_facts.py
"""
import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS deploy_log (deploy_id text PRIMARY KEY, summary text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())")
cur.execute("""INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_315',
 'refresh_title_facts daily cron (46 parents/94 verified edges) + probe category enum expansion + 134 probes recategorized across 8 categories.')
 ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary""")
print('deploy_315 logged')
