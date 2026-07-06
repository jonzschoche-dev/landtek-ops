-- deploy_733: parcels.client_code — resolve decision 7.1 (operator: "add parcels.client_code").
--
-- WHY: the survey-geometry layer `parcels` carried only `matter_code`, so geometry client
-- isolation (ONTOLOGY.md axiom A9) had no DECLARED client to cross-check — the blocker to V6.
-- Adding `client_code` (symmetric with `map_parcels`) gives A9 a clean signal on BOTH geometry
-- layers. This UNBLOCKS the V6 shadow draft (docs/ontology_validator_spec.md §8); it does NOT
-- apply V6 — enforcement is a separate, approval-gated step (shadow-first).
--
-- Nullable (NOT "NOT NULL", unlike map_parcels): a parcel whose `matter_code` doesn't resolve to
-- a client must still be insertable (degrade-don't-crash) — a NULL client_code simply means
-- "no declared client", which V6 skips. `parcels` is empty (0 rows), so the backfill is a no-op
-- today but makes the column correct for every future write. Idempotent + additive.

ALTER TABLE parcels ADD COLUMN IF NOT EXISTS client_code text;

-- FK to the tenancy root (guarded — ADD CONSTRAINT has no IF NOT EXISTS).
DO $$
BEGIN
  IF NOT EXISTS (
      SELECT 1 FROM information_schema.table_constraints
      WHERE constraint_name = 'parcels_client_code_fkey' AND table_name = 'parcels') THEN
    ALTER TABLE parcels
      ADD CONSTRAINT parcels_client_code_fkey
      FOREIGN KEY (client_code) REFERENCES clients(client_code);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_parcels_client ON parcels (client_code);

-- Forward-fill from the existing matter_code via the same resolver V4/V6 use (matters→clients
-- OR clients directly). No-op at 0 rows; correct if rows are ever backfilled from another path.
UPDATE parcels
SET    client_code = _client_of(matter_code)
WHERE  client_code IS NULL AND matter_code IS NOT NULL;
