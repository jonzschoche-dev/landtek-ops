-- deploy_829: parcel_course_proposals — the CLIENT-side entry to the geometry correction
-- loop. A client tapping "flag this course" on their map must NEVER write geometry or a
-- correction directly (A6: corrections are operator-provenance rows; clients don't hold
-- that authority). Proposals land here, ops reviews at /ops/map/proposals, and an ACCEPT
-- writes the real parcel_course_corrections row (created_by=operator, reason cites the
-- proposal id). Client isolation: client_code is resolved SERVER-side from the access
-- token (never from the request body), and every read/insert is scoped to it (A5/A9).
-- Deliberately NO location fields — device GPS stays ephemeral+client-side (A10).

CREATE TABLE IF NOT EXISTS parcel_course_proposals (
    id            BIGSERIAL PRIMARY KEY,
    title_no      TEXT NOT NULL,
    lot           TEXT NOT NULL DEFAULT 'A',
    position      INTEGER,                    -- ring position it targets; NULL = general remark
    note          TEXT NOT NULL,              -- what the client believes is wrong / right
    proposed_bearing  TEXT,                   -- optional structured suggestion, verbatim
    proposed_distance_m DOUBLE PRECISION,
    client_code   TEXT NOT NULL REFERENCES clients(client_code),
    channel       TEXT NOT NULL DEFAULT 'client-map',
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','accepted','rejected')),
    reviewed_by   TEXT,
    reviewed_at   TIMESTAMPTZ,
    review_note   TEXT,
    correction_id BIGINT,                     -- parcel_course_corrections.id when accepted
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pcp_status ON parcel_course_proposals (status);
CREATE INDEX IF NOT EXISTS idx_pcp_client ON parcel_course_proposals (client_code);

-- target_call: the call text the client SAW when flagging (copied into the correction's
-- expected_call on accept, so the correction verifies its target at apply time).
ALTER TABLE parcel_course_proposals ADD COLUMN IF NOT EXISTS target_call TEXT;
