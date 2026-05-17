-- deploy_170: add tax-metadata columns so phantom title_refs can move to their
-- proper home. Per Jonathan 2026-05-17: T-2023 / T-025-07 / T-001-00030 are
-- not phantoms — they're tax years, Property Index Numbers, and Assessor
-- Reference Numbers wrongly captured by the title-extraction regex.

BEGIN;

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS tax_years              int[]   DEFAULT '{}'::int[],
  ADD COLUMN IF NOT EXISTS property_index_numbers text[]  DEFAULT '{}'::text[],
  ADD COLUMN IF NOT EXISTS arp_numbers            text[]  DEFAULT '{}'::text[];

COMMENT ON COLUMN documents.tax_years IS
  'Years referenced in tax-doc context (RPT YYYY, Tax Year YYYY, FY YYYY). '
  'Previously misparsed into title_refs as T-2023 etc.';
COMMENT ON COLUMN documents.property_index_numbers IS
  'PH Property Index Numbers (PIN) — typically NNN-NN-NNN-NN-NNN or shorter '
  'LGU-Mercedes form NNN-NNNNN. Bridges title world to tax-assessment world. '
  'Previously misparsed into title_refs as T-025-07 etc.';
COMMENT ON COLUMN documents.arp_numbers IS
  'Assessor Reference Numbers — typically GR-YYYY-XX-NN-NNN-NNNNN format. '
  'Previously misparsed into title_refs as T-2014-HH-07-001-00268 etc.';

CREATE INDEX IF NOT EXISTS idx_documents_tax_years ON documents USING GIN (tax_years);
CREATE INDEX IF NOT EXISTS idx_documents_pin       ON documents USING GIN (property_index_numbers);
CREATE INDEX IF NOT EXISTS idx_documents_arp       ON documents USING GIN (arp_numbers);

-- Same arrays on client_history for downstream queries (e.g., "show every
-- event referencing PIN 025-07-003-01-039")
ALTER TABLE client_history
  ADD COLUMN IF NOT EXISTS tax_years              int[]   DEFAULT '{}'::int[],
  ADD COLUMN IF NOT EXISTS property_index_numbers text[]  DEFAULT '{}'::text[],
  ADD COLUMN IF NOT EXISTS arp_numbers            text[]  DEFAULT '{}'::text[];

CREATE INDEX IF NOT EXISTS idx_chist_tax_years ON client_history USING GIN (tax_years);
CREATE INDEX IF NOT EXISTS idx_chist_pin       ON client_history USING GIN (property_index_numbers);
CREATE INDEX IF NOT EXISTS idx_chist_arp       ON client_history USING GIN (arp_numbers);

COMMIT;
