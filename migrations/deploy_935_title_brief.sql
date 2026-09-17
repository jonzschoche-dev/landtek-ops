-- deploy_935: title_brief — one digested row per title for property UI (later maps + classification)
--
-- SoR stays titles / title_chain / instruments_on_title / property_assets / map_parcels.
-- title_brief is DERIVED and rebuildable (same pattern as matter_brief).
--
-- Apply:
--   docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/deploy_935_title_brief.sql

BEGIN;

CREATE TABLE IF NOT EXISTS title_brief (
    title_key              text PRIMARY KEY,          -- normalized: T-32911 | OCT-111 | 079-2021002126
    title_kind             text NOT NULL,             -- tct | oct | e_title | unknown
    display_no             text NOT NULL,             -- human label
    case_file              text,                      -- client_code / case_file when known
    client_code            text,
    registrant_name        text,
    area_sqm               numeric,
    location               text,
    status                 text,                      -- titles.status / lifecycle
    lifecycle_status       text,
    parent_titles          text[] NOT NULL DEFAULT '{}',
    child_titles           text[] NOT NULL DEFAULT '{}',
    related_matters        text[] NOT NULL DEFAULT '{}',
    tax_decs               text[] NOT NULL DEFAULT '{}',
    survey_refs            text[] NOT NULL DEFAULT '{}',
    asset_codes            text[] NOT NULL DEFAULT '{}',
    n_instruments          int NOT NULL DEFAULT 0,
    n_source_docs          int NOT NULL DEFAULT 0,
    n_facts_mentioning     int NOT NULL DEFAULT 0,
    n_facts_verified       int NOT NULL DEFAULT 0,
    source_doc_ids         int[] NOT NULL DEFAULT '{}',
    top_fact_ids           int[] NOT NULL DEFAULT '{}',
    map_parcel_ids         int[] NOT NULL DEFAULT '{}',
    has_map_geometry       boolean NOT NULL DEFAULT false,
    readiness_score        numeric,
    title_status_asset     text,                      -- clean/clouded from property_assets
    possession             text,
    headline               text NOT NULL DEFAULT '',
    card                   jsonb NOT NULL DEFAULT '{}'::jsonb,  -- UI-ready pack
    source_fingerprint     text,
    computed_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS title_brief_client_idx ON title_brief (client_code);
CREATE INDEX IF NOT EXISTS title_brief_kind_idx ON title_brief (title_kind);
CREATE INDEX IF NOT EXISTS title_brief_case_idx ON title_brief (case_file);

COMMENT ON TABLE title_brief IS
  'DERIVED one-row-per-title card for property classification UI (maps, tax, chain, docs). '
  'Rebuild from titles + fact_fields + instruments + chain + assets + map_parcels. Never SoR.';

-- Catalog of every title identifier we know (union), for materializer discovery
CREATE OR REPLACE VIEW v_title_catalog AS
SELECT DISTINCT ON (title_key) title_key, title_kind, display_no, case_file, source
FROM (
    SELECT
        upper(regexp_replace(t.tct_number, '\s+', '', 'g')) AS title_key,
        CASE
          WHEN t.tct_number ~* '^OCT' THEN 'oct'
          WHEN t.tct_number ~ '^\d{3}-\d{10,}' THEN 'e_title'
          ELSE 'tct'
        END AS title_kind,
        t.tct_number AS display_no,
        t.case_file,
        'titles'::text AS source
    FROM titles t
    WHERE coalesce(t.tct_number, '') <> ''

    UNION ALL

    SELECT
        upper(regexp_replace(ff.value_norm, '\s+', '', 'g')),
        ff.field_kind,
        ff.value_norm,
        NULL,
        'fact_fields'
    FROM fact_fields ff
    WHERE ff.field_kind IN ('tct', 'oct', 'e_title')
      AND coalesce(ff.value_norm, '') <> ''

    UNION ALL

    SELECT
        upper(regexp_replace(pa.title_ref, '\s+', '', 'g')),
        CASE WHEN pa.title_ref ~ '^\d{3}-\d{10,}' THEN 'e_title' ELSE 'tct' END,
        pa.title_ref,
        pa.client_code,
        'property_assets'
    FROM property_assets pa
    WHERE coalesce(pa.title_ref, '') <> ''

    UNION ALL

    SELECT
        upper(regexp_replace(dt.tct_number, '\s+', '', 'g')),
        'tct',
        dt.tct_number,
        NULL,
        'document_titles'
    FROM document_titles dt
    WHERE coalesce(dt.tct_number, '') <> ''
) u
WHERE title_key IS NOT NULL AND title_key <> ''
ORDER BY title_key, source;  -- prefer stable order; DISTINCT ON keeps first

COMMENT ON VIEW v_title_catalog IS
  'Discovery set of title identifiers from titles + fact_fields + assets + document_titles.';

COMMIT;

SELECT 'title_brief ready: ' || to_regclass('title_brief')::text;
SELECT 'v_title_catalog rows: ' || count(*)::text FROM v_title_catalog;
