-- 2026-07-21_client_classifier.sql — seed the missing client-principal keywords + the triage-queue view.
-- Feeds scripts/classify_client.py. Every term is a DISTINCTIVE proper name / org / application-id — NEVER a
-- bare place (passes truth_tests/test_case_keywords_no_bare_geo; the Paracale place-leak lesson holds).
-- Idempotent (ON CONFLICT-free via NOT EXISTS). case_keywords has no unique constraint, so guard on absence.

BEGIN;

INSERT INTO case_keywords (case_file, keyword, weight, notes)
SELECT v.case_file, v.keyword, 1.0, '2026-07-21 client-principal (classify_client)'
  FROM (VALUES
    -- NIBDC-001 (Northern Island Builders — mining) had ZERO keywords; that's why its 16 docs never auto-filed
    ('NIBDC-001','Northern Island Builders'),
    ('NIBDC-001','Northern Islands Builders'),   -- OCR plural variant
    ('NIBDC-001','NIBDC'),
    ('NIBDC-001','EXPA-000250'),
    ('NIBDC-001','EXPA - 000250'),
    ('NIBDC-001','APSA-000322'),
    ('NIBDC-001','APSA No. 000322'),
    -- MWK-001 — OCR-robust estate principals (tax decs OCR "Keesey" as Keosay/Keeser/Kissey, but the estate
    -- surname WORRICK/WARRICK survives every variant and is distinctive to this estate)
    ('MWK-001','Worrick'),
    ('MWK-001','Warrick'),
    ('MWK-001','Zschoche'),
    ('MWK-001','Keesey'),
    -- Paracale-001 — the distinctive Inocalla surname (multi-match→flag protects the shared-affiant overlap)
    ('Paracale-001','Inocalla')
  ) AS v(case_file, keyword)
 WHERE NOT EXISTS (SELECT 1 FROM case_keywords k
                    WHERE lower(k.keyword)=lower(v.keyword) AND k.case_file=v.case_file);

COMMIT;

-- Triage queue: the operator's filing surface — everything the deterministic layers couldn't confidently file.
CREATE OR REPLACE VIEW v_scan_triage AS
SELECT d.id AS doc_id,
       d.original_filename,
       coalesce(d.document_type,'—')      AS document_type,
       coalesce(d.ingest_source,'—')      AS source,
       length(coalesce(d.extracted_text,'')) AS text_len,
       coalesce(d.case_file,'(unfiled)')  AS folder,
       d.analyst_memo->'client_classification'->>'reason'   AS classify_reason,
       d.analyst_memo->'client_classification'->'matched'   AS classify_evidence,
       d.created_at::date AS landed
  FROM documents d
 WHERE d.case_file IS NULL OR d.case_file = 'PENDING_TRIAGE'
 ORDER BY d.created_at DESC, d.id DESC;

COMMENT ON VIEW v_scan_triage IS
  'Operator filing queue: docs the deterministic client-classifier could not confidently file (unfiled or PENDING_TRIAGE). Apply with: python3 scripts/classify_client.py --file <doc_id> <case_file> [matter].';
