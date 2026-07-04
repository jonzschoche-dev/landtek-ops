-- deploy_682: parcels — the geometry spine of the Mapping subsystem.
--
-- One row per plottable lot a client can SEE on a map. Geometry is stored as
-- GeoJSON in JSONB so the stack needs NO PostGIS (the n8n Postgres has none):
-- point-in-polygon runs client-side in JS, area/centroid in leo_tools/geo_math.py.
--
-- Two invariants are enforced structurally, not by convention:
--
--   1. CLIENT SEPARATION. Every parcel FKs to clients(client_code). The client
--      render route resolves an opaque token -> exactly one client_code and
--      selects WHERE client_code = <that>. MWK / Paracale-Inocalla / NIBDC can
--      never bleed across a map. (Mirrors client_access_tokens, deploy_659.)
--
--   2. PROVENANCE / accuracy is a first-class column, not a footnote.
--      accuracy_tier ∈ rough | survey | ortho. A 'rough' parcel is hand-placed
--      on satellite imagery and is ALWAYS rendered with an "APPROXIMATE — not a
--      survey" banner (Principle 9 — inference is marked). A parcel never
--      silently graduates tiers; the tier is set explicitly at save time and
--      only bumped to 'ortho' when a sub-meter orthomosaic confirms it.

CREATE TABLE IF NOT EXISTS parcels (
    id             BIGSERIAL PRIMARY KEY,
    parcel_code    TEXT NOT NULL UNIQUE,               -- stable slug, e.g. MWK-BALANE
    client_code    TEXT NOT NULL REFERENCES clients(client_code),
    matter_code    TEXT,                               -- soft ref (e.g. MWK-001 / Civil Case 26-360)
    title_no       TEXT,                               -- soft ref to titles (e.g. T-079-2021002126)
    label          TEXT,                               -- human name shown on the map ("Balane parcel, San Roque")
    description     TEXT,

    -- Geometry (WGS84). NULL geometry = row exists but not yet plotted.
    geom_geojson   JSONB,                              -- a GeoJSON Polygon (or Feature)
    centroid_lat   DOUBLE PRECISION,
    centroid_lng   DOUBLE PRECISION,
    area_sqm       DOUBLE PRECISION,                   -- computed from geom at save time

    -- Provenance / accuracy.
    accuracy_tier  TEXT CHECK (accuracy_tier IN ('rough','survey','ortho')),
    source_note    TEXT,                               -- "hand-placed on Esri imagery 2026-07-04" etc.
    stated_area_sqm DOUBLE PRECISION,                  -- area the TITLE claims, for the plot-vs-title check
    area_flag      TEXT,                               -- set by mapping_agent: NULL | 'ok' | 'deviation:NN%'

    -- Orthomosaic overlay (Phase 3). URL of an XYZ tile template once available.
    ortho_tiles_url TEXT,

    status         TEXT NOT NULL DEFAULT 'awaiting_plot',  -- awaiting_plot | plotted | published
    plotted_by     TEXT,
    plotted_at     TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_parcels_client ON parcels (client_code);
CREATE INDEX IF NOT EXISTS idx_parcels_matter ON parcels (matter_code);

-- Client-facing view: only the columns a map page needs, plus an explicit
-- `approximate` flag so the render layer cannot forget the banner. Anything
-- not 'ortho' is approximate. Rows without geometry are excluded (nothing to draw).
CREATE OR REPLACE VIEW parcels_client AS
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
FROM parcels
WHERE geom_geojson IS NOT NULL
  AND status IN ('plotted','published');

-- Seed the live MWK Balane parcel as an UNPLOTTED placeholder. Geometry is left
-- NULL on purpose — we do not fabricate coordinates; a human draws it via the
-- /ops/map draw tool. stated_area_sqm = 2587 (the parcel-recovery figure in
-- Civil Case 26-360). Guarded so it no-ops if the MWK-001 client row is absent.
INSERT INTO parcels (parcel_code, client_code, matter_code, title_no, label,
                     stated_area_sqm, accuracy_tier, source_note, status)
SELECT 'MWK-BALANE', 'MWK-001', 'MWK-001', 'T-079-2021002126',
       'Balane parcel (Lot 2-X-6-I-4-C-1)', 2587, NULL,
       'Seed row — awaiting rough plot on satellite', 'awaiting_plot'
WHERE EXISTS (SELECT 1 FROM clients WHERE client_code = 'MWK-001')
ON CONFLICT (parcel_code) DO NOTHING;
