-- deploy_947: plan_overlays — georeferenced raster overlays of survey/cadastral plan images.
-- The "table maps / old cadastral plans" layer of the premium spec: an operator aligns a plan
-- SCAN onto the satellite via corner control points, so the whole subdivision shape is visible
-- in place even when the plan's course tables are too damaged/handwritten to transcribe. This is
-- a VISUAL REFERENCE layer only — it never becomes survey geometry or an accuracy tier (a warped
-- 1975 scan is not a survey). Client-separation via client_code; not exposed until the switch (A11).
CREATE TABLE IF NOT EXISTS plan_overlays (
    id           BIGSERIAL PRIMARY KEY,
    doc_id       INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    client_code  TEXT NOT NULL REFERENCES clients(client_code),
    matter_code  TEXT,
    label        TEXT,
    corners      JSONB,          -- [[lat,lng] x3]: plan image TL, TR, BL placed on the world
    img_w        INTEGER,
    img_h        INTEGER,
    opacity      DOUBLE PRECISION NOT NULL DEFAULT 0.6,
    created_by   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (doc_id)
);
CREATE INDEX IF NOT EXISTS idx_plan_overlays_client ON plan_overlays (client_code);
