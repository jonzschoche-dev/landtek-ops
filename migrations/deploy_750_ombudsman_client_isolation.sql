-- deploy_750_ombudsman_client_isolation.sql
-- Client isolation for the Ombudsman Hunter (ONTOLOGY A35/A36/A37).
-- `ombudsman_candidates` gains a client_code, a CLIENT-SCOPED identity, and a V5 shadow validator
-- that catches a candidate citing another client's matter. Paired with scripts/ombudsman_hunter.py
-- (scoped reads/writes + client-keyed roster/own-side). SAFE single-client migration: every existing
-- row is MWK (verified 40/40), so the backfill and the UNIQUE re-key cannot collide.
BEGIN;

-- 1. Isolation key: add nullable → backfill (all live rows are MWK) → enforce NOT NULL.
ALTER TABLE ombudsman_candidates ADD COLUMN IF NOT EXISTS client_code text;
-- canonical clients.client_code (what _client_of() resolves MWK matters to — NOT the short 'MWK' key);
-- every live row is MWK, so this is a verified single-client backfill.
UPDATE ombudsman_candidates SET client_code = 'MWK-001' WHERE client_code IS NULL OR client_code = 'MWK';
ALTER TABLE ombudsman_candidates ALTER COLUMN client_code SET NOT NULL;

-- 2. Re-key identity to be client-scoped. The old UNIQUE(official, violation_code) collided across
--    clients — the same official+violation for MWK and PAR would UPSERT-merge into one row (A35).
ALTER TABLE ombudsman_candidates DROP CONSTRAINT IF EXISTS ombudsman_candidates_official_violation_code_key;
ALTER TABLE ombudsman_candidates
  ADD CONSTRAINT ombudsman_candidates_client_official_violation_key
  UNIQUE (client_code, official, violation_code);

-- 3. Index the scan/report read path (every report now filters WHERE client_code = active).
CREATE INDEX IF NOT EXISTS idx_ombuds_client_score ON ombudsman_candidates (client_code, score DESC);

-- 4. V5 shadow validator — a candidate's declared client must match the client of EVERY matter it
--    cites (A35). Modeled exactly on V4 ontvv_client_isolation: config-gated, logs via the crash-proof
--    ontology_reject(), RAISEs only in 'block'. Ships in 'log' (shadow), like V6/V7.
INSERT INTO ontology_validator_config (check_code, mode, note)
  SELECT 'V5', 'log', 'ombudsman candidate client-isolation (A35) — client_code must match every cited matter'
  WHERE NOT EXISTS (SELECT 1 FROM ontology_validator_config WHERE check_code = 'V5');

CREATE OR REPLACE FUNCTION ontvv_v5_ombudsman() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m text; mc text; rc text;
BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code = 'V5';
  IF m IS NULL OR m = 'off' THEN RETURN NEW; END IF;

  IF NEW.matters IS NOT NULL THEN
    FOREACH mc IN ARRAY NEW.matters LOOP
      rc := _client_of(rtrim(mc, '%'));                 -- strip wildcard; resolve the matter's client
      IF rc IS NOT NULL AND NEW.client_code IS NOT NULL AND rc <> NEW.client_code THEN
        PERFORM ontology_reject('ONTOLOGY_CLIENT_CROSS',
          'ombudsman_candidates: candidate client ' || NEW.client_code ||
          ' cites a matter owned by client ' || rc ||
          ' (matter=' || mc || ', official=' || COALESCE(NEW.official, '?') || ')');
        IF m = 'block' THEN
          RAISE EXCEPTION 'ontology_validator V5: client isolation — an ombudsman candidate for % cannot cite a matter owned by client % (ONTOLOGY.md A35)', NEW.client_code, rc;
        END IF;
      END IF;
    END LOOP;
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS ontvv_v5_ombudsman_candidates ON ombudsman_candidates;
CREATE TRIGGER ontvv_v5_ombudsman_candidates
  BEFORE INSERT OR UPDATE ON ombudsman_candidates
  FOR EACH ROW EXECUTE FUNCTION ontvv_v5_ombudsman();

COMMIT;
