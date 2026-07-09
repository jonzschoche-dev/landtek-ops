-- deploy_814 — V6 geometry client isolation (ONTOLOGY.md A9) · SHADOW (log) — RECORD OF REALITY.
-- V6 was applied LIVE by the mapping/geometry session (~2026-07-06/07) and proven (deliberate cross-client
-- insert logged + rolled back; 0 live violations; MWK-BALANE seed clean). This file records it for
-- reproducibility/reversibility per the mapping desk's handoff directive (received 2026-07-09) — it was
-- DUMPED FROM THE LIVE DB (pg_get_viewdef/functiondef/triggerdef, 2026-07-09), not authored from the
-- directive's draft SQL. Idempotent; safe to re-run. Ontology-doc side: A9 row re-grounded in deploy_806
-- (the --enforcement check caught the row still saying "not yet applied"); spec §8 updated with this deploy.
--
-- Mode ladder: log (CURRENT — logs ONTOLOGY_GEOMETRY_CLIENT_CROSS to holes_findings via ontology_reject,
-- blocks nothing) → block (RAISES). Flip per ONTOLOGY_ALIGNMENT.md §9 checklist — NOTE the pipeline is
-- near-dormant (map_parcels=1, parcels=0), so a 0-findings window is trivially clean; flip should ride the
-- first real geometry-write campaign (strip_plot_info / survey re-OCR), not the calendar.

CREATE OR REPLACE VIEW v_ontology_geometry_cross AS
SELECT 'map_parcels'::text AS layer,
       mp.parcel_code      AS ref,
       mp.matter_code,
       mp.client_code      AS declared_client,
       _client_of(mp.matter_code) AS resolved_client
FROM map_parcels mp
WHERE mp.matter_code IS NOT NULL AND mp.client_code IS NOT NULL
  AND _client_of(mp.matter_code) IS NOT NULL
  AND mp.client_code IS DISTINCT FROM _client_of(mp.matter_code)
UNION ALL
SELECT 'parcels'::text, p.id::text, p.matter_code, p.client_code, _client_of(p.matter_code)
FROM parcels p
WHERE p.matter_code IS NOT NULL AND p.client_code IS NOT NULL
  AND _client_of(p.matter_code) IS NOT NULL
  AND p.client_code IS DISTINCT FROM _client_of(p.matter_code);

INSERT INTO ontology_validator_config (check_code, mode, note)
SELECT 'V6', 'log', 'geometry client-isolation (A9) via v_ontology_geometry_cross — map_parcels + parcels'
WHERE NOT EXISTS (SELECT 1 FROM ontology_validator_config WHERE check_code = 'V6');

CREATE OR REPLACE FUNCTION public.ontvv_geometry_isolation()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE m text; resolved text; BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code = 'V6';
  IF m IS NULL OR m = 'off' THEN RETURN NEW; END IF;
  IF NEW.matter_code IS NOT NULL AND NEW.client_code IS NOT NULL THEN
    resolved := _client_of(NEW.matter_code);
    IF resolved IS NOT NULL AND NEW.client_code <> resolved THEN
      PERFORM ontology_reject('ONTOLOGY_GEOMETRY_CLIENT_CROSS',
        TG_TABLE_NAME || ' matter_code=' || NEW.matter_code || ' client_code=' || NEW.client_code
        || ' but matter resolves to ' || resolved);
      IF m = 'block' THEN
        RAISE EXCEPTION 'ontology_validator V6: %.client_code (%) must match the client of matter_code % (%) — A9',
          TG_TABLE_NAME, NEW.client_code, NEW.matter_code, resolved;
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END $function$;

DROP TRIGGER IF EXISTS ontvv_v6_map_parcels ON map_parcels;
CREATE TRIGGER ontvv_v6_map_parcels BEFORE INSERT OR UPDATE ON public.map_parcels
  FOR EACH ROW EXECUTE FUNCTION ontvv_geometry_isolation();
DROP TRIGGER IF EXISTS ontvv_v6_parcels ON parcels;
CREATE TRIGGER ontvv_v6_parcels BEFORE INSERT OR UPDATE ON public.parcels
  FOR EACH ROW EXECUTE FUNCTION ontvv_geometry_isolation();

-- Rollback:
--   DROP TRIGGER IF EXISTS ontvv_v6_map_parcels ON map_parcels;
--   DROP TRIGGER IF EXISTS ontvv_v6_parcels ON parcels;
--   DROP FUNCTION IF EXISTS ontvv_geometry_isolation();
--   DROP VIEW IF EXISTS v_ontology_geometry_cross;
--   DELETE FROM ontology_validator_config WHERE check_code = 'V6';
