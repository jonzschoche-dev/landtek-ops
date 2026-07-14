-- deploy_911: Property Development + Revenue precondition spine (reconciled design).
--
-- Design of record: docs/PROPERTY_DEVELOPMENT_SPINE.md (operator-signed 2026-07-14).
-- Additive + idempotent. Promotes the existing `property_assets` hub; does NOT rename or
-- merge parcels / map_parcels / property_assets. Graduates two Future Domains at once
-- (ONTOLOGY §8.8 Revenue/Valuation/Portfolio + §9 Construction/Project Delivery) as ONE spine.
--
-- Preflight (2026-07-14, live n8n DB) confirmed:
--   * clients.client_code domain = {MWK-001, Paracale-001, NIBDC-001, Archive, Owner, PENDING_TRIAGE}
--     -> client_code IS the bucket string; the draft's MWK/PAR guess was wrong. Do NOT hardcode.
--   * _client_of('MWK-CV26360')->MWK-001, _client_of('Paracale-001')->Paracale-001 : ALL 83 PA rows
--     resolve via COALESCE(_client_of(controlling_matter), _client_of(case_file)). Zero orphans.
--   * property_assets already has `origin` (values: title=77, seed=6); no spine tables exist yet.
--
-- Invariants (provisional, minted with the ontology desk on land): A81 (client_code on every
-- governed row; cross-client links refused), A82 (precondition ok requires evidence — DB CHECK
-- below, fail-closed), A83 (geometry only via link tables), A84 (ready requires all preconds ok —
-- engine + truth_test). A5/A9 isolation, A67 timeline, A74 recheck, A78 provenance discipline.
--
-- NOT in this migration (design §10 non-goals): V12 isolation triggers (shadow-later), auto stage
-- transitions, tenant/CAPEX/finance product, client-facing publish, LLM agent loop.

\set ON_ERROR_STOP on
BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Promote the hub: property_assets (no primary_project_code — is_primary lives on the project)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE property_assets
  ADD COLUMN IF NOT EXISTS client_code text,               -- A81 wall; backfilled via _client_of only
  ADD COLUMN IF NOT EXISTS stage text
    DEFAULT 'inventory'
    CHECK (stage IN (
      'inventory','assessing','entitling','financing','permitting',
      'ready','under_construction','operating','exited','blocked')),
  ADD COLUMN IF NOT EXISTS provenance_level text
    DEFAULT 'inferred_strong'
    CHECK (provenance_level IN ('verified','operator','inferred_strong','inferred_weak')),
  ADD COLUMN IF NOT EXISTS source_doc_id int,
  ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();

-- `origin` already exists (text DEFAULT 'seed', no CHECK). Convention (enforced in engine + truth_test):
--   origin='title'            -> title STUB (enroll_titles population; 1:1 with a corpus title; fast-cash only)
--   origin IN ('seed','operator') -> CURATED asset (may own asset_titles / asset_map_parcels / projects)
-- No CHECK added: adding one risks failing on an unforeseen legacy value; the discriminator is a
-- read-side + write-side rule, not a storage constraint (design §1.1).

-- FK to the tenancy root (guarded — ADD CONSTRAINT has no IF NOT EXISTS). Nullable, like parcels
-- (deploy_733): a row whose client can't be resolved must still insert (degrade-don't-crash);
-- NULL simply means "no declared client" and isolation stays dark for that row, never blocks a write.
DO $$
BEGIN
  IF NOT EXISTS (
      SELECT 1 FROM information_schema.table_constraints
      WHERE constraint_name = 'property_assets_client_code_fkey' AND table_name = 'property_assets') THEN
    ALTER TABLE property_assets
      ADD CONSTRAINT property_assets_client_code_fkey
      FOREIGN KEY (client_code) REFERENCES clients(client_code);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_property_assets_client ON property_assets (client_code);
CREATE INDEX IF NOT EXISTS idx_property_assets_origin ON property_assets (origin);
CREATE INDEX IF NOT EXISTS idx_property_assets_stage  ON property_assets (stage);

-- Backfill client_code — NO case_file->matter collapse, NO hardcoded map. Preflight: 0 orphans.
UPDATE property_assets
SET    client_code = COALESCE(_client_of(controlling_matter), _client_of(case_file))
WHERE  client_code IS NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. development_projects — the deal track (many per curated asset; one is_primary)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS development_projects (
  project_code         text PRIMARY KEY,
  client_code          text NOT NULL REFERENCES clients(client_code),
  label                text NOT NULL,
  asset_code           text NOT NULL REFERENCES property_assets(asset_code),  -- curated-only (engine+test)
  mode                 text NOT NULL DEFAULT 'develop'
    CHECK (mode IN ('develop','sale','lease','mineral')),
  stage                text NOT NULL DEFAULT 'assessing'
    CHECK (stage IN (
      'assessing','entitling','financing','permitting',
      'ready','under_construction','operating','exited','blocked')),
  is_primary           boolean NOT NULL DEFAULT false,
  objective            text,
  target_use           text,
  gating_precondition  text,                          -- denorm cache: first non-ok across the mode chain
  readiness_ratio      numeric(5,4),                  -- denorm cache: ok / total
  -- A67 forward timeline (pulse reads next_milestone_date; stage_target_dates is a detail store only)
  next_milestone_date  date,
  next_milestone_label text,
  stage_target_dates   jsonb,
  dateless_class       text CHECK (dateless_class IS NULL OR dateless_class IN ('needs_date','watch','n/a')),
  status               text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active','paused','done','cancelled')),
  provenance_level     text NOT NULL DEFAULT 'operator'
    CHECK (provenance_level IN ('verified','operator','inferred_strong','inferred_weak')),
  source_doc_id        int,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now()
);

-- At most one primary ACTIVE project per asset (mirrors uq_asset_titles_one_primary)
CREATE UNIQUE INDEX IF NOT EXISTS uq_dev_projects_one_primary
  ON development_projects (asset_code) WHERE is_primary AND status = 'active';
CREATE INDEX IF NOT EXISTS idx_dev_projects_client ON development_projects (client_code);
CREATE INDEX IF NOT EXISTS idx_dev_projects_asset  ON development_projects (asset_code);
CREATE INDEX IF NOT EXISTS idx_dev_projects_stage  ON development_projects (stage);
CREATE INDEX IF NOT EXISTS idx_dev_projects_milestone
  ON development_projects (next_milestone_date) WHERE status = 'active' AND next_milestone_date IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Link tables — multi-title / multi-lot aggregates (curated assets only)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS asset_titles (
  id               bigserial PRIMARY KEY,
  asset_code       text NOT NULL REFERENCES property_assets(asset_code) ON DELETE CASCADE,
  client_code      text NOT NULL REFERENCES clients(client_code),
  title_no         text NOT NULL,                     -- soft match titles.tct_number (titles are messy)
  role             text NOT NULL DEFAULT 'component'
    CHECK (role IN ('primary','component','adjacent','claim','encumbering')),
  title_status     text,
  is_primary       boolean NOT NULL DEFAULT false,
  provenance_level text NOT NULL DEFAULT 'inferred_strong'
    CHECK (provenance_level IN ('verified','operator','inferred_strong','inferred_weak')),
  source_doc_id    int,
  note             text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (asset_code, title_no)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_asset_titles_one_primary
  ON asset_titles (asset_code) WHERE is_primary;
CREATE INDEX IF NOT EXISTS idx_asset_titles_title  ON asset_titles (title_no);
CREATE INDEX IF NOT EXISTS idx_asset_titles_client ON asset_titles (client_code);

CREATE TABLE IF NOT EXISTS asset_map_parcels (
  id               bigserial PRIMARY KEY,
  asset_code       text NOT NULL REFERENCES property_assets(asset_code) ON DELETE CASCADE,
  client_code      text NOT NULL REFERENCES clients(client_code),
  parcel_code      text NOT NULL REFERENCES map_parcels(parcel_code),
  role             text NOT NULL DEFAULT 'site'
    CHECK (role IN ('site','access','buffer','claim','exclude')),
  provenance_level text NOT NULL DEFAULT 'operator'
    CHECK (provenance_level IN ('verified','operator','inferred_strong','inferred_weak')),
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (asset_code, parcel_code)
);
CREATE INDEX IF NOT EXISTS idx_asset_map_parcels_client ON asset_map_parcels (client_code);
CREATE INDEX IF NOT EXISTS idx_asset_map_parcels_parcel ON asset_map_parcels (parcel_code);

CREATE TABLE IF NOT EXISTS asset_survey_parcels (
  id               bigserial PRIMARY KEY,
  asset_code       text NOT NULL REFERENCES property_assets(asset_code) ON DELETE CASCADE,
  client_code      text NOT NULL REFERENCES clients(client_code),
  survey_parcel_id int NOT NULL REFERENCES parcels(id),   -- HARD FK (parcels.id is a real PK)
  role             text NOT NULL DEFAULT 'boundary',
  provenance_level text NOT NULL DEFAULT 'inferred_strong'
    CHECK (provenance_level IN ('verified','operator','inferred_strong','inferred_weak')),
  source_doc_id    int,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (asset_code, survey_parcel_id)
);
CREATE INDEX IF NOT EXISTS idx_asset_survey_parcels_client ON asset_survey_parcels (client_code);

-- Soft denorm on the map layer (Open Decision #3: soft first, consistent with map_parcels.matter_code/title_no)
ALTER TABLE map_parcels ADD COLUMN IF NOT EXISTS asset_code text;   -- NO hard FK in Sprint 1
CREATE INDEX IF NOT EXISTS idx_map_parcels_asset ON map_parcels (asset_code);

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. asset_preconditions — the generalized readiness ledger (all 4 modes; polymorphic owner)
--    Asset-owned rows (tenure/geometry/possession/...) are an ENGINE-DERIVED CACHE of asset facts:
--    sole-writer engine, recomputed atomically, NEVER hand-set. Source of truth = title_status/geometry.
--    Operator 'ok' is legal ONLY for project-owned sourcing codes (capital_partner/feasibility/...).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS asset_preconditions (
  id                 bigserial PRIMARY KEY,
  client_code        text NOT NULL REFERENCES clients(client_code),
  owner_kind         text NOT NULL CHECK (owner_kind IN ('asset','project')),
  owner_code         text NOT NULL,                   -- asset_code | project_code (polymorphic: no FK; V12 checks existence)
  mode               text NOT NULL CHECK (mode IN ('develop','sale','lease','mineral')),
  code               text NOT NULL,                   -- secure_tenure | survey_geometry | permits | ...
  label              text NOT NULL,
  sort_order         int NOT NULL DEFAULT 0,
  status             text NOT NULL DEFAULT 'unknown'
    CHECK (status IN ('ok','blocked','todo','unknown')),
  reason             text,
  next_move          text,
  evidence_kind      text CHECK (evidence_kind IS NULL OR evidence_kind IN (
                       'title_status','matter','permit','doc','operator','geometry','finance','external')),
  evidence_ref       text,
  source_doc_id      int,
  provenance_level   text NOT NULL DEFAULT 'inferred_weak'
    CHECK (provenance_level IN ('verified','operator','inferred_strong','inferred_weak')),
  recheck_condition  text,                            -- A74
  last_assessed_at   timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (owner_kind, owner_code, mode, code),
  -- A82 fail-closed: ok requires evidence (a cited doc, a non-empty evidence_ref, or operator attestation)
  CONSTRAINT asset_preconditions_ok_requires_evidence CHECK (
    status <> 'ok'
    OR source_doc_id IS NOT NULL
    OR (evidence_ref IS NOT NULL AND btrim(evidence_ref) <> '')
    OR provenance_level = 'operator'
  )
);
CREATE INDEX IF NOT EXISTS idx_asset_pre_owner  ON asset_preconditions (owner_kind, owner_code);
CREATE INDEX IF NOT EXISTS idx_asset_pre_status ON asset_preconditions (status);
CREATE INDEX IF NOT EXISTS idx_asset_pre_client ON asset_preconditions (client_code);

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. development_permits — project-scoped instruments (expires_on is an instrument FACT;
--    any renew-by nudge is derived into the calendar/pulse layer, never a 2nd deadline truth here)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS development_permits (
  permit_code       text PRIMARY KEY,
  project_code      text NOT NULL REFERENCES development_projects(project_code) ON DELETE CASCADE,
  client_code       text NOT NULL REFERENCES clients(client_code),
  asset_code        text REFERENCES property_assets(asset_code),
  authority         text NOT NULL,                    -- LGU | DENR | MGB | HLURB | BARANGAY | OTHER
  permit_type       text NOT NULL,                    -- locational | ECC | building | mining | business | other
  status            text NOT NULL DEFAULT 'not_started'
    CHECK (status IN ('not_started','preparing','filed','under_review',
                      'granted','denied','expired','waived','not_required')),
  filed_on          date,
  decided_on        date,
  expires_on        date,
  reference_no      text,
  source_doc_id     int,
  provenance_level  text NOT NULL DEFAULT 'operator'
    CHECK (provenance_level IN ('verified','operator','inferred_strong','inferred_weak')),
  note              text,
  recheck_condition text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_dev_permits_project ON development_permits (project_code);
CREATE INDEX IF NOT EXISTS idx_dev_permits_status  ON development_permits (status);
CREATE INDEX IF NOT EXISTS idx_dev_permits_expiry  ON development_permits (expires_on)
  WHERE expires_on IS NOT NULL AND status = 'granted';

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. Views — the boards (single epistemology: read the ledger)
-- ─────────────────────────────────────────────────────────────────────────────
-- 6a. Develop/deal board: project-owned preconds + parent asset-owned preconds for the project's mode.
CREATE OR REPLACE VIEW v_development_board AS
SELECT
  p.project_code, p.client_code, p.label,
  p.asset_code, a.label AS asset_label, a.origin AS asset_origin,
  a.title_ref, a.title_status,
  p.mode, p.stage, p.is_primary,
  p.gating_precondition, p.readiness_ratio,
  p.next_milestone_date, p.next_milestone_label, p.dateless_class, p.status,
  (SELECT count(*) FROM asset_preconditions x
     WHERE x.owner_kind='project' AND x.owner_code=p.project_code AND x.mode=p.mode AND x.status='ok') AS project_pre_ok,
  (SELECT count(*) FROM asset_preconditions x
     WHERE x.owner_kind='project' AND x.owner_code=p.project_code AND x.mode=p.mode)                    AS project_pre_total,
  (SELECT count(*) FROM asset_preconditions x
     WHERE x.owner_kind='asset' AND x.owner_code=p.asset_code AND x.mode=p.mode AND x.status='ok')      AS asset_pre_ok,
  (SELECT count(*) FROM asset_preconditions x
     WHERE x.owner_kind='asset' AND x.owner_code=p.asset_code AND x.mode=p.mode)                        AS asset_pre_total,
  (SELECT bool_or(mp.geom_geojson IS NOT NULL AND mp.accuracy_tier IN ('survey','ortho'))
     FROM asset_map_parcels amp JOIN map_parcels mp ON mp.parcel_code = amp.parcel_code
    WHERE amp.asset_code = p.asset_code)                                                                AS has_survey_grade_geom,
  p.updated_at
FROM development_projects p
JOIN property_assets a ON a.asset_code = p.asset_code
WHERE p.status = 'active' AND a.origin IN ('seed','operator');

-- 6b. Inventory / fast-cash board: ALL assets incl. stubs; decorate stub with its curated parent.
CREATE OR REPLACE VIEW v_asset_inventory AS
SELECT
  a.asset_code, a.client_code, a.origin, a.label, a.stage,
  a.title_ref, a.title_status, a.possession, a.modes, a.tier,
  a.controlling_matter, a.est_value, a.est_income_monthly, a.provenance_level, a.updated_at,
  (SELECT at.asset_code FROM asset_titles at
     WHERE at.title_no = a.title_ref AND at.asset_code <> a.asset_code
     ORDER BY at.is_primary DESC LIMIT 1)                                    AS component_of_curated,
  (SELECT ap.status FROM asset_preconditions ap
     WHERE ap.owner_kind='asset' AND ap.owner_code=a.asset_code
       AND ap.code IN ('marketable_title','secure_tenure')
     ORDER BY ap.updated_at DESC LIMIT 1)                                    AS tenure_status
FROM property_assets a;

COMMIT;

\echo ''
\echo '=== deploy_911 applied. Verifying ==='
SELECT 'client_code backfilled' AS check, count(*) FILTER (WHERE client_code IS NOT NULL) AS filled,
       count(*) FILTER (WHERE client_code IS NULL) AS orphans FROM property_assets;
SELECT 'spine tables' AS check, string_agg(tablename, ', ' ORDER BY tablename) AS created
FROM pg_tables WHERE tablename IN
 ('development_projects','asset_titles','asset_map_parcels','asset_survey_parcels','asset_preconditions','development_permits');
SELECT 'views' AS check, string_agg(viewname, ', ' ORDER BY viewname) AS created
FROM pg_views WHERE viewname IN ('v_development_board','v_asset_inventory');
