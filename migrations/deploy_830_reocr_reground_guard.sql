-- deploy_830: root-cause guard for the deploy-gate breach of 2026-07-09 (8 ungrounded verified facts).
-- Cause: re-OCR rewrote documents.extracted_text AFTER verified matter_facts had cited excerpts from the
-- old text — the facts silently went ungrounded (A2/A20 breach) until the nightly gate caught them.
-- Guard: when a document's extracted_text changes, re-test excerpt_grounded for every verified fact citing
-- it; any fact that no longer grounds is DEMOTED to inferred_strong immediately (never left verified) and
-- the demotion is logged. Verified status can be re-earned by the normal re-verify path against new text.
--
-- Idempotent. Rollback: DROP TRIGGER trg_reocr_reground_guard ON documents;
--                       DROP FUNCTION reocr_reground_guard();
--
-- Run on the VPS:
--   docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/deploy_830_reocr_reground_guard.sql

CREATE OR REPLACE FUNCTION reocr_reground_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE demoted int;
BEGIN
  -- (matter_facts has no notes column — the demotion audit lives in holes_findings via ontology_reject)
  UPDATE matter_facts mf
     SET provenance_level = 'inferred_strong',
         updated_at = now()
   WHERE mf.source_id = NEW.id::text
     AND mf.provenance_level = 'verified'
     AND NOT excerpt_grounded(mf.excerpt, mf.source_id);
  GET DIAGNOSTICS demoted = ROW_COUNT;
  IF demoted > 0 THEN
    BEGIN
      PERFORM ontology_reject('REOCR_UNGROUNDED_FACT_DEMOTED',
        'doc '||NEW.id||' extracted_text changed; '||demoted||
        ' verified fact(s) no longer ground -> demoted to inferred_strong');
    EXCEPTION WHEN OTHERS THEN NULL;  -- logging must never break the OCR write path
    END;
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_reocr_reground_guard ON documents;
CREATE TRIGGER trg_reocr_reground_guard
  AFTER UPDATE OF extracted_text ON documents
  FOR EACH ROW
  WHEN (OLD.extracted_text IS DISTINCT FROM NEW.extracted_text)
  EXECUTE FUNCTION reocr_reground_guard();

-- Safety sweep (no-op when clean): demote anything currently ungrounded-verified.
UPDATE matter_facts
   SET provenance_level='inferred_strong', updated_at=now()
 WHERE provenance_level='verified' AND NOT excerpt_grounded(excerpt, source_id);

SELECT 'guard installed; currently ungrounded verified: '||count(*)
FROM matter_facts WHERE provenance_level='verified' AND NOT excerpt_grounded(excerpt, source_id);
