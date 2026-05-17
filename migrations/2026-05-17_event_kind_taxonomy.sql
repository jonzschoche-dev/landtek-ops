-- Layer A: Canonical event vocabulary for client_history (deploy_151).
--
-- Problem: client_history.event_kind has 64 distinct raw values with
-- overlapping semantics (email/email_received/email_sent, deed/annotation_deed_of_sale,
-- title/title_(tct/oct), etc.). You can't reliably ask "show me all deeds" or
-- "all correspondence" because the same act is split across multiple labels.
--
-- Fix: introduce 12 canonical event_kinds via a lookup table. Add
-- event_kind_canonical column to client_history and backfill. Keep raw
-- event_kind for evidence-grade round-trip (original classifier output).

BEGIN;

-- 1. Taxonomy table — definitive list of canonical kinds + definitions
CREATE TABLE IF NOT EXISTS event_kind_taxonomy (
    raw_kind        text PRIMARY KEY,
    canonical_kind  text NOT NULL,
    definition      text,
    created_at      timestamptz NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE event_kind_taxonomy IS
    'Maps the 64 raw event_kinds in client_history to 12 canonical kinds. '
    'Source of truth for the bible vocabulary (deploy_151).';

-- 2. Canonical-kind catalog (one row per canonical, definition only).
CREATE TABLE IF NOT EXISTS event_kind_canonical_def (
    canonical_kind  text PRIMARY KEY,
    description     text NOT NULL,
    sort_order      int  NOT NULL,
    is_real_event   boolean NOT NULL DEFAULT true  -- false for catch-alls needing reclassification
);

INSERT INTO event_kind_canonical_def (canonical_kind, description, sort_order, is_real_event) VALUES
  ('correspondence',      'Communication between parties — letter, email, notice, demand letter, reply, transcript', 10, true),
  ('legal_act',           'Instrument that asserts a legal effect — deed, contract, SPA, affidavit, motion, complaint, order, resolution', 20, true),
  ('title_annotation',    'Entry recorded on a TCT (Memorandum of Encumbrances) — annotation_*', 30, true),
  ('title_event',         'Title state-change event — issued, cancelled, transferred', 40, true),
  ('judicial_event',      'Court-procedural milestone — pretrial, mediation, hearing, trial, decision, deadline_*', 50, true),
  ('transaction',         'Money flow — registration fee, RPT, filing fee, CNR, receipt, financial statement', 60, true),
  ('tax_document',        'Tax declaration / tax-related government doc', 70, true),
  ('government_submission','Submission TO a government office (request/petition/agency filing)', 80, true),
  ('vital_record',        'Birth/death/marriage/civil-status certificate', 90, true),
  ('legal_memo',          'Internal legal memorandum or analysis', 100, true),
  ('survey_plan',         'Survey, subdivision plan, or technical descriptions', 110, true),
  ('procedural_intake',   'System-generated intake response (pre/post stage)', 120, true),
  ('uncategorized',       'Raw kind too generic to classify — needs human review',  900, false)
ON CONFLICT (canonical_kind) DO NOTHING;

-- 3. Populate raw → canonical mapping
INSERT INTO event_kind_taxonomy (raw_kind, canonical_kind, definition) VALUES
  -- correspondence
  ('letter',                  'correspondence', 'physical letter'),
  ('email_received',          'correspondence', 'inbound email'),
  ('email_sent',              'correspondence', 'outbound email'),
  ('email',                   'correspondence', 'generic email (direction unknown)'),
  ('notice',                  'correspondence', 'formal notice'),
  ('demand_letter',           'correspondence', 'demand letter'),
  ('reply',                   'correspondence', 'reply communication'),
  ('correspondence',          'correspondence', 'generic correspondence'),
  ('transcript',              'correspondence', 'meeting / call transcript'),
  ('summary',                 'correspondence', 'summary of a communication'),

  -- legal_act
  ('deed',                    'legal_act', 'deed (sale/donation/exchange)'),
  ('contract',                'legal_act', 'contract / agreement'),
  ('special_power_of_attorney','legal_act', 'SPA'),
  ('power_of_attorney',       'legal_act', 'POA'),
  ('affidavit',               'legal_act', 'affidavit'),
  ('motion',                  'legal_act', 'court motion'),
  ('complaint',               'legal_act', 'pleading: complaint'),
  ('court_filing',            'legal_act', 'generic court filing'),
  ('resolution',              'legal_act', 'court / LGU resolution'),
  ('order',                   'legal_act', 'court order'),

  -- title_annotation (all annotation_* kinds — both full strings and truncations seen in data)
  ('annotation_affidavit_of_confirmation',           'title_annotation', 'affidavit of confirmation on title'),
  ('annotation_affidavit_of_confirmation_of_s',      'title_annotation', 'affidavit of confirmation (truncated)'),
  ('annotation_affidavit_of_confirmation_of_sale',   'title_annotation', 'affidavit of confirmation of sale'),
  ('annotation_affidavit_of_loss',                   'title_annotation', 'affidavit of loss'),
  ('annotation_confirmation_of_sale',                'title_annotation', 'confirmation of sale'),
  ('annotation_deed_of_absolute_sale',               'title_annotation', 'deed of absolute sale'),
  ('annotation_deed_of_confirmation',                'title_annotation', 'deed of confirmation'),
  ('annotation_deed_of_donation',                    'title_annotation', 'deed of donation'),
  ('annotation_deed_of_sale',                        'title_annotation', 'deed of sale'),
  ('annotation_issuance_of_new_owner''s_duplic',     'title_annotation', 'issuance of new owner''s duplicate (truncated)'),
  ('annotation_issuance_of_new_owner''s_duplicate',  'title_annotation', 'issuance of new owner''s duplicate'),
  ('annotation_kasunduan_sa_pagbibilihan_ng_b',      'title_annotation', 'kasunduan sa pagbibilihan ng bahagi (truncated)'),
  ('annotation_kasunduan_sa_pagbibilihan_ng_bahagi', 'title_annotation', 'kasunduan sa pagbibilihan ng bahagi'),
  ('annotation_partition_-_subdivision_agreem',      'title_annotation', 'partition / subdivision agreement (truncated)'),
  ('annotation_partition_subdivision_agreemen',      'title_annotation', 'partition / subdivision agreement (truncated)'),
  ('annotation_partition_subdivision_agreement',     'title_annotation', 'partition / subdivision agreement'),
  ('annotation_petition',                            'title_annotation', 'petition annotation'),
  ('annotation_reference_to_tct-52540',              'title_annotation', 'reference to TCT 52540'),
  ('annotation_request',                             'title_annotation', 'annotation request'),
  ('annotation_resolution',                          'title_annotation', 'resolution annotation'),
  ('annotation_sale',                                'title_annotation', 'sale annotation'),
  ('annotation_sale_:_bir_-_certificate_autho',      'title_annotation', 'BIR CAR sale annotation (truncated)'),
  ('annotation_sale_(bir_certificate_authoriz',      'title_annotation', 'BIR CAR sale annotation (truncated)'),
  ('annotation_special_power_of_attorney',           'title_annotation', 'SPA annotation on title'),

  -- title_event
  ('title',                   'title_event', 'generic title row'),
  ('title_(tct/oct)',         'title_event', 'TCT/OCT title doc'),
  ('title_(tct)',             'title_event', 'TCT title doc'),
  ('title_issued',            'title_event', 'title issuance event'),

  -- judicial_event
  ('mediation_scheduled',     'judicial_event', 'mediation conference scheduled'),
  ('deadline_pending',        'judicial_event', 'pending case deadline'),
  ('deadline_completed',      'judicial_event', 'completed case deadline'),

  -- transaction
  ('tx_registration_fee',     'transaction', 'registration fee paid'),
  ('tx_rpt',                  'transaction', 'real property tax paid'),
  ('tx_filing_fee',           'transaction', 'court filing fee paid'),
  ('tx_cnr',                  'transaction', 'CNR transaction'),
  ('tx_other',                'transaction', 'other money flow'),
  ('receipt',                 'transaction', 'payment receipt'),
  ('financial_statement',     'transaction', 'financial statement'),

  -- tax_document
  ('tax_document',            'tax_document', 'tax declaration / RPT doc'),

  -- government_submission
  ('government_submission',   'government_submission', 'submission to a govt office'),

  -- vital_record
  ('death_of_administrator',  'vital_record', 'death of an administrator/agent'),

  -- legal_memo
  ('legal_memorandum',        'legal_memo', 'legal memo / analysis'),

  -- survey_plan
  ('plan',                    'survey_plan', 'survey or subdivision plan'),

  -- procedural_intake
  ('intake_pre_open',         'procedural_intake', 'pre-stage intake opened'),
  ('intake_post_open',        'procedural_intake', 'post-stage intake opened'),

  -- uncategorized (catch-alls — flagged for human review)
  ('doc',                     'uncategorized', 'generic doc — needs reclassification'),
  ('other',                   'uncategorized', 'other — needs reclassification'),
  ('legal',                   'uncategorized', 'legal — too vague, needs reclassification')
ON CONFLICT (raw_kind) DO UPDATE SET
  canonical_kind = EXCLUDED.canonical_kind,
  definition     = EXCLUDED.definition;

-- 4. Add canonical column to client_history
ALTER TABLE client_history
  ADD COLUMN IF NOT EXISTS event_kind_canonical text;

CREATE INDEX IF NOT EXISTS idx_chist_canonical
  ON client_history (client_code, event_kind_canonical, event_date DESC);

-- 5. Backfill
UPDATE client_history h
   SET event_kind_canonical = t.canonical_kind
  FROM event_kind_taxonomy t
 WHERE t.raw_kind = h.event_kind
   AND h.event_kind_canonical IS DISTINCT FROM t.canonical_kind;

-- 6. Any rows with unmapped raw_kinds → mark as uncategorized so we don't lose them
UPDATE client_history
   SET event_kind_canonical = 'uncategorized'
 WHERE event_kind_canonical IS NULL;

-- 7. Report
SELECT 'mapping_count' AS metric, COUNT(*) AS n FROM event_kind_taxonomy
UNION ALL
SELECT 'rows_backfilled', COUNT(*) FROM client_history WHERE event_kind_canonical IS NOT NULL
UNION ALL
SELECT 'rows_unmapped', COUNT(*) FROM client_history WHERE event_kind_canonical IS NULL;

-- 8. Per-canonical histogram (sanity check)
SELECT event_kind_canonical, COUNT(*) AS n
  FROM client_history WHERE client_code = 'MWK'
 GROUP BY 1 ORDER BY 2 DESC;

COMMIT;
