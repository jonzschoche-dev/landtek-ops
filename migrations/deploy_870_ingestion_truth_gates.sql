-- deploy_870: A77/A78 ingestion-truth substrate — the DB-side pieces of the writer-lane gates.
-- (WORKORDER_A77-A78_ingestion_truth.md; ontology_validator triggers UNTOUCHED — desk lane.)
--
-- 1. A77(1) graded resolution: comms_artifacts records the bind confidence + matched identity so a
--    held artifact is auditable; channel_users carries a per-bind confidence (NULL = explicit
--    operator bind = 1.0). The sink (comms_artifact_sink.py) holds below COMMS_BIND_MIN_CONF.
-- 2. A78 facts-don't-rot: extend reocr_reground_guard (deploy_830/833/867) — when a source doc's
--    extracted_text RE-ARRIVES (re-OCR), besides demoting no-longer-grounded verified facts, the
--    doc's verify_worker_log cooldown rows are CLEARED so the reader re-reads it next tick and the
--    demoted facts can re-earn verified against the new text (instead of sitting 14 days in limbo).
--    Demotion + ontology_reject logging behavior is byte-identical to deploy_830-as-fixed.
--
-- Idempotent. Rollback: ALTER TABLE comms_artifacts DROP COLUMN bind_confidence, DROP COLUMN matched_identity;
--                       ALTER TABLE channel_users DROP COLUMN bind_confidence;
--                       re-apply migrations/deploy_830_reocr_reground_guard.sql (restores prior fn).
--
-- Run on the VPS:
--   docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/deploy_870_ingestion_truth_gates.sql

ALTER TABLE comms_artifacts ADD COLUMN IF NOT EXISTS bind_confidence numeric;
ALTER TABLE comms_artifacts ADD COLUMN IF NOT EXISTS matched_identity text;
ALTER TABLE channel_users  ADD COLUMN IF NOT EXISTS bind_confidence numeric;  -- NULL = explicit bind (1.0)

CREATE OR REPLACE FUNCTION reocr_reground_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE demoted int;
BEGIN
  -- (matter_facts demotion audit lives in holes_findings via ontology_reject, not a notes column)
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
  -- A78 re-check re-arm (deploy_870): the source re-arrived — clear this doc's read cooldown so
  -- verify_worker re-reads it next tick (bounded: fires once per actual text change, never loops).
  IF to_regclass('public.verify_worker_log') IS NOT NULL THEN
    DELETE FROM verify_worker_log WHERE doc_id = NEW.id;
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_reocr_reground_guard ON documents;
CREATE TRIGGER trg_reocr_reground_guard
  AFTER UPDATE OF extracted_text ON documents
  FOR EACH ROW
  WHEN (OLD.extracted_text IS DISTINCT FROM NEW.extracted_text)
  EXECUTE FUNCTION reocr_reground_guard();

SELECT 'deploy_870 applied: comms bind-confidence columns + reground-guard re-arm' AS status;
