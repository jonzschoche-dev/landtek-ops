-- deploy_1109 — Court Record module (deterministic; no AI). Directive 2026-10-15:
-- "LandTek software application, not an AI search." Trigger: Gerry Hoppe's letter to the court in
-- Spec. Proc. No. 2680 (RTC Br. 41 Daet) could not be found; fees paid were not tracked.
--
-- Tables: court_case, court_record, fee_payment. Named court_case (not "case": SQL reserved word;
-- existing `cases` table is a CRM/intel table with a different shape). court_case.matter_id references
-- the existing matters(id) (SP 2680 = matters.matter_code 'MWK-GUARDIANSHIP', id 32 at time of writing).
-- Idempotent. No deletes, no changes to existing tables. Revert: DROP the three tables + two types.
BEGIN;

DO $$ BEGIN
  CREATE TYPE court_record_kind AS ENUM ('filing','order','notice','letter_received','pleading','receipt');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE court_record_status AS ENUM ('in_hand','reported_not_in_hand');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS court_case (
  id          serial PRIMARY KEY,
  code        text NOT NULL UNIQUE,              -- e.g. 'SP-2680'
  title       text,
  court       text,
  branch      text,
  matter_code text,                              -- soft link to matters.matter_code
  matter_id   integer REFERENCES matters(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS court_record (
  id               serial PRIMARY KEY,
  case_id          integer NOT NULL REFERENCES court_case(id),
  date_received    date,
  date_of_document date,
  kind             court_record_kind NOT NULL,
  from_party       text,
  to_party         text,
  summary          text,
  file_path        text,
  sha256           char(64),
  ocr_text         text,
  status           court_record_status NOT NULL DEFAULT 'in_hand',
  created_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT court_record_case_sha_uq UNIQUE (case_id, sha256),
  CONSTRAINT court_record_hand_has_file CHECK (status = 'reported_not_in_hand' OR sha256 IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS court_record_case_kind_idx ON court_record (case_id, kind);
CREATE INDEX IF NOT EXISTS court_record_docdate_idx   ON court_record (date_of_document);
CREATE INDEX IF NOT EXISTS court_record_fts_idx ON court_record
  USING gin (to_tsvector('simple', coalesce(summary,'') || ' ' || coalesce(ocr_text,'') || ' ' ||
                                   coalesce(from_party,'') || ' ' || coalesce(to_party,'')));

CREATE TABLE IF NOT EXISTS fee_payment (
  id                serial PRIMARY KEY,
  case_id           integer NOT NULL REFERENCES court_case(id),
  date              date,
  or_no             text,
  amount            numeric(12,2) NOT NULL CHECK (amount >= 0),
  payee             text,
  purpose           text,
  receipt_record_id integer REFERENCES court_record(id),
  created_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fee_payment_case_or_uq UNIQUE (case_id, or_no)
);

INSERT INTO court_case (code, title, court, branch, matter_code, matter_id)
SELECT 'SP-2680', 'Spec. Proc. No. 2680 — Judicial Guardianship, Mary Worrick Keesey',
       'RTC Daet, Camarines Norte', 'Branch 41', 'MWK-GUARDIANSHIP',
       (SELECT id FROM matters WHERE matter_code = 'MWK-GUARDIANSHIP')
WHERE NOT EXISTS (SELECT 1 FROM court_case WHERE code = 'SP-2680');

COMMIT;
