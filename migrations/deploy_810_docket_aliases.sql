-- deploy_810_docket_aliases.sql — operator-curated docket ALIASES for the ingest significance engine.
-- The docket-exact rule stays: an alias is still an EXACT registry string (curated here, never fuzzy-matched).
-- extract_email_attachments.load_registries() expands each matter into docket_number + docket_aliases needles.
-- Additive + idempotent; rollback = drop the column.

BEGIN;

ALTER TABLE matters ADD COLUMN IF NOT EXISTS docket_aliases text[];
COMMENT ON COLUMN matters.docket_aliases IS
  'Curated EXACT alias strings for this matter''s docket (court-caption phrasing, bare CTN-less ARTA refs). Consumed by the ingest significance engine (deploy_810). Docket-exact discipline: aliases are curated literals, never fuzzy.';

-- Court captions as they actually appear on filings/filenames (the registry docket is 'CV-2026-360',
-- but every filed document says 'Civil Case No. 26-360').
UPDATE matters SET docket_aliases = ARRAY['Civil Case No. 26-360', 'Civil Case No 26-360', 'Civil Case 26-360']
 WHERE matter_code = 'MWK-CV26360';

-- Guardianship: Special Proceeding 2680 (matter has no docket_number registered; aliases carry it).
UPDATE matters SET docket_aliases = ARRAY['Special Proceeding 2680', 'Sp. Proc. No. 2680', 'Special Proceeding No. 2680']
 WHERE matter_code = 'MWK-GUARDIANSHIP';

-- ARTA: the bare CTN-less form ('SL-2026-0209-1319') appears in agency filenames/bodies.
-- (Substring matching already covers the 'NOR-CTN …' prefixed variants of 'CTN …' dockets.)
UPDATE matters SET docket_aliases = ARRAY[replace(docket_number, 'CTN ', '')]
 WHERE docket_number LIKE 'CTN SL-%' AND docket_aliases IS NULL;

COMMIT;

-- Verify
SELECT matter_code, docket_number, docket_aliases FROM matters WHERE docket_aliases IS NOT NULL ORDER BY matter_code;
