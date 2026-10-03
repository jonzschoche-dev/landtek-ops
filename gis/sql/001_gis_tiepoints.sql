-- LandTek Mapping Division
-- 001_gis_tiepoints.sql — survey tie point reference layer
--
-- Loads the ph-tiepoints-camarines-norte dataset into the LandTek corpus.
-- Idempotent: safe to re-run. Upserts on gp_id.
--
-- PROVENANCE DISCIPLINE
--   Every row lands as provenance_level = 'inferred_strong'.
--   The source is a government service, but it publishes coordinates only —
--   no monument description, no recovery status, no certification. It is not
--   a verified fact until a DENR-LMB certified monument description backs it.
--   gis_tiepoints_safe therefore returns ONLY rows promoted to 'verified'.
--   It is empty on a fresh load. That is correct, not a bug.
--
-- PostGIS is NOT assumed. Coordinates are plain numerics. An optional
-- geometry column is at the bottom, commented out.

BEGIN;

CREATE TABLE IF NOT EXISTS gis_tiepoints (
    gp_id               integer PRIMARY KEY,
    pointref            text        NOT NULL,
    lgu                 text,
    psgc_code           text,
    source_locality     text,
    municipality        text,
    province            text        NOT NULL DEFAULT 'Camarines Norte',
    province_psgc       text,
    mon_type            text        NOT NULL,
    mon_type_label      text,
    mon_no              text,
    survey_project      text,
    barrio              text,
    variant             text,

    -- As published by DENR-LMB. PRS92 geographic, EPSG:4683. Never edited.
    prs92_lat           numeric(12,8) NOT NULL,
    prs92_lon           numeric(12,8) NOT NULL,
    -- Derived for imagery overlay. WGS84, EPSG:4326.
    wgs84_lat           numeric(12,8) NOT NULL,
    wgs84_lon           numeric(12,8) NOT NULL,
    -- As published. PRS92 / Philippines zone IV, EPSG:3124. Passed through.
    ptm_zone            smallint    NOT NULL DEFAULT 4,
    ptm_east            numeric(14,4) NOT NULL,
    ptm_north           numeric(14,4) NOT NULL,
    ptm_check_resid_m   numeric(10,4),

    source              text        NOT NULL,
    retrieved           date        NOT NULL,
    dataset_version     text        NOT NULL,
    legal_status        text        NOT NULL,

    provenance_level    text        NOT NULL DEFAULT 'inferred_strong'
        CHECK (provenance_level IN ('verified', 'inferred_strong', 'inferred_weak')),
    -- Fill these three together when promoting a row to 'verified'.
    verified_source_doc text,
    verified_excerpt    text,
    verified_at         timestamptz,

    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT gis_tiepoints_verified_needs_doc CHECK (
        provenance_level <> 'verified'
        OR (verified_source_doc IS NOT NULL AND verified_excerpt IS NOT NULL)
    )
);

COMMENT ON TABLE  gis_tiepoints IS
    'DENR-LMB survey tie points. Reference grade. Read gis_tiepoints_safe for legal output.';
COMMENT ON COLUMN gis_tiepoints.prs92_lat IS
    'As published. PRS92 geographic EPSG:4683 — NOT WGS84. ~217 m from the WGS84 position.';
COMMENT ON COLUMN gis_tiepoints.ptm_east IS
    'As published, EPSG:3124. Passed through from source, never recomputed.';
COMMENT ON COLUMN gis_tiepoints.ptm_check_resid_m IS
    'QA: metres between the recomputed and published grid position. Expect < 0.01.';

CREATE INDEX IF NOT EXISTS gis_tiepoints_lgu_idx        ON gis_tiepoints (lgu);
CREATE INDEX IF NOT EXISTS gis_tiepoints_psgc_idx       ON gis_tiepoints (psgc_code);
CREATE INDEX IF NOT EXISTS gis_tiepoints_type_idx       ON gis_tiepoints (mon_type);
CREATE INDEX IF NOT EXISTS gis_tiepoints_project_idx    ON gis_tiepoints (survey_project);
CREATE INDEX IF NOT EXISTS gis_tiepoints_prov_idx       ON gis_tiepoints (provenance_level);
CREATE INDEX IF NOT EXISTS gis_tiepoints_pointref_trgm  ON gis_tiepoints
    USING gin (pointref gin_trgm_ops);  -- needs pg_trgm; drop this line if absent

-- Controlled vocabulary -------------------------------------------------
CREATE TABLE IF NOT EXISTS gis_monument_types (
    mon_type   text PRIMARY KEY,
    label      text NOT NULL,
    notes      text
);

INSERT INTO gis_monument_types (mon_type, label, notes) VALUES
 ('BLLM','Bureau of Lands Location Monument','Primary location monument for a Pls/Cad project. Technical descriptions usually tie here.'),
 ('BLBM','Bureau of Lands Barrio Monument','Barrio-level location monument. Distinct class from BLLM - do not conflate.'),
 ('BBM','Barrio Boundary Monument','Barrio boundary monument within a subdivision/cadastral project.'),
 ('MBM','Municipal Boundary Monument','Municipal boundary monument.'),
 ('PBM','Provincial Boundary Monument','Provincial boundary monument.'),
 ('BDRY','Boundary monument (inter-municipal / provincial)','Named boundary monument; no project number.'),
 ('PRS92','PRS92 geodetic control point','CMN-series PRS92 control. Use for GNSS ties.'),
 ('TRIG','Triangulation station','Mostly US C.&G.S. era.'),
 ('FZM','Forest Zone Monument','Forest zone monument.'),
 ('PPM','PPM - US Army 29th Engineer survey monument','1940s US Army survey marker.'),
 ('P','Numbered cadastral point (Cad survey)','Labo Cad-176 only in release 1.0.0.')
ON CONFLICT (mon_type) DO UPDATE
    SET label = EXCLUDED.label, notes = EXCLUDED.notes;

ALTER TABLE gis_tiepoints
    DROP CONSTRAINT IF EXISTS gis_tiepoints_mon_type_fkey;
ALTER TABLE gis_tiepoints
    ADD CONSTRAINT gis_tiepoints_mon_type_fkey
    FOREIGN KEY (mon_type) REFERENCES gis_monument_types (mon_type);

-- Views -----------------------------------------------------------------

-- Legal output reads ONLY this. Empty until rows are promoted.
DROP VIEW IF EXISTS gis_tiepoints_safe;
CREATE VIEW gis_tiepoints_safe AS
SELECT gp_id, pointref, lgu, psgc_code, mon_type, mon_type_label, mon_no,
       survey_project, barrio, variant,
       prs92_lat, prs92_lon, ptm_zone, ptm_east, ptm_north,
       verified_source_doc, verified_excerpt, verified_at
FROM   gis_tiepoints
WHERE  provenance_level = 'verified';

COMMENT ON VIEW gis_tiepoints_safe IS
    'Certified tie points only. Anything absent here is PENDING VERIFICATION and must be labelled as such in any brief, pleading or evidence pack.';

-- Working/orientation view. Carries the caveat in-band so it cannot be
-- copied into an output without the warning travelling with it.
DROP VIEW IF EXISTS gis_tiepoints_reference;
CREATE VIEW gis_tiepoints_reference AS
SELECT t.*,
       'PENDING VERIFICATION - reference coordinate from DENR-LMB Geoportal, no certified monument description on file'::text
         AS verification_notice
FROM   gis_tiepoints t
WHERE  t.provenance_level <> 'verified';

-- Coverage rollup.
DROP VIEW IF EXISTS gis_tiepoint_coverage;
CREATE VIEW gis_tiepoint_coverage AS
SELECT COALESCE(NULLIF(lgu, ''), '(unresolved)') AS lgu,
       psgc_code,
       count(*)                                          AS points,
       count(*) FILTER (WHERE provenance_level = 'verified') AS verified,
       count(*) FILTER (WHERE mon_type = 'BLLM')         AS bllm,
       count(*) FILTER (WHERE mon_type = 'PRS92')        AS prs92_control,
       count(DISTINCT survey_project) FILTER (WHERE survey_project <> '') AS projects
FROM   gis_tiepoints
GROUP  BY 1, 2
ORDER  BY points DESC;

-- Nearest PRS92 control to any given tie point. Planimetric, PTM metres —
-- good enough for picking an occupation station, not for a survey computation.
DROP VIEW IF EXISTS gis_tiepoint_nearest_control;
CREATE VIEW gis_tiepoint_nearest_control AS
SELECT t.gp_id,
       t.pointref,
       t.lgu,
       c.pointref                                           AS nearest_control,
       round(sqrt(power(t.ptm_east - c.ptm_east, 2)
                + power(t.ptm_north - c.ptm_north, 2)), 1)  AS distance_m
FROM   gis_tiepoints t
CROSS  JOIN LATERAL (
    SELECT k.pointref, k.ptm_east, k.ptm_north
    FROM   gis_tiepoints k
    WHERE  k.mon_type = 'PRS92'
    ORDER  BY power(t.ptm_east - k.ptm_east, 2) + power(t.ptm_north - k.ptm_north, 2)
    LIMIT  1
) c
WHERE  t.mon_type <> 'PRS92';

-- Duplicate-position detector. Relocated monuments legitimately share a
-- position; anything else sharing one is worth a look.
DROP VIEW IF EXISTS gis_tiepoint_colocated;
CREATE VIEW gis_tiepoint_colocated AS
SELECT ptm_east, ptm_north, count(*) AS n,
       array_agg(pointref ORDER BY gp_id) AS pointrefs,
       array_agg(gp_id    ORDER BY gp_id) AS gp_ids
FROM   gis_tiepoints
GROUP  BY ptm_east, ptm_north
HAVING count(*) > 1;

COMMIT;

-- ---------------------------------------------------------------------
-- Load: see tools/load_to_postgres.py, or by hand from the export CSV:
--
--   CREATE TEMP TABLE _tp (LIKE gis_tiepoints INCLUDING DEFAULTS);
--   \copy _tp (gp_id,pointref,lgu,psgc_code,source_locality,municipality,
--              province,province_psgc,mon_type,mon_type_label,mon_no,
--              survey_project,barrio,variant,prs92_lat,prs92_lon,
--              wgs84_lat,wgs84_lon,ptm_zone,ptm_east,ptm_north,
--              ptm_check_resid_m,source,retrieved,dataset_version,legal_status)
--     FROM 'datasets/ph-tiepoints-camarines-norte/exports/cn_tiepoints.csv' CSV HEADER;
--   INSERT INTO gis_tiepoints SELECT * FROM _tp
--     ON CONFLICT (gp_id) DO UPDATE SET
--       pointref = EXCLUDED.pointref, lgu = EXCLUDED.lgu,
--       psgc_code = EXCLUDED.psgc_code, mon_type = EXCLUDED.mon_type,
--       prs92_lat = EXCLUDED.prs92_lat, prs92_lon = EXCLUDED.prs92_lon,
--       wgs84_lat = EXCLUDED.wgs84_lat, wgs84_lon = EXCLUDED.wgs84_lon,
--       ptm_east = EXCLUDED.ptm_east, ptm_north = EXCLUDED.ptm_north,
--       dataset_version = EXCLUDED.dataset_version, updated_at = now();
--   -- NOTE: the upsert deliberately does NOT touch provenance_level or the
--   -- verified_* columns. A re-harvest never demotes work already verified.
--
-- ---------------------------------------------------------------------
-- Optional, only if PostGIS is installed:
--
--   CREATE EXTENSION IF NOT EXISTS postgis;
--   ALTER TABLE gis_tiepoints ADD COLUMN IF NOT EXISTS geom_wgs84 geometry(Point, 4326);
--   ALTER TABLE gis_tiepoints ADD COLUMN IF NOT EXISTS geom_ptm4  geometry(Point, 3124);
--   UPDATE gis_tiepoints SET
--     geom_wgs84 = ST_SetSRID(ST_MakePoint(wgs84_lon, wgs84_lat), 4326),
--     geom_ptm4  = ST_SetSRID(ST_MakePoint(ptm_east,  ptm_north), 3124);
--   CREATE INDEX IF NOT EXISTS gis_tiepoints_geom_wgs84_idx ON gis_tiepoints USING gist (geom_wgs84);
