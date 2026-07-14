-- deploy_912 — V12: Property Development spine isolation (ONTOLOGY A81) · SHADOW (log).
--
-- Design: docs/PROPERTY_DEVELOPMENT_SPINE.md §3.2. Pattern: V6 geometry (deploy_814) + V11 null-owner
-- (deploy_871) — ontology_reject + ontology_validator_config mode ladder log→block.
--
-- Why V12 exists:
--   * Polymorphic asset_preconditions.owner_code has NO FK (owner_kind = asset|project) — must check
--     owner EXISTS, not only client match.
--   * Link tables can bridge clients if writers only pass convention — refuse cross-client.
--   * revenue_engine will become a second writer across all clients (step 3) — isolation must shadow first.
--
-- Checks (BEFORE INSERT OR UPDATE):
--   1) owner existence (asset_preconditions): asset → property_assets; project → development_projects
--   2) row client_code matches owner.client_code (when owner has a declared client)
--   3) asset_map_parcels: asset.client = map_parcels.client = row.client
--   4) asset_survey_parcels: asset.client = parcels.client = row.client
--   5) asset_titles: asset.client = row.client
--   6) development_projects: asset.client = project.client (when asset.client IS NOT NULL)
--   7) development_permits: project.client = permit.client
--
-- Mode: log (CURRENT) — logs via ontology_reject, does NOT block. Flip to block per
-- ONTOLOGY_ALIGNMENT.md §9 after soak + negative tests.
-- Idempotent; safe to re-run.

\set ON_ERROR_STOP on
BEGIN;

INSERT INTO ontology_validator_config (check_code, mode, note)
SELECT 'V12', 'log',
       'property spine isolation (A81) — owner existence + cross-client on asset_preconditions/links/projects/permits'
WHERE NOT EXISTS (SELECT 1 FROM ontology_validator_config WHERE check_code = 'V12');

-- ── asset_preconditions: owner existence + client match ──────────────────────
CREATE OR REPLACE FUNCTION public.ontvv_v12_precondition_owner()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
  m text;
  owner_client text;
  owner_found boolean := false;
BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code = 'V12';
  IF m IS NULL OR m = 'off' THEN RETURN NEW; END IF;

  IF NEW.owner_kind = 'asset' THEN
    SELECT true, pa.client_code INTO owner_found, owner_client
      FROM property_assets pa WHERE pa.asset_code = NEW.owner_code;
  ELSIF NEW.owner_kind = 'project' THEN
    SELECT true, dp.client_code INTO owner_found, owner_client
      FROM development_projects dp WHERE dp.project_code = NEW.owner_code;
  ELSE
    PERFORM ontology_reject('ONTOLOGY_SPINE_OWNER_KIND',
      'asset_preconditions: invalid owner_kind=' || COALESCE(NEW.owner_kind, 'NULL'));
    IF m = 'block' THEN
      RAISE EXCEPTION 'ontology_validator V12: invalid owner_kind % (A81)', NEW.owner_kind;
    END IF;
    RETURN NEW;
  END IF;

  IF NOT owner_found THEN
    PERFORM ontology_reject('ONTOLOGY_SPINE_OWNER_MISSING',
      'asset_preconditions: owner_kind=' || NEW.owner_kind || ' owner_code=' || NEW.owner_code
      || ' does not exist — polymorphic owner has no FK; orphan refused (A81)');
    IF m = 'block' THEN
      RAISE EXCEPTION 'ontology_validator V12: precondition owner %/% does not exist (A81)',
        NEW.owner_kind, NEW.owner_code;
    END IF;
    RETURN NEW;
  END IF;

  -- Owner has a declared client and row client differs → cross-client
  IF owner_client IS NOT NULL AND NEW.client_code IS DISTINCT FROM owner_client THEN
    PERFORM ontology_reject('ONTOLOGY_SPINE_CLIENT_CROSS',
      'asset_preconditions: row client_code=' || COALESCE(NEW.client_code, 'NULL')
      || ' but owner ' || NEW.owner_kind || '/' || NEW.owner_code
      || ' resolves to ' || owner_client || ' — A81');
    IF m = 'block' THEN
      RAISE EXCEPTION 'ontology_validator V12: precondition client_code (%) must match owner client (%) — A81',
        NEW.client_code, owner_client;
    END IF;
  END IF;

  RETURN NEW;
END
$function$;

DROP TRIGGER IF EXISTS ontvv_v12_asset_preconditions ON asset_preconditions;
CREATE TRIGGER ontvv_v12_asset_preconditions
  BEFORE INSERT OR UPDATE ON public.asset_preconditions
  FOR EACH ROW EXECUTE FUNCTION public.ontvv_v12_precondition_owner();

-- ── asset_map_parcels: asset + map parcel same client ────────────────────────
CREATE OR REPLACE FUNCTION public.ontvv_v12_asset_map_parcel()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
  m text;
  a_client text;
  p_client text;
BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code = 'V12';
  IF m IS NULL OR m = 'off' THEN RETURN NEW; END IF;

  SELECT client_code INTO a_client FROM property_assets WHERE asset_code = NEW.asset_code;
  IF a_client IS NULL AND NOT EXISTS (SELECT 1 FROM property_assets WHERE asset_code = NEW.asset_code) THEN
    PERFORM ontology_reject('ONTOLOGY_SPINE_OWNER_MISSING',
      'asset_map_parcels: asset_code=' || NEW.asset_code || ' missing (A81)');
    IF m = 'block' THEN
      RAISE EXCEPTION 'ontology_validator V12: asset % missing on asset_map_parcels (A81)', NEW.asset_code;
    END IF;
  ELSIF a_client IS NOT NULL AND NEW.client_code IS DISTINCT FROM a_client THEN
    PERFORM ontology_reject('ONTOLOGY_SPINE_CLIENT_CROSS',
      'asset_map_parcels: row client=' || COALESCE(NEW.client_code,'NULL')
      || ' asset client=' || a_client || ' — A81');
    IF m = 'block' THEN
      RAISE EXCEPTION 'ontology_validator V12: asset_map_parcels client must match asset (A81)';
    END IF;
  END IF;

  SELECT client_code INTO p_client FROM map_parcels WHERE parcel_code = NEW.parcel_code;
  IF p_client IS NULL AND NOT EXISTS (SELECT 1 FROM map_parcels WHERE parcel_code = NEW.parcel_code) THEN
    PERFORM ontology_reject('ONTOLOGY_SPINE_OWNER_MISSING',
      'asset_map_parcels: parcel_code=' || NEW.parcel_code || ' missing (A81)');
    IF m = 'block' THEN
      RAISE EXCEPTION 'ontology_validator V12: map parcel % missing (A81)', NEW.parcel_code;
    END IF;
  ELSIF p_client IS NOT NULL AND NEW.client_code IS DISTINCT FROM p_client THEN
    PERFORM ontology_reject('ONTOLOGY_SPINE_CLIENT_CROSS',
      'asset_map_parcels: row client=' || COALESCE(NEW.client_code,'NULL')
      || ' parcel client=' || p_client || ' — A81');
    IF m = 'block' THEN
      RAISE EXCEPTION 'ontology_validator V12: asset_map_parcels client must match map_parcels (A81)';
    END IF;
  END IF;

  RETURN NEW;
END
$function$;

DROP TRIGGER IF EXISTS ontvv_v12_asset_map_parcels ON asset_map_parcels;
CREATE TRIGGER ontvv_v12_asset_map_parcels
  BEFORE INSERT OR UPDATE ON public.asset_map_parcels
  FOR EACH ROW EXECUTE FUNCTION public.ontvv_v12_asset_map_parcel();

-- ── asset_survey_parcels: asset + survey parcel same client ──────────────────
CREATE OR REPLACE FUNCTION public.ontvv_v12_asset_survey_parcel()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
  m text;
  a_client text;
  p_client text;
BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code = 'V12';
  IF m IS NULL OR m = 'off' THEN RETURN NEW; END IF;

  IF NOT EXISTS (SELECT 1 FROM property_assets WHERE asset_code = NEW.asset_code) THEN
    PERFORM ontology_reject('ONTOLOGY_SPINE_OWNER_MISSING',
      'asset_survey_parcels: asset_code=' || NEW.asset_code || ' missing (A81)');
    IF m = 'block' THEN
      RAISE EXCEPTION 'ontology_validator V12: asset % missing on asset_survey_parcels (A81)', NEW.asset_code;
    END IF;
  ELSE
    SELECT client_code INTO a_client FROM property_assets WHERE asset_code = NEW.asset_code;
    IF a_client IS NOT NULL AND NEW.client_code IS DISTINCT FROM a_client THEN
      PERFORM ontology_reject('ONTOLOGY_SPINE_CLIENT_CROSS',
        'asset_survey_parcels: row client=' || COALESCE(NEW.client_code,'NULL')
        || ' asset client=' || a_client || ' — A81');
      IF m = 'block' THEN
        RAISE EXCEPTION 'ontology_validator V12: asset_survey_parcels client must match asset (A81)';
      END IF;
    END IF;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM parcels WHERE id = NEW.survey_parcel_id) THEN
    PERFORM ontology_reject('ONTOLOGY_SPINE_OWNER_MISSING',
      'asset_survey_parcels: survey_parcel_id=' || NEW.survey_parcel_id || ' missing (A81)');
    IF m = 'block' THEN
      RAISE EXCEPTION 'ontology_validator V12: parcels.id % missing (A81)', NEW.survey_parcel_id;
    END IF;
  ELSE
    SELECT client_code INTO p_client FROM parcels WHERE id = NEW.survey_parcel_id;
    IF p_client IS NOT NULL AND NEW.client_code IS DISTINCT FROM p_client THEN
      PERFORM ontology_reject('ONTOLOGY_SPINE_CLIENT_CROSS',
        'asset_survey_parcels: row client=' || COALESCE(NEW.client_code,'NULL')
        || ' survey client=' || p_client || ' — A81');
      IF m = 'block' THEN
        RAISE EXCEPTION 'ontology_validator V12: asset_survey_parcels client must match parcels (A81)';
      END IF;
    END IF;
  END IF;

  RETURN NEW;
END
$function$;

DROP TRIGGER IF EXISTS ontvv_v12_asset_survey_parcels ON asset_survey_parcels;
CREATE TRIGGER ontvv_v12_asset_survey_parcels
  BEFORE INSERT OR UPDATE ON public.asset_survey_parcels
  FOR EACH ROW EXECUTE FUNCTION public.ontvv_v12_asset_survey_parcel();

-- ── asset_titles: asset client match ─────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.ontvv_v12_asset_titles()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
  m text;
  a_client text;
BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code = 'V12';
  IF m IS NULL OR m = 'off' THEN RETURN NEW; END IF;

  IF NOT EXISTS (SELECT 1 FROM property_assets WHERE asset_code = NEW.asset_code) THEN
    PERFORM ontology_reject('ONTOLOGY_SPINE_OWNER_MISSING',
      'asset_titles: asset_code=' || NEW.asset_code || ' missing (A81)');
    IF m = 'block' THEN
      RAISE EXCEPTION 'ontology_validator V12: asset % missing on asset_titles (A81)', NEW.asset_code;
    END IF;
  ELSE
    SELECT client_code INTO a_client FROM property_assets WHERE asset_code = NEW.asset_code;
    IF a_client IS NOT NULL AND NEW.client_code IS DISTINCT FROM a_client THEN
      PERFORM ontology_reject('ONTOLOGY_SPINE_CLIENT_CROSS',
        'asset_titles: row client=' || COALESCE(NEW.client_code,'NULL')
        || ' asset client=' || a_client || ' — A81');
      IF m = 'block' THEN
        RAISE EXCEPTION 'ontology_validator V12: asset_titles client must match asset (A81)';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END
$function$;

DROP TRIGGER IF EXISTS ontvv_v12_asset_titles ON asset_titles;
CREATE TRIGGER ontvv_v12_asset_titles
  BEFORE INSERT OR UPDATE ON public.asset_titles
  FOR EACH ROW EXECUTE FUNCTION public.ontvv_v12_asset_titles();

-- ── development_projects: asset client match ─────────────────────────────────
CREATE OR REPLACE FUNCTION public.ontvv_v12_development_projects()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
  m text;
  a_client text;
BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code = 'V12';
  IF m IS NULL OR m = 'off' THEN RETURN NEW; END IF;

  IF NOT EXISTS (SELECT 1 FROM property_assets WHERE asset_code = NEW.asset_code) THEN
    PERFORM ontology_reject('ONTOLOGY_SPINE_OWNER_MISSING',
      'development_projects: asset_code=' || NEW.asset_code || ' missing (A81)');
    IF m = 'block' THEN
      RAISE EXCEPTION 'ontology_validator V12: asset % missing on development_projects (A81)', NEW.asset_code;
    END IF;
  ELSE
    SELECT client_code INTO a_client FROM property_assets WHERE asset_code = NEW.asset_code;
    IF a_client IS NOT NULL AND NEW.client_code IS DISTINCT FROM a_client THEN
      PERFORM ontology_reject('ONTOLOGY_SPINE_CLIENT_CROSS',
        'development_projects: project client=' || COALESCE(NEW.client_code,'NULL')
        || ' asset client=' || a_client || ' — A81');
      IF m = 'block' THEN
        RAISE EXCEPTION 'ontology_validator V12: project client must match asset (A81)';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END
$function$;

DROP TRIGGER IF EXISTS ontvv_v12_development_projects ON development_projects;
CREATE TRIGGER ontvv_v12_development_projects
  BEFORE INSERT OR UPDATE ON public.development_projects
  FOR EACH ROW EXECUTE FUNCTION public.ontvv_v12_development_projects();

-- ── development_permits: project client match ────────────────────────────────
CREATE OR REPLACE FUNCTION public.ontvv_v12_development_permits()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
  m text;
  p_client text;
BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code = 'V12';
  IF m IS NULL OR m = 'off' THEN RETURN NEW; END IF;

  IF NOT EXISTS (SELECT 1 FROM development_projects WHERE project_code = NEW.project_code) THEN
    PERFORM ontology_reject('ONTOLOGY_SPINE_OWNER_MISSING',
      'development_permits: project_code=' || NEW.project_code || ' missing (A81)');
    IF m = 'block' THEN
      RAISE EXCEPTION 'ontology_validator V12: project % missing on development_permits (A81)', NEW.project_code;
    END IF;
  ELSE
    SELECT client_code INTO p_client FROM development_projects WHERE project_code = NEW.project_code;
    IF p_client IS NOT NULL AND NEW.client_code IS DISTINCT FROM p_client THEN
      PERFORM ontology_reject('ONTOLOGY_SPINE_CLIENT_CROSS',
        'development_permits: permit client=' || COALESCE(NEW.client_code,'NULL')
        || ' project client=' || p_client || ' — A81');
      IF m = 'block' THEN
        RAISE EXCEPTION 'ontology_validator V12: permit client must match project (A81)';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END
$function$;

DROP TRIGGER IF EXISTS ontvv_v12_development_permits ON development_permits;
CREATE TRIGGER ontvv_v12_development_permits
  BEFORE INSERT OR UPDATE ON public.development_permits
  FOR EACH ROW EXECUTE FUNCTION public.ontvv_v12_development_permits();

-- Audit view: live cross-client / orphan-ish conditions (read-only inventory)
CREATE OR REPLACE VIEW v_ontology_spine_cross AS
SELECT 'asset_preconditions'::text AS layer,
       ap.id::text AS ref,
       ap.owner_kind,
       ap.owner_code,
       ap.client_code AS declared_client,
       CASE ap.owner_kind
         WHEN 'asset' THEN (SELECT pa.client_code FROM property_assets pa WHERE pa.asset_code = ap.owner_code)
         WHEN 'project' THEN (SELECT dp.client_code FROM development_projects dp WHERE dp.project_code = ap.owner_code)
       END AS owner_client,
       CASE
         WHEN ap.owner_kind = 'asset' AND NOT EXISTS (SELECT 1 FROM property_assets pa WHERE pa.asset_code = ap.owner_code)
           THEN 'owner_missing'
         WHEN ap.owner_kind = 'project' AND NOT EXISTS (SELECT 1 FROM development_projects dp WHERE dp.project_code = ap.owner_code)
           THEN 'owner_missing'
         WHEN ap.owner_kind = 'asset'
              AND (SELECT pa.client_code FROM property_assets pa WHERE pa.asset_code = ap.owner_code) IS NOT NULL
              AND ap.client_code IS DISTINCT FROM (SELECT pa.client_code FROM property_assets pa WHERE pa.asset_code = ap.owner_code)
           THEN 'client_cross'
         WHEN ap.owner_kind = 'project'
              AND (SELECT dp.client_code FROM development_projects dp WHERE dp.project_code = ap.owner_code) IS NOT NULL
              AND ap.client_code IS DISTINCT FROM (SELECT dp.client_code FROM development_projects dp WHERE dp.project_code = ap.owner_code)
           THEN 'client_cross'
         ELSE NULL
       END AS issue
  FROM asset_preconditions ap
 WHERE TRUE;

COMMIT;

-- Smoke (manual):
--   SELECT check_code, mode FROM ontology_validator_config WHERE check_code='V12';
--   -- orphan (log only): insert precondition with fake owner → holes_findings row; rolled back
-- Rollback:
--   DROP TRIGGER IF EXISTS ontvv_v12_asset_preconditions ON asset_preconditions;
--   DROP TRIGGER IF EXISTS ontvv_v12_asset_map_parcels ON asset_map_parcels;
--   DROP TRIGGER IF EXISTS ontvv_v12_asset_survey_parcels ON asset_survey_parcels;
--   DROP TRIGGER IF EXISTS ontvv_v12_asset_titles ON asset_titles;
--   DROP TRIGGER IF EXISTS ontvv_v12_development_projects ON development_projects;
--   DROP TRIGGER IF EXISTS ontvv_v12_development_permits ON development_permits;
--   DROP FUNCTION IF EXISTS ontvv_v12_precondition_owner(), ontvv_v12_asset_map_parcel(),
--     ontvv_v12_asset_survey_parcel(), ontvv_v12_asset_titles(),
--     ontvv_v12_development_projects(), ontvv_v12_development_permits();
--   DROP VIEW IF EXISTS v_ontology_spine_cross;
--   DELETE FROM ontology_validator_config WHERE check_code='V12';
