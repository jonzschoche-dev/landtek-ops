-- Layer B: multi-attribution + time axes for client_history (deploy_155).
--
-- Per Jonathan 2026-05-17: events touch MULTIPLE matters, MULTIPLE titles,
-- MULTIPLE parties — a single matter_code TEXT and single event_date can't
-- represent reality. The void-SPA case turns on the gap between SPA-executed
-- and SPA-revoked dates on the same legal act, so we need separate timing
-- axes for executed/filed/received.

BEGIN;

ALTER TABLE client_history
  ADD COLUMN IF NOT EXISTS matter_codes  text[]  DEFAULT '{}'::text[],
  ADD COLUMN IF NOT EXISTS title_refs    text[]  DEFAULT '{}'::text[],
  ADD COLUMN IF NOT EXISTS party_refs    int[]   DEFAULT '{}'::int[],
  ADD COLUMN IF NOT EXISTS date_executed date,
  ADD COLUMN IF NOT EXISTS date_filed    date,
  ADD COLUMN IF NOT EXISTS date_received date;

COMMENT ON COLUMN client_history.matter_codes IS
  'Multi-attribution: matter_codes this event pertains to (a doc can serve multiple matters).';
COMMENT ON COLUMN client_history.title_refs IS
  'TCT numbers this event touches (e.g., {T-4497,T-32917}).';
COMMENT ON COLUMN client_history.party_refs IS
  'Entity IDs (transferees/entities) involved in this event.';
COMMENT ON COLUMN client_history.date_executed IS
  'Date the legal act was executed/signed/notarized (distinct from filing/receipt).';
COMMENT ON COLUMN client_history.date_filed IS
  'Date the document was filed with a court/RD/agency.';
COMMENT ON COLUMN client_history.date_received IS
  'Date the document was received (correspondence) or actioned.';

-- GIN indexes for array membership queries
CREATE INDEX IF NOT EXISTS idx_chist_matter_codes ON client_history USING GIN (matter_codes);
CREATE INDEX IF NOT EXISTS idx_chist_title_refs   ON client_history USING GIN (title_refs);
CREATE INDEX IF NOT EXISTS idx_chist_party_refs   ON client_history USING GIN (party_refs);

-- ── BACKFILL ───────────────────────────────────────────────────────────

-- 1. matter_codes: seed from existing matter_code text column
UPDATE client_history h
   SET matter_codes = ARRAY[h.matter_code]
 WHERE h.matter_code IS NOT NULL
   AND (h.matter_codes IS NULL OR h.matter_codes = '{}');

-- 2. matter_codes: if matter_code is null but case_file maps to exactly one matter, use it
UPDATE client_history h
   SET matter_codes = ARRAY[m.matter_code]
  FROM matters m
 WHERE h.case_file = m.case_file
   AND (h.matter_codes IS NULL OR h.matter_codes = '{}')
   AND h.matter_code IS NULL;

-- 3. title_refs: extract TCT references from doc-derived rows.
--    Sources: documents.original_filename + smart_filename + document_title + extracted_text.
WITH doc_titles AS (
  SELECT d.id,
         array_agg(DISTINCT m[1]) FILTER (WHERE m[1] IS NOT NULL) AS tct_list
    FROM documents d
    LEFT JOIN LATERAL regexp_matches(
      coalesce(d.smart_filename,'') || ' ' ||
      coalesce(d.original_filename,'') || ' ' ||
      coalesce(d.document_title,'') || ' ' ||
      coalesce(LEFT(d.extracted_text, 5000),''),
      '(?:TCT[\s\-_]*|OCT[\s\-_]*|T[\s\-_]+)(\d{2,7}(?:[-_]\d+)?)',
      'gi'
    ) m ON true
   GROUP BY d.id
)
UPDATE client_history h
   SET title_refs = (
     SELECT ARRAY_AGG(DISTINCT
       CASE WHEN tct ~ '^[0-9]' THEN 'T-' || tct ELSE tct END
     )
       FROM unnest(dt.tct_list) tct
   )
  FROM doc_titles dt
 WHERE h.source_table = 'documents'
   AND h.source_id = dt.id::text
   AND dt.tct_list IS NOT NULL
   AND (h.title_refs IS NULL OR h.title_refs = '{}');

-- 4. title_refs: title_transfers rows have parent_title + derivative_title directly
UPDATE client_history h
   SET title_refs = (
     SELECT array_remove(ARRAY[tt.parent_title, tt.derivative_title], NULL)
   )
  FROM title_transfers tt
 WHERE h.source_table = 'title_transfers'
   AND h.source_id = tt.id::text
   AND (h.title_refs IS NULL OR h.title_refs = '{}');

-- 5. title_refs: instruments_on_title rows have parent_tct_number
UPDATE client_history h
   SET title_refs = ARRAY[iot.parent_tct_number]
  FROM instruments_on_title iot
 WHERE h.source_table = 'instruments_on_title'
   AND h.source_id = iot.id::text
   AND iot.parent_tct_number IS NOT NULL
   AND (h.title_refs IS NULL OR h.title_refs = '{}');

-- 6. party_refs: title_transfers carry transferee_id
UPDATE client_history h
   SET party_refs = ARRAY[tt.transferee_id]
  FROM title_transfers tt
 WHERE h.source_table = 'title_transfers'
   AND h.source_id = tt.id::text
   AND tt.transferee_id IS NOT NULL
   AND (h.party_refs IS NULL OR h.party_refs = '{}');

-- 7. date_received: gmail-derived rows use received_at
UPDATE client_history h
   SET date_received = g.received_at::date
  FROM gmail_messages g
 WHERE h.source_table = 'gmail_messages'
   AND h.source_id = g.id::text
   AND g.received_at IS NOT NULL
   AND h.date_received IS NULL;

-- 8. date_filed: documents with execution_status='executed_filed' use doc_date_norm
UPDATE client_history h
   SET date_filed = d.doc_date_norm
  FROM documents d
 WHERE h.source_table = 'documents'
   AND h.source_id = d.id::text
   AND d.execution_status = 'executed_filed'
   AND d.doc_date_norm IS NOT NULL
   AND h.date_filed IS NULL;

-- 9. date_executed: documents with execution_status='executed_notarized'/'government_issued' use doc_date_norm
UPDATE client_history h
   SET date_executed = d.doc_date_norm
  FROM documents d
 WHERE h.source_table = 'documents'
   AND h.source_id = d.id::text
   AND d.execution_status IN ('executed_notarized','government_issued')
   AND d.doc_date_norm IS NOT NULL
   AND h.date_executed IS NULL;

-- 10. date_executed: title_transfers use transfer_date
UPDATE client_history h
   SET date_executed = tt.transfer_date
  FROM title_transfers tt
 WHERE h.source_table = 'title_transfers'
   AND h.source_id = tt.id::text
   AND tt.transfer_date IS NOT NULL
   AND h.date_executed IS NULL;

-- 11. date_executed: instruments_on_title use entry_date as the closest proxy
UPDATE client_history h
   SET date_executed = iot.entry_date
  FROM instruments_on_title iot
 WHERE h.source_table = 'instruments_on_title'
   AND h.source_id = iot.id::text
   AND iot.entry_date IS NOT NULL
   AND h.date_executed IS NULL;

-- Report
SELECT 'with_matter_codes' AS metric, COUNT(*) FROM client_history WHERE matter_codes <> '{}'
UNION ALL SELECT 'with_title_refs',   COUNT(*) FROM client_history WHERE title_refs <> '{}'
UNION ALL SELECT 'with_party_refs',   COUNT(*) FROM client_history WHERE party_refs <> '{}'
UNION ALL SELECT 'with_date_executed',COUNT(*) FROM client_history WHERE date_executed IS NOT NULL
UNION ALL SELECT 'with_date_filed',   COUNT(*) FROM client_history WHERE date_filed IS NOT NULL
UNION ALL SELECT 'with_date_received',COUNT(*) FROM client_history WHERE date_received IS NOT NULL
UNION ALL SELECT 'total_rows',        COUNT(*) FROM client_history;

COMMIT;
