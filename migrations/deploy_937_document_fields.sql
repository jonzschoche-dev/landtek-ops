-- deploy_937: document_fields — every doc's typed extractions (the bulk intake table)
-- Full-text → structured rows. Rebuildable. Source of mass population for titles/facts UI.
--
--   docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/deploy_937_document_fields.sql

BEGIN;

CREATE TABLE IF NOT EXISTS document_fields (
    id                 bigserial PRIMARY KEY,
    doc_id             int NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    field_kind         text NOT NULL,   -- ctn|tct|oct|e_title|tax_dec|docket|date|amount|party|survey|forum|...
    value_raw          text NOT NULL,
    value_norm         text NOT NULL,
    source_span        text NOT NULL,
    char_start         int,
    char_end           int,
    extraction_method  text NOT NULL DEFAULT 'regex',
    created_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (doc_id, field_kind, value_norm)
);

CREATE INDEX IF NOT EXISTS document_fields_kind_norm_idx
  ON document_fields (field_kind, value_norm);
CREATE INDEX IF NOT EXISTS document_fields_doc_idx
  ON document_fields (doc_id);

COMMENT ON TABLE document_fields IS
  'Bulk typed extraction from full document text. Rebuildable. Not SoR for verified claims — '
  'feeds document_titles, title_brief, and (when matter-linked) matter_facts/fact_fields.';

-- track last populate run
CREATE TABLE IF NOT EXISTS table_populate_log (
    id              bigserial PRIMARY KEY,
    ran_at          timestamptz NOT NULL DEFAULT now(),
    docs_scanned    int,
    docs_with_hits  int,
    fields_written  int,
    titles_linked   int,
    parties_written int,
    matter_facts_written int,
    notes           text
);

COMMIT;

SELECT 'document_fields: ' || to_regclass('document_fields')::text;
