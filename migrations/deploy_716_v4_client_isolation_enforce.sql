-- deploy_716_v4_client_isolation_enforce.sql — A5 client-isolation, ENFORCED (V4 shadow→block).
--
-- Why a trigger, not a rigid column FK: `matter_code` legitimately holds a matter code OR a client
-- code (case_file ≠ matter_code; e.g. 65 facts + 4 docs tagged 'MWK-001', the CLIENT code). A strict
-- matter_code→matters FK would reject those legitimate MWK writes. The referential chain matters→clients
-- already exists; client ISOLATION (the A5 invariant) is enforced here at write-time on matter_facts.
--
-- Safety: V4 cross-client = 0 right now → a block trigger rejects ZERO current writes (same profile as
-- the V1/V3 flip). Fires only on new INSERT/UPDATE; existing rows untouched. Logger is crash-proof.
-- Idempotent.

-- Robust client resolution: a code resolves to a client whether it is a matter code OR a client code.
CREATE OR REPLACE FUNCTION _client_of(code text) RETURNS text LANGUAGE sql STABLE AS $$
  SELECT COALESCE(
    (SELECT client_code FROM matters  WHERE matter_code = code),
    (SELECT client_code FROM clients  WHERE client_code = code)
  );
$$;

-- V4: a fact may not cite a document owned by a DIFFERENT client.
CREATE OR REPLACE FUNCTION ontvv_client_isolation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m text; fc text; dc text;
BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code='V4';
  IF m IS NULL OR m='off' THEN RETURN NEW; END IF;

  fc := _client_of(NEW.matter_code);                 -- the fact's client
  IF NEW.source_id ~ '^[0-9]+$' THEN                 -- cited doc (numeric source_id)
    SELECT _client_of(COALESCE(d.matter_code, d.case_file))
      INTO dc FROM documents d WHERE d.id = NEW.source_id::int;
  END IF;

  IF fc IS NOT NULL AND dc IS NOT NULL AND fc <> dc THEN
    PERFORM ontology_reject('ONTOLOGY_CLIENT_CROSS',
      'matter_facts: fact client '||fc||' cites a document owned by client '||dc||' (source_id='||coalesce(NEW.source_id,'?')||')');
    IF m='block' THEN
      RAISE EXCEPTION 'ontology_validator V4: client isolation — a % fact cannot cite a document owned by client % (ONTOLOGY.md A5)', fc, dc;
    END IF;
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS ontvv_v4_matter_facts ON matter_facts;
CREATE TRIGGER ontvv_v4_matter_facts BEFORE INSERT OR UPDATE ON matter_facts
  FOR EACH ROW EXECUTE FUNCTION ontvv_client_isolation();

-- Flip V4 to enforce.
UPDATE ontology_validator_config SET mode='block', updated_at=now() WHERE check_code='V4';
