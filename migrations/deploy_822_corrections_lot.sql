-- deploy_822: lot-scope operator corrections. With lot clustering (one consensus ring per
-- lot within a title), a correction's position is meaningful only within its lot's ring.
ALTER TABLE parcel_course_corrections ADD COLUMN IF NOT EXISTS lot TEXT NOT NULL DEFAULT 'A';
ALTER TABLE parcel_course_corrections DROP CONSTRAINT IF EXISTS parcel_course_corrections_title_no_position_action_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_pcc_title_lot_pos_action
    ON parcel_course_corrections (title_no, lot, position, action);

-- expected_call: the verbatim/canonical call the correction was written AGAINST. Lot
-- labels + positions can shift when new source docs reshuffle clusters; apply-time
-- verification against expected_call stops an operator-provenance value from silently
-- landing on the wrong course (review finding P0, 2026-07-11).
ALTER TABLE parcel_course_corrections ADD COLUMN IF NOT EXISTS expected_call TEXT;
