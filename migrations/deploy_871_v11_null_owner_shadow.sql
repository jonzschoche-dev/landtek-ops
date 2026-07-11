-- deploy_871 — V11: null-owner edge guard (A77(1)) · SHADOW (log). Idempotent.
-- Closes the V4 bypass class AT THE DB: V4 compares fact-client vs doc-client but passes when the doc's
-- owner resolves NULL — proven live 2026-07-11 (untagged docs 1172/1177 seeded MWK-OP-PETITION facts).
-- The writer-lane gate (scripts/ingest_gate.py, deploy_870) holds harvest_facts + verify_worker upstream
-- (>99% of automated writes); V11 closes the remainder (decipher_matter / reconciler / load_issue_spine /
-- source_read_facts / n8n / ad-hoc SQL) once flipped to block. Ships LOG per the ALIGNMENT §9 checklist;
-- backlog note: 152 open unresolved_doc_owner holds + ~840 pre-existing facts cite owner-unresolvable docs
-- (historical rows — the trigger judges NEW writes only).
-- Fires only when the cited doc EXISTS but its owner is unresolvable; a nonexistent doc is V3's problem.

CREATE OR REPLACE FUNCTION public.ontvv_v11_null_owner() RETURNS trigger
LANGUAGE plpgsql AS $function$
DECLARE m text; dc text; doc_found boolean := false;
BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code='V11';
  IF m IS NULL OR m='off' THEN RETURN NEW; END IF;
  IF NEW.source_id ~ '^[0-9]+$' THEN
    SELECT true, _client_of(COALESCE(d.matter_code, d.case_file))
      INTO doc_found, dc FROM documents d WHERE d.id = NEW.source_id::int;
    IF doc_found AND dc IS NULL THEN
      PERFORM ontology_reject('ONTOLOGY_NULL_OWNER_EDGE',
        'matter_facts: fact for '||COALESCE(NEW.matter_code,'?')||' cites doc '||NEW.source_id||
        ' whose client owner is UNRESOLVED — A77(1): an unresolved artifact never forms an edge');
      IF m='block' THEN
        RAISE EXCEPTION 'ontology_validator V11: cited document % has no resolvable client owner — resolve/tag the document first (A77)',
          NEW.source_id;
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END $function$;

INSERT INTO ontology_validator_config (check_code, mode, note)
SELECT 'V11', 'log', 'null-owner edge guard (A77) — a fact citing an owner-unresolvable doc; closes the V4 NULL bypass'
WHERE NOT EXISTS (SELECT 1 FROM ontology_validator_config WHERE check_code='V11');

DROP TRIGGER IF EXISTS ontvv_v11_matter_facts ON matter_facts;
CREATE TRIGGER ontvv_v11_matter_facts BEFORE INSERT OR UPDATE OF source_id, matter_code ON matter_facts
  FOR EACH ROW EXECUTE FUNCTION ontvv_v11_null_owner();

-- Rollback: DROP TRIGGER IF EXISTS ontvv_v11_matter_facts ON matter_facts;
--           DROP FUNCTION IF EXISTS ontvv_v11_null_owner();
--           DELETE FROM ontology_validator_config WHERE check_code='V11';
