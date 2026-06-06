#!/usr/bin/env python3
"""apply_deploy_312_title_chain_context.py — title_chain into Leo's context.

The mandate-invariant probes from deploy_307 (T-30683 separateness, T-4494
separateness, MMK!=MWK, T-32917 positive control) were all failing because
Leo had no access to the verified title_chain at decision time — he was
guessing on every derivative question.

Three iterations shipped together:
  - deploy_312:  extended Execute a SQL query to also return title_chain_verified +
                 separate_titles + mmk_vs_mwk_invariant. BROKE: missing comma in SQL
                 injection caused syntax error; rolled back via snapshot #6.
  - deploy_312-fix: comma fix; SQL extension landed. But sim senders (999000xxx)
                    don't match any client row → clientRow.* returned empty →
                    Leo still saw '(title_chain not loaded)' fallback.
  - deploy_312c: switched architecture — embedded TITLE_CHAIN_FACTS_TEXT as a
                 const inside Context Builder JS so it loads unconditionally
                 regardless of who's asking. Reference data; regenerate via
                 scripts/refresh_title_facts.py when chain changes.
  - Probe fix:  the T-30683 / T-4494 probes had forbidden_substrings that
                matched BOTH 'is a derivative of T-4497' (wrong) and 'not a
                derivative of T-4497' (right) — couldn't distinguish negation.
                Replaced with phrases unambiguously wrong (e.g. 'yes, T-30683
                is a derivative').

Verified mandate probe results post-shipment:
  ✓ mandate.t32917_is_known_derivative_of_t4497 (positive control)
  ✓ mandate.mmk_not_equal_mwk
  ✓ mandate.t4494_cabanbanan_not_derivative_of_t4497  (after probe fix)
  ✓ mandate.t30683_manguisoc_not_derivative_of_t4497  (after probe fix)
"""
import os, psycopg2
DSN=os.environ.get('PG_DSN','postgresql://n8n:n8npassword@172.18.0.3:5432/n8n')
conn=psycopg2.connect(DSN); conn.autocommit=True
cur=conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS deploy_log (deploy_id text PRIMARY KEY, summary text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())")
cur.execute("""INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_312',
 'Title chain into Leos context: TITLE_CHAIN_FACTS_TEXT const in Context Builder JS surfaces verified T-4497 derivatives + explicit separate matters (T-30683, T-4494) + MMK!=MWK invariant unconditionally. Mandate-invariant probes now passing with sourced, substantive answers (T-32917 derivative affirmation, MMK quotes CLAUDE.md 307 corpus occurrences, T-30683/T-4494 correctly classified as separate). Probe forbidden_substrings fixed to distinguish negation.')
 ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary""")
print('deploy_312 logged')
