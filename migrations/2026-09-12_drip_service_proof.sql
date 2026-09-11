-- Drip hardening (operator rule 2026-09-12): "unless the evidence is in the corpus, a document must
-- always be assumed NOT served." Service proof is a corpus DOCUMENT (documents.id — the received-stamp
-- copy / registry card, ingested), never free text. The DB refuses served_at without it. Idempotent.
BEGIN;

ALTER TABLE office_obligation ADD COLUMN IF NOT EXISTS service_proof_doc_id INT REFERENCES documents(id);

ALTER TABLE office_obligation DROP CONSTRAINT IF EXISTS drip_no_invented_period;
ALTER TABLE office_obligation ADD CONSTRAINT drip_no_invented_period
  CHECK (due_at IS NULL OR (served_at IS NOT NULL AND clock_rule IS NOT NULL AND service_proof_doc_id IS NOT NULL));

ALTER TABLE office_obligation DROP CONSTRAINT IF EXISTS drip_service_needs_corpus_proof;
ALTER TABLE office_obligation ADD CONSTRAINT drip_service_needs_corpus_proof
  CHECK (served_at IS NULL OR service_proof_doc_id IS NOT NULL);

COMMENT ON COLUMN office_obligation.service_proof_doc_id IS
  'The corpus document proving service (received-stamp copy / registry card). Absent ⇒ NOT served. Free text is not proof.';

COMMIT;
