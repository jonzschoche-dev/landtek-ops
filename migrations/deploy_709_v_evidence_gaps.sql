-- deploy_709_v_evidence_gaps.sql — gaps become a DERIVED query, not an asserted value.
-- THE single source of "what evidence is missing". The strategist CONSUMES this; it never asserts
-- gaps in prose. "missing" is derived: a register gap with NO plausible corpus document is real; one
-- WITH candidate docs is flagged possibly_held (verify). This catches the #4/#5 phantom-gap class
-- structurally in the data model, replacing the runtime LLM-prose checks (deploy_707/708, now removed).
-- Precision of the corpus match is bounded by document metadata — improving that is the next investment.

CREATE OR REPLACE VIEW v_evidence_gaps AS
SELECT
  'transfer:'||tds.transfer_id||':req:'||tds.requirement_id AS gap_key,
  tt.case_file,
  coalesce(tt.instrument_type, '(requirement '||tds.requirement_id||')') AS needed,
  tt.transferee_name, tt.derivative_title,
  tds.status AS register_status,
  cand.docs AS candidate_docs,
  CASE WHEN cand.docs IS NULL THEN 'missing' ELSE 'possibly_held' END AS derived_status
FROM transfer_doc_status tds
JOIN title_transfers tt ON tt.id = tds.transfer_id
LEFT JOIN LATERAL (
  SELECT array_agg(d.id ORDER BY d.id) AS docs
  FROM documents d
  WHERE d.case_file = tt.case_file
    AND length(trim(regexp_replace(coalesce(tt.instrument_type,''), '\([^)]*\)', '', 'g'))) > 3
    AND to_tsvector('simple',
          lower(coalesce(d.document_title,'')||' '||coalesce(d.original_filename,'')||' '||coalesce(d.file_name,'')))
        @@ plainto_tsquery('simple',
          regexp_replace(lower(coalesce(tt.instrument_type,'')), '\([^)]*\)', '', 'g'))
) cand ON true
WHERE tds.status IN ('missing','gap') AND tds.evidence_doc_id IS NULL

UNION ALL

SELECT
  'record:'||rg.id AS gap_key,
  rg.matter_code AS case_file,
  rg.reference AS needed,
  NULL, NULL,
  rg.status AS register_status,
  CASE WHEN rg.found_doc_id IS NOT NULL THEN ARRAY[rg.found_doc_id] ELSE NULL END AS candidate_docs,
  CASE WHEN rg.found_doc_id IS NOT NULL THEN 'held' ELSE 'missing' END AS derived_status
FROM record_gaps rg
WHERE coalesce(rg.status,'open') <> 'resolved';
