-- deploy_818: course-level consensus for parcel geometry (the anti-single-source layer).
--
-- Jonathan's requirement (2026-07-10): OCR-extracted courses must NOT be trusted from one
-- source. Each course is an ASSERTION by one document; the parcel's geometry is affirmed
-- only when independent sources (multiple title copies, plans) agree, and every doubt is
-- flagged for MANUAL review + correction. Mirrors the field_consensus idiom on the fact side.
--
--   parcel_courses            — one row per (source doc, segment, course): what THIS doc says
--   parcel_course_corrections — operator-provenance manual fixes applied at consensus build
--
-- geometry_consensus.py builds these, aligns courses across sources, classifies each as
-- corroborated / single_source / conflict, applies operator corrections (which outrank
-- everything), and only then composes a ring. Conflicts + single-source courses in an open
-- ring are the review queue — never silently accepted.

CREATE TABLE IF NOT EXISTS parcel_courses (
    id            BIGSERIAL PRIMARY KEY,
    title_no      TEXT NOT NULL,
    matter_code   TEXT,
    source_doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    seg           INTEGER NOT NULL DEFAULT 1,   -- technical-description segment within the doc
    idx           INTEGER NOT NULL,             -- course order within the segment's ring
    azimuth_deg   DOUBLE PRECISION NOT NULL,    -- clockwise from north
    distance_m    DOUBLE PRECISION NOT NULL,
    raw_call      TEXT,                         -- the verbatim matched call text (the excerpt)
    extracted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_doc_id, seg, idx)
);
CREATE INDEX IF NOT EXISTS idx_parcel_courses_title ON parcel_courses (title_no);

CREATE TABLE IF NOT EXISTS parcel_course_corrections (
    id            BIGSERIAL PRIMARY KEY,
    title_no      TEXT NOT NULL,
    position      INTEGER NOT NULL,             -- 1-based position in the consensus ring
    action        TEXT NOT NULL CHECK (action IN ('replace','insert','delete')),
    azimuth_deg   DOUBLE PRECISION,             -- NULL for delete
    distance_m    DOUBLE PRECISION,
    raw_call      TEXT,                         -- the bearing as the human read it off the scan
    reason        TEXT NOT NULL,                -- e.g. 'read from doc 684 scan, course 12'
    created_by    TEXT NOT NULL DEFAULT 'jonathan',
    provenance_level TEXT NOT NULL DEFAULT 'operator',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (title_no, position, action)
);
