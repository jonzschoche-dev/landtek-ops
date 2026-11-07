-- UNDO for 2026-11-07_staff_record_fix_2.sql (correction id rf-2026-11-07-b). Ends in ROLLBACK.
-- Change to COMMIT only on Jonathan's go.
--
-- Restores the exact before-values logged in staff_record_fix_log, not assumed values.
-- REFUSES if any row now differs from the after-value the correction logged (someone edited it since: write a new
-- correction instead). The log rows are kept and marked undone_at, so the audit history survives the undo.
-- staff_record_fix_log itself is left in place.

BEGIN;

SELECT id FROM staff_knowledge WHERE id IN (95, 96) FOR UPDATE;
SELECT id FROM staff_task      WHERE id IN (1, 2)   FOR UPDATE;
SELECT id FROM staff_exam      WHERE id IN (28, 193) FOR UPDATE;

DO $guard$
DECLARE n_live int; n_drift int;
BEGIN
  SELECT count(*) INTO n_live FROM staff_record_fix_log
   WHERE correction_id = 'rf-2026-11-07-b' AND undone_at IS NULL;
  IF n_live <> 6 THEN
    RAISE EXCEPTION 'rf-2026-11-07-b undo: expected 6 live log rows, found % (not applied, or already undone)', n_live;
  END IF;

  SELECT count(*) INTO n_drift FROM staff_record_fix_log l
   WHERE l.correction_id = 'rf-2026-11-07-b' AND l.undone_at IS NULL
     AND l.after IS DISTINCT FROM CASE l.table_name
       WHEN 'staff_knowledge' THEN (SELECT jsonb_build_object('fact', fact, 'source_ref', source_ref) FROM staff_knowledge WHERE id = l.row_id)
       WHEN 'staff_task'      THEN (SELECT jsonb_build_object('how', how, 'materials', materials, 'proof_needed', proof_needed) FROM staff_task WHERE id = l.row_id)
       WHEN 'staff_exam'      THEN (SELECT jsonb_build_object('must_not', to_jsonb(must_not), 'note', note) FROM staff_exam WHERE id = l.row_id)
     END;
  IF n_drift <> 0 THEN
    RAISE EXCEPTION 'rf-2026-11-07-b undo refused: % row(s) changed since the correction', n_drift;
  END IF;
END
$guard$;

UPDATE staff_knowledge k
   SET fact = l.before->>'fact', source_ref = l.before->>'source_ref', updated_at = now()
  FROM staff_record_fix_log l
 WHERE l.correction_id = 'rf-2026-11-07-b' AND l.table_name = 'staff_knowledge' AND l.row_id = k.id;

UPDATE staff_task t
   SET how = l.before->>'how', materials = l.before->>'materials', proof_needed = l.before->>'proof_needed', updated_at = now()
  FROM staff_record_fix_log l
 WHERE l.correction_id = 'rf-2026-11-07-b' AND l.table_name = 'staff_task' AND l.row_id = t.id;

UPDATE staff_exam e
   SET must_not = ARRAY(SELECT jsonb_array_elements_text(l.before->'must_not')), note = l.before->>'note'
  FROM staff_record_fix_log l
 WHERE l.correction_id = 'rf-2026-11-07-b' AND l.table_name = 'staff_exam' AND l.row_id = e.id;

UPDATE staff_record_fix_log SET undone_at = now()
 WHERE correction_id = 'rf-2026-11-07-b' AND undone_at IS NULL;

ROLLBACK;
