-- case_timeline — the single, ALWAYS-CURRENT case-file ledger per matter.
-- A VIEW (not a materialized table) so it never goes stale: every document, correspondence
-- event, and deadline for a matter, unified + dated, computed live on read. The continuous
-- corpus sweep (case_corpus_sweep.sh on a timer) keeps the underlying DATA complete; this view
-- keeps the HISTORY current with zero rebuild. Retrieve with: scripts/case_file.py <MATTER>.
CREATE OR REPLACE VIEW case_timeline AS
SELECT l.matter_code AS matter,
       coalesce(left(d.doc_date,10),'') AS event_date,
       CASE WHEN coalesce(d.original_filename,'') ~* 'nsr|notice of submission|resolution|order|osca|disposition|referral report|indorsement'
            THEN 'disposition'
            WHEN coalesce(d.original_filename,'') ~* 'complaint|affidavit|manifestation|rejoinder|counter|reply|cease|petition'
            THEN 'filing' ELSE 'document' END AS event_type,
       coalesce(nullif(d.original_filename,''), d.smart_filename, 'document') AS title,
       'doc:'||d.id AS ref,
       'https://leo.hayuma.org/files/c/'||d.id AS link, d.id AS sort_id
FROM documents d JOIN document_matter_links l ON l.doc_id=d.id
UNION ALL
SELECT matter_code, coalesce(left(claimed_date::text,10),''), 'correspondence',
       coalesce(nullif(subject,''),'(correspondence)'), 'corr:'||id, NULL, id
FROM correspondence_events
UNION ALL
SELECT case_file, coalesce(left(due_date::text,10),''), 'deadline',
       coalesce(nullif(title,''),'(deadline)'), 'deadline:'||id, NULL, id
FROM case_deadlines;
