-- deploy_083: case_keywords correlation views (created 2026-05-16)
-- Used by 'Auto-Correct Case File' node in workflow.

CREATE OR REPLACE VIEW documents_keyword_vote AS
WITH matches AS (
  SELECT d.id AS doc_id,
         d.case_file AS gpt_case_file,
         ck.case_file AS keyword_case_file,
         sum(ck.weight) AS total_weight,
         array_agg(ck.keyword ORDER BY ck.weight DESC) AS matched_keywords
    FROM documents d
    JOIN case_keywords ck
      ON d.extracted_text IS NOT NULL
     AND d.extracted_text != ''
     AND d.extracted_text ILIKE '%' || ck.keyword || '%'
   GROUP BY d.id, d.case_file, ck.case_file
), ranked AS (
  SELECT *, row_number() OVER (PARTITION BY doc_id ORDER BY total_weight DESC) AS rank
    FROM matches
)
SELECT doc_id, gpt_case_file,
       keyword_case_file AS top_keyword_case_file,
       total_weight, matched_keywords,
       (gpt_case_file IS DISTINCT FROM keyword_case_file
        AND NOT (gpt_case_file IS NULL AND keyword_case_file IS NULL)) AS classification_conflict
  FROM ranked WHERE rank = 1;

CREATE OR REPLACE VIEW classification_conflicts AS
SELECT v.doc_id, v.gpt_case_file, v.top_keyword_case_file, v.total_weight,
       v.matched_keywords[1:5] AS top_keywords,
       d.original_filename, d.timestamp
  FROM documents_keyword_vote v JOIN documents d ON d.id = v.doc_id
 WHERE classification_conflict AND total_weight >= 5.0
 ORDER BY total_weight DESC;
