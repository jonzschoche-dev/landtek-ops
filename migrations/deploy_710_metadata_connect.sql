-- deploy_710_metadata_connect.sql — connect the corpus (Step 2, done from RELIABLE existing data).
-- 1) Backfill document_type from the already-assigned `classification` (deterministic map, no re-OCR,
--    no LLM) — types ~770 docs so v_evidence_gaps and classify→contract routing can join on structure.
-- 2) Add court_order_v1 — the one genuinely-missing extraction contract (deed/spa/affidavit already exist).
-- Idempotent: only fills document_type where NULL; ON CONFLICT no-op for the contract.

-- 1) document_type ← classification (canonical values aligned to extraction_contract.doc_class)
UPDATE documents SET document_type = CASE
    WHEN lower(classification) LIKE 'title%'                                          THEN 'TCT'
    WHEN lower(classification) = 'deed'                                               THEN 'Deed'
    WHEN lower(classification) LIKE '%power of attorney'                              THEN 'SPA'
    WHEN lower(classification) LIKE '%affidavit%'                                     THEN 'Affidavit'
    WHEN lower(classification) IN ('resolution','order','decision')                  THEN 'Court Order'
    WHEN lower(classification) IN ('complaint','motion','reply','petition','court filing') THEN 'Court Filing'
    WHEN lower(classification) = 'tax document'                                       THEN 'Tax Document'
    WHEN lower(classification) IN ('letter','correspondence','demand letter','email','notice','memorandum') THEN 'Correspondence'
    WHEN lower(classification) = 'receipt'                                            THEN 'Receipt'
    WHEN lower(classification) = 'contract'                                           THEN 'Contract'
    WHEN lower(classification) = 'government submission'                              THEN 'Government Submission'
    ELSE document_type
  END
WHERE document_type IS NULL AND classification IS NOT NULL;

-- 2) court_order_v1 — the missing contract (mirrors deed_v1/spa_v1 canonical shape)
INSERT INTO extraction_contract (version, doc_class, required_fields, optional_fields, validation_rules, notes)
VALUES (
  'court_order_v1', 'Court Order',
  '["doc_class","case_number","court_and_branch","case_title","parties_and_roles","nature_of_action","dispositive_portion","ordered_reliefs","dated_events","promulgation_date","finality_markers","presiding_judge_or_signatory","all_persons_mentioned","all_dates_mentioned","all_reference_numbers","full_raw_text","completeness_score","secondary_review_needed","secondary_review_reason"]'::jsonb,
  '[]'::jsonb,
  '{"field_status_enum":["extracted","not_present","illegible","partial","requires_heightened_ocr"],"must_emit_full_raw_text":true,"every_extracted_field_must_carry_source_quote":true,"dispositive_portion_is_verbatim":true,"dated_events_require_source_text":true}'::jsonb,
  'v1 CANONICAL Court Order/Resolution/Decision/Writ schema — captures case no., court+branch, parties+roles, the VERBATIM dispositive portion (the fallo — never paraphrase), ordered reliefs, typed dated_events each with source_text (feeds calendar_sync), finality markers. Built because every dispositive portion this session (98-88750, 13-131220, alias writ) was hand-mined from garbled text. Applies to orders, resolutions, decisions, writs, judgments.'
)
ON CONFLICT DO NOTHING;
