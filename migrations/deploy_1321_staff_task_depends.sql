-- deploy_1321: staff_task.depends_on — an errand that must wait for another, from the source.
-- Jonathan's 2 Nov email, step 2: fix the fiscal year "before the BIR registration in step 3" (Task 1 before Task 2).
ALTER TABLE staff_task ADD COLUMN IF NOT EXISTS depends_on bigint REFERENCES staff_task(id);
UPDATE staff_task t SET depends_on = d.id
  FROM staff_task d
 WHERE t.source_ref = 'gmail_messages:152157' AND t.seq = 2
   AND d.source_ref = 'gmail_messages:152157' AND d.seq = 1 AND t.depends_on IS NULL;
