-- 2026-07-18 — stop the matter_facts sawtooth (deploy: mf idempotent write key)
--
-- harvest_facts.py and populate_tables_from_docs.py both DELETE+reINSERT their
-- unchanged facts every awareness cycle (~34.8k rows recreated per run; max(id)
-- hit 2,595,938 for a 41k-row table). fact_fields.fact_id is ON DELETE CASCADE,
-- so every rewrite wiped the typed fields and extract_fact_fields refilled them
-- — a perpetual sawtooth (4k → 16k → 29k → ~41.6k observed mid-cycle).
--
-- This adds the natural write key for the two automated writers so they can
-- upsert in place (ids preserved, cascade never fires for unchanged facts).
-- Other writers (verify_worker, operator, inquiry_stack, …) are outside the
-- partial predicate and completely unaffected.

BEGIN;

-- 1) Dedup existing rows under the new key (386 harvest dups from docs with
--    multiple document_matter_links rows). Keep the row with the most typed
--    fact_fields; tiebreak lowest id.
WITH ranked AS (
  SELECT mf.id,
         row_number() OVER (
           PARTITION BY mf.matter_code, mf.created_by, mf.source_id, md5(mf.statement)
           ORDER BY (SELECT count(*) FROM fact_fields ff WHERE ff.fact_id = mf.id) DESC,
                    mf.id
         ) AS rn
  FROM matter_facts mf
  WHERE mf.created_by IN ('harvest', 'doc_populate')
)
DELETE FROM matter_facts WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

-- 2) The idempotency key. md5(statement) keeps the index small (statement is
--    capped at 500 chars but can be multibyte).
CREATE UNIQUE INDEX IF NOT EXISTS uq_mf_writer_key
  ON matter_facts (matter_code, created_by, source_id, md5(statement))
  WHERE created_by IN ('harvest', 'doc_populate');

COMMIT;
