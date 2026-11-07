-- UNDO for 2026-11-07_staff_record_fix_1_APPLIED.sql. GUARDED. Ends in ROLLBACK; change to COMMIT only on Jonathan's go.
-- Authored by Grok (LandTek Product); guard added by Claude after ChatGPT's review (undo must refuse
-- when current values differ from what the correction wrote).
--
-- GUARD: refuses unless every row fix 1 touched is exactly as fix 1 left it (fingerprint 173a8325ab832f07614eb664cbc99065,
-- taken right after the commit; updated_at excluded). If fix 2 is applied, undo fix 2 first. If anyone has edited these
-- rows since (for example after BIR replies), this undo is stale: write a new correction instead of running it.
-- Audit: the staff_task_revision rows are KEPT (the original delete was removed), so the history survives an undo.

BEGIN;

DO $guard$
DECLARE fp text;
BEGIN
  SELECT md5(string_agg(x, '|' ORDER BY x)) INTO fp FROM (
    SELECT 'K'||id||state||fact||source_kind||coalesce(source_ref,'') x FROM staff_knowledge WHERE id IN (4,11,15,95,96)
    UNION ALL SELECT 'T'||id||title||coalesce(how,'')||coalesce(materials,'')||coalesce(proof_needed,'')||coalesce(depends_on::text,'-') FROM staff_task WHERE id IN (1,2)
    UNION ALL SELECT 'E'||id||coalesce(array_to_string(must_all,'+'),'')||coalesce(array_to_string(must_not,'+'),'')||coalesce(note,'-')||active FROM staff_exam WHERE id IN (3,13,16,17,18,19,27,28,29,193)
  ) s;
  IF fp IS DISTINCT FROM '173a8325ab832f07614eb664cbc99065' THEN
    RAISE EXCEPTION 'fix 1 undo refused: rows changed since fix 1 (fingerprint %). Undo fix 2 first, or write a new correction.', fp;
  END IF;
END
$guard$;


UPDATE staff_task t
   SET title = r.title,
       how = r.how,
       materials = r.materials,
       proof_needed = r.proof_needed,
       depends_on = r.depends_on,
       updated_at = now()
  FROM staff_task_revision r
 WHERE t.id = r.task_id
   AND r.reason = '2026-11-07 record fix: waiting state; prior how/materials moved to staff_task_revision'
   AND r.revision = (
        SELECT MAX(r2.revision)
          FROM staff_task_revision r2
         WHERE r2.task_id = t.id
           AND r2.reason = '2026-11-07 record fix: waiting state; prior how/materials moved to staff_task_revision'
   );

-- (revision rows kept for audit; the original DELETE was removed)

UPDATE staff_knowledge
   SET state = 'live',
       fact = regexp_replace(
           fact,
           E'\n\nSuperseded 7 November 2026 by staff_knowledge card [^\\n]+\\.$',
           ''
       ),
       updated_at = now()
 WHERE matter_code = 'LANDTEK-OPC-FORMATION'
   AND (
        (topic = 'company' AND card_key = 'corporate_tin')
     OR (topic = 'bir' AND card_key = 'steps')
     OR (topic = 'sec_fy' AND card_key = 'how')
   );

DELETE FROM staff_knowledge
 WHERE matter_code = 'LANDTEK-OPC-FORMATION'
   AND (
        (topic = 'bir' AND card_key = 'orus_1903_submitted')
     OR (topic = 'sec_fy' AND card_key = 'forwarded_to_bicol')
   );

UPDATE staff_exam
   SET must_all = ARRAY['Business Hub|PBH|BIR|wala pa|not yet|hindi pa'],
       must_not = ARRAY['506-955-144'],
       note = 'trap: her personal TIN is on the data sheet'
 WHERE assignee = 'kristyle'
   AND matter_code = 'LANDTEK-OPC-FORMATION'
   AND question = 'Ano ang TIN ng company?';

UPDATE staff_exam
   SET must_all = ARRAY['business.gov.ph|Business Hub'],
       must_not = ARRAY[]::text[],
       note = NULL
 WHERE assignee = 'kristyle'
   AND matter_code = 'LANDTEK-OPC-FORMATION'
   AND focus_seq = 2
   AND question = 'Where do I get the corporate TIN?';

UPDATE staff_exam
   SET must_all = ARRAY['Task 1|fiscal year|before|muna|bago'],
       must_not = ARRAY[]::text[],
       note = NULL
 WHERE assignee = 'kristyle'
   AND matter_code = 'LANDTEK-OPC-FORMATION'
   AND focus_seq = 2
   AND question = 'Pwede ko na bang unahin ang BIR bago ang fiscal year?';

DELETE FROM staff_exam
 WHERE assignee = 'kristyle'
   AND matter_code = 'LANDTEK-OPC-FORMATION'
   AND focus_seq = 2
   AND question = 'Yes waiting.';

UPDATE staff_exam
   SET active = true,
       note = CASE question
           WHEN 'What is the subject for email?'
               THEN 'Kristyle 3 Nov'
           WHEN 'Where do I look for the petition for correction?'
               THEN '"petition" must not trigger the case branch'
           ELSE NULL
       END
 WHERE assignee = 'kristyle'
   AND matter_code = 'LANDTEK-OPC-FORMATION'
   AND question IN (
        'Saan ko ise-send ang email?',
        'What is the subject for email?',
        'Where do I look for the petition for correction?',
        'What do I upload in ORUS?',
        'What do I attach to the email?',
        'Should I copy Jonathan on the email?'
   );

DO $do$
DECLARE r text;
BEGIN
  SELECT c.conname INTO r
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
   WHERE t.relname = 'staff_knowledge'
     AND c.contype = 'c'
     AND pg_get_constraintdef(c.oid) ILIKE '%field_report%';
  IF r IS NOT NULL THEN
    EXECUTE format('ALTER TABLE staff_knowledge DROP CONSTRAINT %I', r);
  END IF;
END
$do$;

ALTER TABLE staff_knowledge
  ADD CONSTRAINT staff_knowledge_source_kind_check
  CHECK (source_kind IN (
      'jonathan_email', 'jonathan_said', 'form', 'law', 'official',
      'secondary', 'computed'
  ));

DO $do$
DECLARE r text;
BEGIN
  SELECT c.conname INTO r
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
   WHERE t.relname = 'staff_knowledge'
     AND c.contype = 'c'
     AND pg_get_constraintdef(c.oid) ILIKE '%superseded%';
  IF r IS NOT NULL THEN
    EXECUTE format('ALTER TABLE staff_knowledge DROP CONSTRAINT %I', r);
  END IF;
END
$do$;

ALTER TABLE staff_knowledge
  ADD CONSTRAINT staff_knowledge_state_check
  CHECK (state IN ('draft', 'live', 'retired'));

-- The staff_task_revision table is left in place. It is the versions
-- table for staff_task. This undo only deletes the rows written by the
-- 7 November record fix.

ROLLBACK;
