-- apply_deploy_693_kg_triples_provenance_split.sql
-- Schema-health quick win: knowledge_graph_triples.provenance_level was OVERLOADED with
-- extraction-method strings instead of a provenance tier (ONTOLOGY.md known-exception,
-- flagged by scripts/ontology_check.py every run). Split method → new extraction_method
-- column; rewrite provenance_level to the canonical 5-value vocab.
--
-- Mapping (grounded on live rows 2026-07-05):
--   llm_sonnet_4_6_triple        (70) -> inferred_strong   (LLM-extracted triple)
--   llm_sonnet_4_6_triple_empty  (1)  -> inferred_weak     (empty/low-signal extraction)
--   verified_from_doc_title      (1)  -> verified          (grounded in doc title)
--   verified_from_doc_header     (1)  -> verified          (grounded in doc header)
--   verified_from_court_caption  (1)  -> verified          (grounded in court caption)
-- The model/source is already carried in the existing `model` column.
--
-- Idempotent (IF NOT EXISTS + NULL-guarded backfill + NOT-IN-guarded rewrite). 74 rows. No trigger fires.

BEGIN;

ALTER TABLE knowledge_graph_triples ADD COLUMN IF NOT EXISTS extraction_method text;

-- 1. preserve the original method string before we overwrite the tier
UPDATE knowledge_graph_triples
   SET extraction_method = provenance_level
 WHERE extraction_method IS NULL;

-- 2. rewrite provenance_level to a canonical tier
UPDATE knowledge_graph_triples
   SET provenance_level = CASE
         WHEN provenance_level LIKE 'verified_from_%'          THEN 'verified'
         WHEN provenance_level = 'llm_sonnet_4_6_triple'       THEN 'inferred_strong'
         WHEN provenance_level = 'llm_sonnet_4_6_triple_empty' THEN 'inferred_weak'
         ELSE provenance_level
       END
 WHERE provenance_level NOT IN
       ('verified','operator','inferred_strong','inferred_corroborated','inferred_weak');

COMMIT;
