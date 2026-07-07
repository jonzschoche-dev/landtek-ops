-- deploy_766_incorporation_status.sql — Phase 3: governed visibility into data-incorporation status.
-- Read-only views + a tiny append-only trend log. The 5-signal predicates MIRROR
-- truth_tests/test_connected_document_count.py (A41 / ONTOLOGY §2.17) EXACTLY, so the reported numbers
-- can NEVER drift from the truth test. This only SURFACES existing state — no connectivity/provenance
-- logic is added or changed here. Idempotent (CREATE OR REPLACE / IF NOT EXISTS).

-- Per-document 5-signal connectivity. `connected` = all 5 (the A41 ConnectedDocument).
CREATE OR REPLACE VIEW v_doc_connectivity AS
SELECT d.id, d.case_file,
  (coalesce(length(d.extracted_text),0) >= 50)                                              AS sig_text,
  (d.model_used IS NOT NULL)                                                                AS sig_provenance,
  (d.document_type IS NOT NULL)                                                             AS sig_type,
  EXISTS (SELECT 1 FROM ocr_quality q WHERE q.doc_id = d.id)                                AS sig_quality,
  EXISTS (SELECT 1 FROM corpus_backfill_state c WHERE c.doc_id = d.id AND c.embedded IS TRUE) AS sig_embedded,
  ( (coalesce(length(d.extracted_text),0) >= 50)
    AND d.model_used IS NOT NULL
    AND d.document_type IS NOT NULL
    AND EXISTS (SELECT 1 FROM ocr_quality q WHERE q.doc_id = d.id)
    AND EXISTS (SELECT 1 FROM corpus_backfill_state c WHERE c.doc_id = d.id AND c.embedded IS TRUE)
  )                                                                                          AS connected,
  coalesce((SELECT flagged FROM ocr_quality q WHERE q.doc_id = d.id), false)                AS flagged
FROM documents d;

COMMENT ON VIEW v_doc_connectivity IS
  'Per-document 5-signal connectivity (A41/ONTOLOGY §2.17). Predicates IDENTICAL to '
  'truth_tests/test_connected_document_count.py. connected = all 5 signals. Read-only, no side effects.';

-- Per-matter (case_file) incorporation status, with a corpus-wide TOTAL rollup row.
CREATE OR REPLACE VIEW v_incorporation_status AS
SELECT
  CASE WHEN GROUPING(case_file) = 1 THEN 'ALL (corpus)' ELSE coalesce(case_file, '(unfiled)') END AS matter,
  GROUPING(case_file)                                                          AS is_total,
  count(*)                                                                     AS total,
  count(*) FILTER (WHERE connected)                                            AS connected,
  round(100.0 * count(*) FILTER (WHERE connected) / nullif(count(*), 0), 1)    AS connected_pct,
  count(*) FILTER (WHERE sig_provenance)                                       AS provenance_earned,
  count(*) FILTER (WHERE sig_text)                                             AS w_text,
  count(*) FILTER (WHERE sig_type)                                             AS w_type,
  count(*) FILTER (WHERE sig_quality)                                          AS w_quality,
  count(*) FILTER (WHERE sig_embedded)                                         AS w_embedded,
  count(*) FILTER (WHERE flagged AND NOT connected)                            AS stuck_flagged
FROM v_doc_connectivity
GROUP BY GROUPING SETS ((case_file), ());

COMMENT ON VIEW v_incorporation_status IS
  'Data-incorporation health per matter (case_file) + a TOTAL rollup (is_total=1). Mirrors A41. '
  'connected/provenance_earned reconcile to test_connected_document_count.py. Read-only.';

-- Tiny append-only trend log (one snapshot per day) — high-water mark + progress/regression visibility.
CREATE TABLE IF NOT EXISTS incorporation_log (
  snapshot_date date PRIMARY KEY,
  total       int,
  connected   int,
  provenance  int,
  stuck       int,
  per_matter  jsonb,
  logged_at   timestamptz DEFAULT now()
);

COMMENT ON TABLE incorporation_log IS
  'Daily incorporation snapshot (appended by scripts/incorporation_status.py --log). One row/day; '
  'lets connected-count progress/regression and the high-water mark be seen over time.';
