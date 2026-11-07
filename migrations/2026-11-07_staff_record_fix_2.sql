-- Record fix 2, 7 November 2026 (Asia/Manila). Claude (Mac desk), on Jonathan's go.
-- Follows 2026-11-07_staff_record_fix_1_APPLIED.sql. Correction id: rf-2026-11-07-b.
-- APPLIED to production 2026-11-07 01:45:08 UTC (09:45 Asia/Manila), this file with the final ROLLBACK changed to
-- COMMIT, after a rehearsal (apply; re-apply refused; fix-1 undo refused while this is applied; this undo restored the
-- fix-1 fingerprint 173a8325ab832f07614eb664cbc99065 exactly; a second undo refused; undo refused after an edit).
--
-- Why (ChatGPT's review of fix 1, confirmed against the live rows by Claude):
--   1. gmail_messages 152685 does NOT mention SEC Bicol. It is SEC CRMD's 4 Nov reply: SEC no longer takes this by
--      email; file through an iMessage ticket. Card 96 and Task 1 cited it as support for "forwarded to SEC Bicol".
--      The Bicol fact rests only on Kristyle's own report, channel_messages 3332. Each claim now carries its own source.
--   2. "The corporate TIN and Form 2303 have not been issued" claims more than her reports establish (they establish
--      waiting). Now: "No corporate TIN or Form 2303 is recorded yet."
--   3. Exams 28 and 193 also forbid the rewind phrases Leo actually sent her (messages 3232, 3339, 3349).
--
-- Safety: locks its rows; refuses unless they are exactly as fix 1 left them; refuses a second apply; snapshots every
-- row's before and after values into staff_record_fix_log (kept for audit); checks that every update changed its row.
-- Undo: 2026-11-07_staff_record_fix_2_UNDO.sql restores the logged before-values and refuses if anything changed since.
-- Ends in ROLLBACK. Change to COMMIT only on Jonathan's go.

BEGIN;

CREATE TABLE IF NOT EXISTS staff_record_fix_log (
    id             bigserial   PRIMARY KEY,
    correction_id  text        NOT NULL,
    table_name     text        NOT NULL,
    row_id         bigint      NOT NULL,
    before         jsonb       NOT NULL,
    after          jsonb,
    applied_at     timestamptz NOT NULL DEFAULT now(),
    undone_at      timestamptz,
    UNIQUE (correction_id, table_name, row_id)
);
COMMENT ON TABLE staff_record_fix_log IS
  'Before/after snapshots of hand corrections to staff_knowledge / staff_task / staff_exam, keyed by correction id. '
  'Undo scripts restore from here and refuse when current values differ from the logged after-values.';

-- Lock the targets before reading them.
SELECT id FROM staff_knowledge WHERE id IN (95, 96) FOR UPDATE;
SELECT id FROM staff_task      WHERE id IN (1, 2)   FOR UPDATE;
SELECT id FROM staff_exam      WHERE id IN (28, 193) FOR UPDATE;

-- Expected state: exactly what fix 1 wrote, and not already applied.
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM staff_record_fix_log WHERE correction_id = 'rf-2026-11-07-b') THEN
    RAISE EXCEPTION 'rf-2026-11-07-b already applied';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM staff_knowledge WHERE id = 95 AND state = 'live'
                   AND matter_code = 'LANDTEK-OPC-FORMATION' AND topic = 'bir' AND card_key = 'orus_1903_submitted'
                   AND fact LIKE '%The corporate TIN and Form 2303 have not been issued. The company still has no corporate TIN.%') THEN
    RAISE EXCEPTION 'card 95 is not as fix 1 left it';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM staff_knowledge WHERE id = 96 AND state = 'live'
                   AND matter_code = 'LANDTEK-OPC-FORMATION' AND topic = 'sec_fy' AND card_key = 'forwarded_to_bicol'
                   AND source_ref = 'channel_messages:3332; gmail_messages:152685') THEN
    RAISE EXCEPTION 'card 96 is not as fix 1 left it';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM staff_task WHERE id = 1 AND state = 'open'
                   AND title = 'Fiscal year correction: waiting for SEC.'
                   AND materials LIKE '%Reported in channel_messages 3332 and gmail_messages 152685: the fiscal year correction request was forwarded to SEC Bicol and the documents were emailed.%') THEN
    RAISE EXCEPTION 'task 1 is not as fix 1 left it';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM staff_task WHERE id = 2 AND state = 'open'
                   AND title = 'BIR registration (Form 1903): waiting for BIR.'
                   AND how LIKE '%The corporate TIN and Form 2303 have not been issued yet.%'
                   AND proof_needed LIKE '%The corporate TIN and Form 2303 have not been issued yet; send those when BIR issues them.%'
                   AND materials LIKE '%The corporate TIN and Form 2303 have not been issued. The company still has no corporate TIN.%') THEN
    RAISE EXCEPTION 'task 2 is not as fix 1 left it';
  END IF;
  IF (SELECT count(*) FROM staff_exam WHERE id IN (28, 193) AND active
        AND must_not = ARRAY['get the corporate TIN through|go to business.gov.ph|start at the Philippine Business Hub']) <> 2 THEN
    RAISE EXCEPTION 'exams 28/193 are not as fix 1 left them';
  END IF;
END
$guard$;

-- Snapshot before-values.
INSERT INTO staff_record_fix_log (correction_id, table_name, row_id, before)
SELECT 'rf-2026-11-07-b', 'staff_knowledge', id, jsonb_build_object('fact', fact, 'source_ref', source_ref)
  FROM staff_knowledge WHERE id IN (95, 96)
UNION ALL
SELECT 'rf-2026-11-07-b', 'staff_task', id, jsonb_build_object('how', how, 'materials', materials, 'proof_needed', proof_needed)
  FROM staff_task WHERE id IN (1, 2)
UNION ALL
SELECT 'rf-2026-11-07-b', 'staff_exam', id, jsonb_build_object('must_not', to_jsonb(must_not), 'note', note)
  FROM staff_exam WHERE id IN (28, 193);

-- 1. Card 95: claim only what the sources establish.
UPDATE staff_knowledge
   SET fact = replace(fact,
         'The corporate TIN and Form 2303 have not been issued. The company still has no corporate TIN.',
         'No corporate TIN or Form 2303 is recorded yet.'),
       updated_at = now()
 WHERE id = 95;

-- 2. Card 96: each claim carries its own source.
UPDATE staff_knowledge
   SET fact = $fact$The fiscal year correction request was forwarded to SEC Bicol and the documents were emailed (reported by Kristyle, proof pending). The Articles say the fiscal year runs 31 December to 30 December; it should be 1 January to 31 December. Separately, on 4 November SEC's CRMD desk replied that it no longer takes this by email and to file through an iMessage ticket. Do not open a new SEC iMessage ticket and do not resend the request. Next is the SEC reply. This no longer has to be finished before the ORUS filing that was already submitted.$fact$,
       source_ref = 'channel_messages:3332 (forwarded to SEC Bicol, documents emailed); gmail_messages:152685 (SEC CRMD 4 Nov: file through an iMessage ticket)',
       updated_at = now()
 WHERE id = 96;

-- 3. Task 1 status note: same split of sources.
UPDATE staff_task
   SET materials = replace(materials,
         'Reported in channel_messages 3332 and gmail_messages 152685: the fiscal year correction request was forwarded to SEC Bicol and the documents were emailed.',
         'Reported in channel_messages 3332: the fiscal year correction request was forwarded to SEC Bicol and the documents were emailed. Separately, on 4 November SEC''s CRMD desk replied that it no longer takes this by email and to file through an iMessage ticket (gmail_messages 152685).'),
       updated_at = now()
 WHERE id = 1;

-- 4. Task 2: "not recorded yet", not "not issued".
UPDATE staff_task
   SET how = replace(how, 'The corporate TIN and Form 2303 have not been issued yet.',
                          'No corporate TIN or Form 2303 is recorded yet.'),
       proof_needed = replace(proof_needed, 'The corporate TIN and Form 2303 have not been issued yet; send those when BIR issues them.',
                                            'No corporate TIN or Form 2303 is recorded yet; send them when BIR issues them.'),
       materials = replace(materials, 'The corporate TIN and Form 2303 have not been issued. The company still has no corporate TIN.',
                                      'No corporate TIN or Form 2303 is recorded yet.'),
       updated_at = now()
 WHERE id = 2;

-- 5. Exams 28 and 193: also forbid the rewind phrases Leo actually sent (3232, 3339, 3349).
UPDATE staff_exam
   SET must_not = ARRAY['get the corporate TIN through|go to business.gov.ph|start at the Philippine Business Hub|register the company with BIR online|then register with BIR|the next step is to register'],
       note = coalesce(note, '') || ' | rf-2026-11-07-b: also forbids the rewind phrases Leo sent on 4 and 7 Nov.'
 WHERE id IN (28, 193);

-- Snapshot after-values.
UPDATE staff_record_fix_log l
   SET after = CASE l.table_name
       WHEN 'staff_knowledge' THEN (SELECT jsonb_build_object('fact', fact, 'source_ref', source_ref) FROM staff_knowledge WHERE id = l.row_id)
       WHEN 'staff_task'      THEN (SELECT jsonb_build_object('how', how, 'materials', materials, 'proof_needed', proof_needed) FROM staff_task WHERE id = l.row_id)
       WHEN 'staff_exam'      THEN (SELECT jsonb_build_object('must_not', to_jsonb(must_not), 'note', note) FROM staff_exam WHERE id = l.row_id)
   END
 WHERE l.correction_id = 'rf-2026-11-07-b';

-- Guards: 6 rows logged, every one actually changed, and the old wording is gone from every live source.
DO $guard$
DECLARE n_logged int; n_changed int;
BEGIN
  SELECT count(*), count(*) FILTER (WHERE after IS DISTINCT FROM before)
    INTO n_logged, n_changed FROM staff_record_fix_log WHERE correction_id = 'rf-2026-11-07-b';
  IF n_logged <> 6 OR n_changed <> 6 THEN
    RAISE EXCEPTION 'rf-2026-11-07-b: expected 6 rows logged and changed, got % logged, % changed', n_logged, n_changed;
  END IF;
  IF EXISTS (SELECT 1 FROM staff_knowledge WHERE state = 'live' AND matter_code = 'LANDTEK-OPC-FORMATION'
               AND (fact LIKE '%have not been issued%' OR source_ref LIKE '%3332; gmail_messages:152685')) THEN
    RAISE EXCEPTION 'rf-2026-11-07-b: old wording or citation still in a live card';
  END IF;
  IF EXISTS (SELECT 1 FROM staff_task WHERE id IN (1, 2)
               AND (how LIKE '%have not been issued%' OR proof_needed LIKE '%have not been issued%'
                    OR materials LIKE '%have not been issued%' OR materials LIKE '%3332 and gmail_messages 152685%')) THEN
    RAISE EXCEPTION 'rf-2026-11-07-b: old wording or citation still in task 1 or 2';
  END IF;
END
$guard$;

-- After snapshot.
SELECT table_name, row_id, after IS DISTINCT FROM before AS changed FROM staff_record_fix_log
 WHERE correction_id = 'rf-2026-11-07-b' ORDER BY table_name, row_id;
SELECT id, source_ref, fact FROM staff_knowledge WHERE id IN (95, 96) ORDER BY id;
SELECT id, how, proof_needed, materials FROM staff_task WHERE id IN (1, 2) ORDER BY id;
SELECT id, question, must_not, note FROM staff_exam WHERE id IN (28, 193) ORDER BY id;

ROLLBACK;
