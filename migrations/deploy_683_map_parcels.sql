-- deploy_683: map_parcels — the geometry spine of the client-facing Mapping subsystem.
--
-- SUPERSEDES deploy_682 (which used the name `parcels` and collided with the
-- pre-existing survey-extraction table). The two are DIFFERENT layers, kept apart
-- on purpose:
--
--   * `parcels` (scripts/parcels.py) = the RELATIVE survey shape computed from a
--     title's metes-and-bounds — local-meter WKT, un-georeferenced, provenance
--     inferred_strong. It answers "what shape/area does the paper describe?"
--   * `map_parcels` (this table) = the ABSOLUTE parcel PLACED on the world — WGS84
--     lat/lng GeoJSON, hand-plotted on satellite (rough) or georeferenced from a
--     survey (survey) or a drone orthomosaic (ortho). It answers "where on Google
--     Maps is it, so a client can see it and stand inside it?"
--
--   The bridge (still ahead): a `parcels` survey shape + a tie point → georeference
--   → a `map_parcels` row at accuracy_tier='survey'.
--
-- One row per plottable lot a client can SEE. Geometry is GeoJSON in JSONB so the
-- stack needs NO PostGIS: point-in-polygon runs client-side in JS, area/centroid in
-- leo_tools/geo_math.py.
--
-- Two invariants are enforced structurally, not by convention:
--   1. CLIENT SEPARATION — every row FKs to clients(client_code); the client route
--      resolves an opaque token -> exactly one client_code and selects WHERE
--      client_code = that. (Mirrors client_access_tokens, deploy_659.)
--   2. PROVENANCE/accuracy is a first-class column. accuracy_tier ∈ rough|survey|ortho;
--      a non-ortho parcel ALWAYS renders an "APPROXIMATE — not a survey" banner
--      (Principle 9). A parcel never silently graduates tiers.

CREATE TABLE IF NOT EXISTS map_parcels (
    id             BIGSERIAL PRIMARY KEY,
    parcel_code    TEXT NOT NULL UNIQUE,               -- stable slug, e.g. MWK-BALANE
    client_code    TEXT NOT NULL REFERENCES clients(client_code),
    matter_code    TEXT,                               -- soft ref (e.g. MWK-001 / Civil Case 26-360)
    title_no       TEXT,                               -- soft ref to titles (e.g. T-079-2021002126)
    survey_parcel_id INTEGER,                          -- optional link to parcels.id (the survey shape)
    label          TEXT,                               -- human name shown on the map
    description     TEXT,

    -- Geometry (WGS84). NULL geometry = row exists but not yet plotted.
    geom_geojson   JSONB,                              -- a GeoJSON Polygon (or Feature)
    centroid_lat   DOUBLE PRECISION,
    centroid_lng   DOUBLE PRECISION,
    area_sqm       DOUBLE PRECISION,                   -- computed from geom at save time

    -- Provenance / accuracy.
    accuracy_tier  TEXT CHECK (accuracy_tier IN ('rough','survey','ortho')),
    source_note    TEXT,
    stated_area_sqm DOUBLE PRECISION,                  -- area the TITLE claims, for the plot-vs-title check
    area_flag      TEXT,                               -- set by mapping_agent: NULL | 'ok' | 'deviation:NN%'

    -- Orthomosaic overlay (Phase 3). XYZ tile template once available.
    ortho_tiles_url TEXT,

    status         TEXT NOT NULL DEFAULT 'awaiting_plot',  -- awaiting_plot | plotted | published
    plotted_by     TEXT,
    plotted_at     TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_map_parcels_client ON map_parcels (client_code);
CREATE INDEX IF NOT EXISTS idx_map_parcels_matter ON map_parcels (matter_code);

-- Client-facing view: only render-safe columns + an explicit `approximate` flag
-- so the render layer cannot forget the banner. Un-plotted rows are excluded.
CREATE OR REPLACE VIEW map_parcels_client AS
SELECT
    parcel_code,
    client_code,
    label,
    description,
    geom_geojson,
    centroid_lat,
    centroid_lng,
    area_sqm,
    stated_area_sqm,
    accuracy_tier,
    ortho_tiles_url,
    (accuracy_tier IS DISTINCT FROM 'ortho') AS approximate
FROM map_parcels
WHERE geom_geojson IS NOT NULL
  AND status IN ('plotted','published');

-- Seed the live MWK Balane parcel as an UNPLOTTED placeholder. Geometry is left
-- NULL on purpose — we do not fabricate coordinates; a human draws it via the
-- /ops/map draw tool. Guarded so it no-ops if the MWK-001 client row is absent.
INSERT INTO map_parcels (parcel_code, client_code, matter_code, title_no, label,
                         stated_area_sqm, accuracy_tier, source_note, status)
SELECT 'MWK-BALANE', 'MWK-001', 'MWK-001', 'T-079-2021002126',
       'Balane parcel (Lot 2-X-6-I-4-C-1)', 2587, NULL,
       'Seed row — awaiting rough plot on satellite', 'awaiting_plot'
WHERE EXISTS (SELECT 1 FROM clients WHERE client_code = 'MWK-001')
ON CONFLICT (parcel_code) DO NOTHING;
