-- deploy_808_composition_layer.sql — COMPOSITION LAYER, shadow install.
-- Implements docs/COMPOSITION_MODEL_DRAFT.md §2.4/2.5 under ontology governance A54–A56 (deploy_801/802).
-- ADDITIVE + SHADOW: new table + new columns + new indexes; the A54/A56 write-guards install in mode='log'
-- (they LOG violations to holes_findings via ontology_reject but do NOT raise). Flip to enforced with:
--     UPDATE ontology_validator_config SET mode='block' WHERE check_code IN ('V9','V10');
-- Fully reversible: DROP the table/columns/functions/config rows.
-- Idempotent (IF NOT EXISTS / CREATE OR REPLACE / ON CONFLICT). Run: psql -U n8n -d n8n -f this.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. document_parts — sub-document page ranges (COMPOSITION §2.4).
--    A55: a part carries NO provenance/connectivity of its own — it INHERITS the parent document's
--    (A41 connectivity + A42 provenance). Deliberately thin: no model_used/ocr_quality/embedded columns.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS document_parts (
  id          serial PRIMARY KEY,
  doc_id      integer NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  part_index  integer NOT NULL,                       -- order of the part within its parent document
  page_start  integer,
  page_end    integer,
  kind        text,                                   -- 'annex' | 'exhibit' | 'section' | 'cover' | 'body' | ...
  label       text,                                   -- 'Annex A', 'Exhibit 3'
  created_at  timestamptz DEFAULT now(),
  UNIQUE (doc_id, part_index),
  CONSTRAINT document_parts_page_order CHECK (page_end IS NULL OR page_start IS NULL OR page_end >= page_start)
);
CREATE INDEX IF NOT EXISTS idx_document_parts_doc ON document_parts (doc_id);
COMMENT ON TABLE  document_parts IS
  'Sub-document page ranges (COMPOSITION §2.4). A part inherits its parent documents row''s connectivity(A41) + provenance(A42); never separately gated/stamped/counted (A55).';

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Exhibit composition on case_thread_documents (COMPOSITION §2.5).
--    A "filing" = a case_thread whose documents carry ordered exhibit labels; case_bundle.py binds them.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE case_thread_documents ADD COLUMN IF NOT EXISTS exhibit_label text;                 -- 'A', 'B', ...
ALTER TABLE case_thread_documents ADD COLUMN IF NOT EXISTS order_seq      integer;             -- bind order
ALTER TABLE case_thread_documents ADD COLUMN IF NOT EXISTS part_id        integer
      REFERENCES document_parts(id) ON DELETE SET NULL;                                        -- page-range exhibit
CREATE INDEX IF NOT EXISTS idx_ctd_thread_order ON case_thread_documents (thread_id, order_seq);

-- 3. Finalized marker on case_threads (A56 keys immutability on this; shadow, nullable).
ALTER TABLE case_threads ADD COLUMN IF NOT EXISTS finalized_at timestamptz;
COMMENT ON COLUMN case_threads.finalized_at IS
  'When set, the thread is a FINALIZED filing: its exhibit set/order/labels become immutable (A56).';

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. V9 — A54 composition client-scope (enforce-at-write). A filing + every exhibit it binds must resolve
--    to ONE client, regardless of exhibit source. Trigger on case_thread_documents; mirrors ontvv V4.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION ontvv_v9_composition_client() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE m text; tc text; dc text;
BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code='V9';
  IF m IS NULL OR m='off' THEN RETURN NEW; END IF;

  SELECT _client_of(t.parent_case_file) INTO tc FROM case_threads t WHERE t.id = NEW.thread_id;  -- thread's client
  SELECT _client_of(COALESCE(d.matter_code, d.case_file)) INTO dc FROM documents d WHERE d.id = NEW.doc_id;  -- exhibit's client

  IF tc IS NOT NULL AND dc IS NOT NULL AND tc <> dc THEN
    PERFORM ontology_reject('ONTOLOGY_COMPOSITION_CROSS',
      'case_thread_documents: thread '||NEW.thread_id||' (client '||tc||') binds a document owned by client '||dc||' (doc_id='||NEW.doc_id||')');
    IF m='block' THEN
      RAISE EXCEPTION 'ontology_validator V9: composition client-scope — a % filing cannot bind a document owned by client % (ONTOLOGY.md A54)', tc, dc;
    END IF;
  END IF;
  RETURN NEW;
END $fn$;

DROP TRIGGER IF EXISTS ontvv_v9_ctd ON case_thread_documents;
CREATE TRIGGER ontvv_v9_ctd BEFORE INSERT OR UPDATE ON case_thread_documents
  FOR EACH ROW EXECUTE FUNCTION ontvv_v9_composition_client();

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. V10 — A56 finalized-filing immutability. Once a thread is finalized, its exhibit composition
--    (exhibit_label / order_seq / part_id / membership) is frozen — it is evidence of what was submitted.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION ontvv_v10_filing_immutable() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE m text; fin timestamptz; tid integer;
BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code='V10';
  IF m IS NULL OR m='off' THEN RETURN COALESCE(NEW, OLD); END IF;

  tid := COALESCE(OLD.thread_id, NEW.thread_id);
  SELECT finalized_at INTO fin FROM case_threads WHERE id = tid;
  IF fin IS NULL THEN RETURN COALESCE(NEW, OLD); END IF;  -- not finalized → mutable

  IF TG_OP='DELETE'
     OR NEW.exhibit_label IS DISTINCT FROM OLD.exhibit_label
     OR NEW.order_seq     IS DISTINCT FROM OLD.order_seq
     OR NEW.part_id       IS DISTINCT FROM OLD.part_id
     OR NEW.doc_id        IS DISTINCT FROM OLD.doc_id THEN
    PERFORM ontology_reject('ONTOLOGY_FILING_IMMUTABLE',
      'case_thread_documents: '||TG_OP||' on finalized thread '||tid||' (exhibit composition is frozen, A56)');
    IF m='block' THEN
      RAISE EXCEPTION 'ontology_validator V10: filing immutability — thread % is finalized; its exhibit set/order/labels cannot change (ONTOLOGY.md A56)', tid;
    END IF;
  END IF;
  RETURN COALESCE(NEW, OLD);
END $fn$;

DROP TRIGGER IF EXISTS ontvv_v10_ctd ON case_thread_documents;
CREATE TRIGGER ontvv_v10_ctd BEFORE UPDATE OR DELETE ON case_thread_documents
  FOR EACH ROW EXECUTE FUNCTION ontvv_v10_filing_immutable();

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. Register the invariants in SHADOW (mode='log'). Flip to 'block' to enforce.
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO ontology_validator_config (check_code, mode, note, updated_at) VALUES
  ('V9',  'log', 'composition client-scope (A54): a filing + its exhibits resolve to ONE client', now()),
  ('V10', 'log', 'finalized-filing immutability (A56): frozen exhibit set/order/labels on case_threads.finalized_at', now())
ON CONFLICT (check_code) DO UPDATE SET note=EXCLUDED.note, updated_at=now();
-- A55 (a part inherits parent connectivity(A41)+provenance(A42), never separately gated/stamped/counted) is
-- enforced BY CONSTRUCTION — document_parts carries no provenance columns (see its thin schema + COMMENT above)
-- — so it has no write-guard to flip. It is a modeling + consumer-side rule, deliberately NOT a config row.

COMMIT;
