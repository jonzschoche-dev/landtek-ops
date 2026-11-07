-- APPLIED to production 2026-11-07 01:34:45 UTC (09:34 Asia/Manila) by Claude (Mac desk) on Jonathan's go.
-- Authored by Grok (LandTek Product), reviewed by Claude in four rounds, dry-run + apply/undo round trip passed first.
-- This is the exact file that ran (STAGED.sql md5 0ac240790dc7dfde4251919f4eb908e5 with the final ROLLBACK changed to COMMIT).
-- Undo: 2026-11-07_staff_record_fix_1_UNDO.sql (guarded). Follow-up correction: 2026-11-07_staff_record_fix_2.sql.

-- Staged 7 November 2026 (Asia/Manila) by LandTek Product.
-- Fourth draft, after Claude's ambiguous-k and historical-exam review. NOT RUN.
-- Ends in ROLLBACK. After Jonathan authorizes apply, change the final
-- ROLLBACK to COMMIT and run once.
--
-- Cards by (matter_code, topic, card_key):
--   company / corporate_tin  = live card 4
--   bir / steps              = live card 11
--   sec_fy / how             = live card 15
-- Tasks: staff_task seq 1 and 2, source_ref gmail_messages:152157
-- Exams matched by question text (live ids 13, 28, 29)
--
-- Does not write an application number, an RDO number, a filing timestamp,
-- or Kristyle's personal TIN digits into any live source Leo reads.

BEGIN;

CREATE TEMP TABLE _fix_counts (k text PRIMARY KEY, n int);

-- ---------------------------------------------------------------------------
-- 0. Before snapshot
-- ---------------------------------------------------------------------------
SELECT id, topic, card_key, state, fact, checked_on, source_kind, source_ref
  FROM staff_knowledge
 WHERE matter_code = 'LANDTEK-OPC-FORMATION'
   AND (
        (topic = 'company' AND card_key = 'corporate_tin')
     OR (topic = 'bir' AND card_key IN ('steps', 'orus_1903_submitted'))
     OR (topic = 'sec_fy' AND card_key IN ('how', 'forwarded_to_bicol'))
   )
 ORDER BY id;

SELECT id, seq, state, title, how, proof_needed, depends_on, proof_doc_id, updated_at,
       length(materials) AS materials_chars,
       left(materials, 200) AS materials_start
  FROM staff_task
 WHERE assignee = 'kristyle'
   AND matter_code = 'LANDTEK-OPC-FORMATION'
   AND source_ref = 'gmail_messages:152157'
   AND seq IN (1, 2)
 ORDER BY seq;

SELECT id, question, expect, must_all, must_not, unknown_ok, note, active
  FROM staff_exam
 WHERE assignee = 'kristyle'
   AND matter_code = 'LANDTEK-OPC-FORMATION'
   AND question IN (
        'Ano ang TIN ng company?',
        'Where do I get the corporate TIN?',
        'Pwede ko na bang unahin ang BIR bago ang fiscal year?',
        'Yes waiting.',
        'Saan ko ise-send ang email?',
        'What is the subject for email?',
        'Where do I look for the petition for correction?',
        'What do I upload in ORUS?',
        'What do I attach to the email?',
        'Should I copy Jonathan on the email?'
   )
 ORDER BY id;

SELECT id, direction, left(text_content, 200) AS text_start, sent_at
  FROM channel_messages
 WHERE id IN (3332, 3342, 3344, 3348, 3350, 3356)
 ORDER BY id;

SELECT id
  FROM gmail_messages
 WHERE id = 152685;

SELECT conname, pg_get_constraintdef(oid) AS def
  FROM pg_constraint
 WHERE conrelid = 'staff_knowledge'::regclass
   AND contype = 'c'
 ORDER BY conname;

-- ---------------------------------------------------------------------------
-- 1. Allow state = superseded and source_kind = field_report
-- ---------------------------------------------------------------------------
DO $do$
DECLARE r text;
BEGIN
  SELECT c.conname INTO r
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
   WHERE t.relname = 'staff_knowledge'
     AND c.contype = 'c'
     AND pg_get_constraintdef(c.oid) ILIKE '%live%'
     AND pg_get_constraintdef(c.oid) ILIKE '%retired%';
  IF r IS NOT NULL THEN
    EXECUTE format('ALTER TABLE staff_knowledge DROP CONSTRAINT %I', r);
  END IF;
END
$do$;

ALTER TABLE staff_knowledge
  ADD CONSTRAINT staff_knowledge_state_check
  CHECK (state IN ('draft', 'live', 'retired', 'superseded'));

DO $do$
DECLARE r text;
BEGIN
  SELECT c.conname INTO r
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
   WHERE t.relname = 'staff_knowledge'
     AND c.contype = 'c'
     AND pg_get_constraintdef(c.oid) ILIKE '%jonathan_said%';
  IF r IS NOT NULL THEN
    EXECUTE format('ALTER TABLE staff_knowledge DROP CONSTRAINT %I', r);
  END IF;
END
$do$;

ALTER TABLE staff_knowledge
  ADD CONSTRAINT staff_knowledge_source_kind_check
  CHECK (source_kind IN (
      'jonathan_email', 'jonathan_said', 'form', 'law', 'official',
      'secondary', 'computed', 'field_report'
  ));

-- ---------------------------------------------------------------------------
-- 2. Versions table: prior task text leaves the answerer's view
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS staff_task_revision (
    id            bigserial   PRIMARY KEY,
    task_id       bigint      NOT NULL REFERENCES staff_task(id),
    revision      integer     NOT NULL,
    title         text,
    how           text,
    materials     text,
    proof_needed  text,
    depends_on    bigint,
    saved_at      timestamptz NOT NULL DEFAULT now(),
    reason        text        NOT NULL,
    UNIQUE (task_id, revision)
);

WITH ins AS (
    INSERT INTO staff_task_revision (
        task_id, revision, title, how, materials, proof_needed, depends_on, reason
    )
    SELECT t.id,
           COALESCE(r.max_rev, 0) + 1,
           t.title, t.how, t.materials, t.proof_needed, t.depends_on,
           $reason$2026-11-07 record fix: waiting state; prior how/materials moved to staff_task_revision$reason$
      FROM staff_task t
      LEFT JOIN LATERAL (
          SELECT MAX(x.revision) AS max_rev
            FROM staff_task_revision x
           WHERE x.task_id = t.id
      ) r ON true
     WHERE t.assignee = 'kristyle'
       AND t.matter_code = 'LANDTEK-OPC-FORMATION'
       AND t.source_ref = 'gmail_messages:152157'
       AND t.seq IN (1, 2)
    RETURNING 1
)
INSERT INTO _fix_counts (k, n) SELECT 'revisions', count(*) FROM ins;

-- ---------------------------------------------------------------------------
-- 3. Supersede cards 4, 11 and 15; keep old text; point at replacements
-- ---------------------------------------------------------------------------
WITH u AS (
    UPDATE staff_knowledge
       SET state = 'superseded',
           fact = CASE
               WHEN fact LIKE '%Superseded 7 November 2026 by staff_knowledge card %'
               THEN fact
               ELSE fact || CASE topic
                   WHEN 'sec_fy' THEN E'\n\nSuperseded 7 November 2026 by staff_knowledge card sec_fy/forwarded_to_bicol.'
                   ELSE E'\n\nSuperseded 7 November 2026 by staff_knowledge card bir/orus_1903_submitted.'
               END
           END,
           updated_at = now()
     WHERE matter_code = 'LANDTEK-OPC-FORMATION'
       AND (
            (topic = 'company' AND card_key = 'corporate_tin')
         OR (topic = 'bir' AND card_key = 'steps')
         OR (topic = 'sec_fy' AND card_key = 'how')
       )
       AND state IN ('live', 'draft', 'retired')
    RETURNING 1
)
INSERT INTO _fix_counts (k, n) SELECT 'supersede_cards', count(*) FROM u;

-- ---------------------------------------------------------------------------
-- 4. Two new live cards, cited to field reports already in Postgres
-- ---------------------------------------------------------------------------
WITH i AS (
    INSERT INTO staff_knowledge (
        assignee, matter_code, topic, card_key, fact,
        source_kind, source_ref, checked_on, state
    ) VALUES (
        'kristyle',
        'LANDTEK-OPC-FORMATION',
        'bir',
        'orus_1903_submitted',
        $fact$Form 1903 was submitted on ORUS (reported by Kristyle, proof pending). Do not restart the Philippine Business Hub or file a new ORUS application. Next is the BIR reply. If ORUS emailed an acknowledgment, forward it to Jonathan. The corporate TIN and Form 2303 have not been issued. The company still has no corporate TIN. Kristyle's personal TIN on the data sheet is not the company's; never write it as the company TIN.$fact$,
        'field_report',
        'channel_messages:3342,3344,3348,3350,3356',
        DATE '2026-11-07',
        'live'
    ), (
        'kristyle',
        'LANDTEK-OPC-FORMATION',
        'sec_fy',
        'forwarded_to_bicol',
        $fact$The fiscal year correction request was forwarded to SEC Bicol and the documents were emailed (reported by Kristyle, proof pending). The Articles say the fiscal year runs 31 December to 30 December; it should be 1 January to 31 December. Do not open a new SEC iMessage ticket and do not resend the request. Next is the SEC reply. This no longer has to be finished before the ORUS filing that was already submitted.$fact$,
        'field_report',
        'channel_messages:3332; gmail_messages:152685',
        DATE '2026-11-07',
        'live'
    )
    ON CONFLICT (matter_code, topic, card_key) DO UPDATE
       SET fact = EXCLUDED.fact,
           source_kind = EXCLUDED.source_kind,
           source_ref = EXCLUDED.source_ref,
           checked_on = EXCLUDED.checked_on,
           state = 'live',
           updated_at = now()
    RETURNING (xmax = 0) AS inserted
)
INSERT INTO _fix_counts (k, n) SELECT 'insert_cards', count(*) FILTER (WHERE inserted) FROM i;

-- ---------------------------------------------------------------------------
-- 5. Task 2: waiting title and how; materials = status note only
-- ---------------------------------------------------------------------------
WITH u AS (
    UPDATE staff_task
       SET title = 'BIR registration (Form 1903): waiting for BIR.',
           how = $how$Form 1903 was submitted on ORUS (reported by Kristyle, proof pending). Do not restart the Philippine Business Hub or file a new ORUS application. Next is the BIR reply. If ORUS emailed an acknowledgment, forward it to Jonathan. The corporate TIN and Form 2303 have not been issued yet.$how$,
           proof_needed = $proof$If ORUS emailed an acknowledgment, forward it to Jonathan. The corporate TIN and Form 2303 have not been issued yet; send those when BIR issues them. Do not restart the Philippine Business Hub or ORUS.$proof$,
           materials = $status$SOURCE: current status as of 7 November 2026 (reported by Kristyle, proof pending)
Reported in channel_messages 3342, 3344, 3348, 3350 and 3356: Form 1903 was submitted on ORUS. Do not restart the Philippine Business Hub or file a new ORUS application. Next is the BIR reply. If ORUS emailed an acknowledgment, forward it to Jonathan. The corporate TIN and Form 2303 have not been issued. The company still has no corporate TIN. Kristyle's personal TIN on the data sheet is not the company's.$status$,
           depends_on = NULL,
           updated_at = now()
     WHERE assignee = 'kristyle'
       AND matter_code = 'LANDTEK-OPC-FORMATION'
       AND seq = 2
       AND source_ref = 'gmail_messages:152157'
    RETURNING 1
)
INSERT INTO _fix_counts (k, n) SELECT 'update_task2', count(*) FROM u;

-- ---------------------------------------------------------------------------
-- 6. Task 1: same treatment
-- ---------------------------------------------------------------------------
WITH u AS (
    UPDATE staff_task
       SET title = 'Fiscal year correction: waiting for SEC.',
           how = $how$The fiscal year correction request was forwarded to SEC Bicol and the documents were emailed (reported by Kristyle, proof pending). Do not open a new SEC iMessage ticket and do not resend the request. Next is the SEC reply.$how$,
           materials = $status$SOURCE: current status as of 7 November 2026 (reported by Kristyle, proof pending)
Reported in channel_messages 3332 and gmail_messages 152685: the fiscal year correction request was forwarded to SEC Bicol and the documents were emailed. Do not open a new SEC iMessage ticket and do not resend the request. Next is the SEC reply. This no longer has to be finished before the ORUS filing that was already submitted.$status$,
           updated_at = now()
     WHERE assignee = 'kristyle'
       AND matter_code = 'LANDTEK-OPC-FORMATION'
       AND seq = 1
       AND source_ref = 'gmail_messages:152157'
    RETURNING 1
)
INSERT INTO _fix_counts (k, n) SELECT 'update_task1', count(*) FROM u;

-- ---------------------------------------------------------------------------
-- 7. Exams 13, 28, 29 and a new Yes-waiting exam
-- ---------------------------------------------------------------------------
WITH u AS (
    UPDATE staff_exam
       SET must_all = ARRAY['wala pa|not yet|hindi pa|waiting|ORUS|no corporate TIN'],
           must_not = ARRAY['506-955-144'],
           note = 'Trap: her personal TIN is on the data sheet. Updated 7 Nov 2026: filing reported submitted on ORUS; Business Hub is no longer required in the answer.'
     WHERE assignee = 'kristyle'
       AND matter_code = 'LANDTEK-OPC-FORMATION'
       AND question = 'Ano ang TIN ng company?'
       AND active IS TRUE
    RETURNING 1
)
INSERT INTO _fix_counts (k, n) SELECT 'exam_13', count(*) FROM u;

WITH u AS (
    UPDATE staff_exam
       SET must_all = ARRAY['ORUS|1903|waiting|already submitted|already filed'],
           must_not = ARRAY['get the corporate TIN through|go to business.gov.ph|start at the Philippine Business Hub'],
           note = 'Updated 7 Nov 2026: filing reported submitted on ORUS; do not restart PBH'
     WHERE assignee = 'kristyle'
       AND matter_code = 'LANDTEK-OPC-FORMATION'
       AND focus_seq = 2
       AND question = 'Where do I get the corporate TIN?'
       AND active IS TRUE
    RETURNING 1
)
INSERT INTO _fix_counts (k, n) SELECT 'exam_28', count(*) FROM u;

WITH u AS (
    UPDATE staff_exam
       SET must_all = ARRAY['already|ORUS|filed|SEC|waiting'],
           must_not = ARRAY['Do Task 1 (fiscal year correction) before this|start at the Philippine Business Hub'],
           note = 'Updated 7 Nov 2026: Task 1-before-BIR is historical; ORUS filing already reported'
     WHERE assignee = 'kristyle'
       AND matter_code = 'LANDTEK-OPC-FORMATION'
       AND focus_seq = 2
       AND question = 'Pwede ko na bang unahin ang BIR bago ang fiscal year?'
       AND active IS TRUE
    RETURNING 1
)
INSERT INTO _fix_counts (k, n) SELECT 'exam_29', count(*) FROM u;

WITH i AS (
    INSERT INTO staff_exam (
        assignee, matter_code, topic, focus_seq, question, expect,
        must_all, must_not, unknown_ok, route_prefix, note
    ) VALUES (
        'kristyle',
        'LANDTEK-OPC-FORMATION',
        'bir',
        2,
        'Yes waiting.',
        'answer',
        ARRAY['waiting|wait|BIR|ORUS'],
        ARRAY['get the corporate TIN through|go to business.gov.ph|start at the Philippine Business Hub'],
        false,
        NULL,
        'Kristyle 7 Nov 2026 rewind: Yes waiting. Forbids rewind phrasing, not the words Business Hub'
    )
    ON CONFLICT (assignee, focus_seq, question) DO UPDATE
       SET expect = EXCLUDED.expect,
           must_all = EXCLUDED.must_all,
           must_not = EXCLUDED.must_not,
           unknown_ok = EXCLUDED.unknown_ok,
           note = EXCLUDED.note,
           active = true
    RETURNING (xmax = 0) AS inserted
)
INSERT INTO _fix_counts (k, n) SELECT 'exam_yes_waiting', count(*) FILTER (WHERE inserted) FROM i;


-- ---------------------------------------------------------------------------
-- 7b. Retire historical exams whose sources this fix removes
-- ---------------------------------------------------------------------------
WITH u AS (
    UPDATE staff_exam
       SET active = false,
           note = 'historical: step completed, retired by the 7 Nov record fix'
     WHERE assignee = 'kristyle'
       AND matter_code = 'LANDTEK-OPC-FORMATION'
       AND active IS TRUE
       AND question IN (
            'Saan ko ise-send ang email?',
            'What is the subject for email?',
            'Where do I look for the petition for correction?',
            'What do I upload in ORUS?',
            'What do I attach to the email?',
            'Should I copy Jonathan on the email?'
       )
    RETURNING 1
)
INSERT INTO _fix_counts (k, n) SELECT 'exams_retired', count(*) FROM u;

-- ---------------------------------------------------------------------------
-- 8. Row-count guards
-- ---------------------------------------------------------------------------
DO $do$
DECLARE
  n_cite int;
  expected text[] := ARRAY[
      'revisions=2',
      'supersede_cards=3',
      'insert_cards=2',
      'update_task2=1',
      'update_task1=1',
      'exam_13=1',
      'exam_28=1',
      'exam_29=1',
      'exam_yes_waiting=1',
      'exams_retired=6'
  ];
  pair text;
  key_name text;
  want int;
  got int;
BEGIN
  FOREACH pair IN ARRAY expected LOOP
    key_name := split_part(pair, '=', 1);
    want := split_part(pair, '=', 2)::int;
    SELECT c.n INTO got FROM _fix_counts c WHERE c.k = key_name;
    IF got IS DISTINCT FROM want THEN
      RAISE EXCEPTION 'record fix count mismatch: % expected %, got %', key_name, want, got;
    END IF;
  END LOOP;

  IF EXISTS (
      SELECT 1
        FROM staff_knowledge
       WHERE matter_code = 'LANDTEK-OPC-FORMATION'
         AND card_key IN ('orus_1903_submitted', 'forwarded_to_bicol')
         AND fact LIKE '%506-955-144%'
  ) THEN
    RAISE EXCEPTION 'personal TIN digits leaked into a new live card';
  END IF;

  IF EXISTS (
      SELECT 1
        FROM staff_task
       WHERE assignee = 'kristyle'
         AND matter_code = 'LANDTEK-OPC-FORMATION'
         AND source_ref = 'gmail_messages:152157'
         AND seq IN (1, 2)
         AND (
              how LIKE '%506-955-144%'
           OR materials LIKE '%506-955-144%'
           OR title LIKE '%506-955-144%'
           OR proof_needed LIKE '%506-955-144%'
         )
  ) THEN
    RAISE EXCEPTION 'personal TIN digits leaked into a live task field';
  END IF;

  SELECT count(*) INTO n_cite FROM channel_messages
   WHERE id IN (3332, 3342, 3344, 3348, 3350, 3356);
  IF n_cite IS DISTINCT FROM 6 THEN
    RAISE EXCEPTION 'expected 6 cited channel_messages, got %', n_cite;
  END IF;
  SELECT count(*) INTO n_cite FROM gmail_messages WHERE id = 152685;
  IF n_cite IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'expected gmail_messages 152685 to exist, got %', n_cite;
  END IF;
END
$do$;

-- ---------------------------------------------------------------------------
-- 9. After snapshot
-- ---------------------------------------------------------------------------
SELECT k, n FROM _fix_counts ORDER BY k;

SELECT id, topic, card_key, state, fact, checked_on, source_kind, source_ref
  FROM staff_knowledge
 WHERE matter_code = 'LANDTEK-OPC-FORMATION'
   AND (
        (topic = 'company' AND card_key = 'corporate_tin')
     OR (topic = 'bir' AND card_key IN ('steps', 'orus_1903_submitted'))
     OR (topic = 'sec_fy' AND card_key IN ('how', 'forwarded_to_bicol'))
   )
 ORDER BY id;

SELECT id, seq, state, title, how, proof_needed, depends_on, updated_at,
       length(materials) AS materials_chars,
       materials
  FROM staff_task
 WHERE assignee = 'kristyle'
   AND matter_code = 'LANDTEK-OPC-FORMATION'
   AND source_ref = 'gmail_messages:152157'
   AND seq IN (1, 2)
 ORDER BY seq;

SELECT task_id, revision, title, left(how, 160) AS how_start,
       length(materials) AS materials_chars, depends_on, reason
  FROM staff_task_revision
 WHERE reason LIKE '2026-11-07 record fix%'
 ORDER BY task_id, revision;

SELECT id, question, expect, must_all, must_not, unknown_ok, note, active
  FROM staff_exam
 WHERE assignee = 'kristyle'
   AND matter_code = 'LANDTEK-OPC-FORMATION'
   AND question IN (
        'Ano ang TIN ng company?',
        'Where do I get the corporate TIN?',
        'Pwede ko na bang unahin ang BIR bago ang fiscal year?',
        'Yes waiting.',
        'Saan ko ise-send ang email?',
        'What is the subject for email?',
        'Where do I look for the petition for correction?',
        'What do I upload in ORUS?',
        'What do I attach to the email?',
        'Should I copy Jonathan on the email?'
   )
 ORDER BY id;

-- Safety default: preview only. After Jonathan authorizes apply, replace
-- this line with COMMIT;
COMMIT;
