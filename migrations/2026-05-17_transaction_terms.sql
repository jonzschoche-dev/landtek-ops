-- deploy_171: substantive transaction terms columns for forensic ledger.
-- Per Jonathan 2026-05-17: a deed entry that doesn't capture price, lot, and
-- subdivision plan is useless for proving illegal subdivisions or undervalued
-- sales. Add hard-typed fields for structured extraction.

BEGIN;

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS lot_number            text,
  ADD COLUMN IF NOT EXISTS subdivision_plan      text,
  ADD COLUMN IF NOT EXISTS area_sqm              numeric(14,2),
  ADD COLUMN IF NOT EXISTS consideration_price   numeric(18,2),
  ADD COLUMN IF NOT EXISTS consideration_currency text DEFAULT 'PHP',
  ADD COLUMN IF NOT EXISTS grantor_seller        text,
  ADD COLUMN IF NOT EXISTS grantee_buyer         text,
  ADD COLUMN IF NOT EXISTS terms_extracted_at    timestamptz,
  ADD COLUMN IF NOT EXISTS terms_provenance      text;

COMMENT ON COLUMN documents.lot_number IS 'e.g., Lot 2-X-6-P (per PH subdivision-plan convention)';
COMMENT ON COLUMN documents.subdivision_plan IS 'e.g., Psd-05-026614, LRC Psd-12802';
COMMENT ON COLUMN documents.area_sqm IS 'Land area in square meters';
COMMENT ON COLUMN documents.consideration_price IS 'Monetary consideration paid (in PHP unless currency overridden)';
COMMENT ON COLUMN documents.grantor_seller IS 'Conveying party (seller, donor, transferor) — verbatim name';
COMMENT ON COLUMN documents.grantee_buyer IS 'Receiving party (buyer, donee, transferee) — verbatim name';

CREATE INDEX IF NOT EXISTS idx_documents_lot_number      ON documents (lot_number) WHERE lot_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_subdivision_plan ON documents (subdivision_plan) WHERE subdivision_plan IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_consideration   ON documents (consideration_price) WHERE consideration_price IS NOT NULL;

COMMIT;
