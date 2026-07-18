-- deploy_973: idempotent fact-writer key (kills the matter_facts id churn)
--
-- The bulk fact writers (harvest_facts, populate_tables_from_docs) used a
-- delete-first rewrite: every sweep re-created ~35k unchanged rows with NEW
-- ids, and fact_fields (fact_id ON DELETE CASCADE) lost its typed rows every
-- time — a perpetual wipe+refill sawtooth (caught by agent_stack_sim cycles
-- 5/10/14 as ±12–27k fact_fields swings).
--
-- This key lets both writers upsert IN PLACE: an unchanged fact keeps its id,
-- so cascades never fire for unchanged content. Scoped to the two bulk
-- writers only — operator/verify writers are not constrained.
--
-- NOTE: the index + column may already exist (created live 2026-07-18 during
-- the churn fix); this migration is the idempotent record of that schema.
--
--   docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/deploy_973_mf_writer_key.sql

BEGIN;

ALTER TABLE matter_facts ADD COLUMN IF NOT EXISTS updated_at timestamptz;

COMMIT;

-- Deduplicate any legacy (matter, writer, source, statement) twins before the
-- unique index (keep the lowest id — the one fact_fields points at longest).
DELETE FROM matter_facts a
USING matter_facts b
WHERE a.created_by IN ('harvest', 'doc_populate')
  AND b.created_by = a.created_by
  AND b.matter_code = a.matter_code
  AND b.source_id IS NOT DISTINCT FROM a.source_id
  AND md5(b.statement) = md5(a.statement)
  AND b.id < a.id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mf_writer_key
  ON matter_facts (matter_code, created_by, source_id, md5(statement))
  WHERE created_by IN ('harvest', 'doc_populate');

SELECT 'uq_mf_writer_key ready: ' || count(*)::text
FROM pg_indexes WHERE indexname = 'uq_mf_writer_key';
