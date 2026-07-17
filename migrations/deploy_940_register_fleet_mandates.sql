-- deploy_940: register two fleet agents in agent_mandates (deploy_938 registry)
--
-- Criterion for joining the registry: the agent owns living tables that the
-- inquiry read path depends on. contradiction owns holes_findings — a layer
-- scrutinize() already reads on every ask. corpus_steward owns matter-corpus
-- completeness (document_matter_links backfill + awareness_log), the substrate
-- doc_populate and every brief materializes from.
--
-- Drain behavior (inquiry_stack._run_agent_hook):
--   contradiction  → runs directly (light single-pass scan)
--   corpus_steward → defers to its 6h systemd timer (heavy sweep), like verify_worker
--
--   docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/deploy_940_register_fleet_mandates.sql

BEGIN;

INSERT INTO agent_mandates (agent_key, mandate, owns_tables, reads_tables, trigger_on, notes) VALUES
(
  'contradiction',
  'Cross-check facts for conflicts per matter; keep contradictions and holes visible to inquiry',
  ARRAY['contradictions', 'holes_findings'],
  ARRAY['matter_facts'],
  ARRAY['new_matter_fact', 'inquiry_answer_atom'],
  'Fleet agent (scripts/contradiction.py, daily in verify svc) — scrutinize() reads the holes layer on every ask'
),
(
  'corpus_steward',
  'Keep every matter''s case file complete, current and reachable',
  ARRAY['document_matter_links', 'awareness_log'],
  ARRAY['documents', 'matters'],
  ARRAY['new_document', 'inquiry_gap_doc'],
  'Fleet agent (scripts/case_corpus_sweep.sh, 6h timer) — drain defers to the timer; sim measures its tables'
)
ON CONFLICT (agent_key) DO UPDATE SET
  mandate = EXCLUDED.mandate,
  owns_tables = EXCLUDED.owns_tables,
  reads_tables = EXCLUDED.reads_tables,
  trigger_on = EXCLUDED.trigger_on,
  notes = EXCLUDED.notes,
  updated_at = now();

COMMIT;

SELECT agent_key, owns_tables FROM agent_mandates WHERE active ORDER BY agent_key;
