-- DRAFT DELTA (NOT APPLIED) — e-notarization for the R2/R3 rungs, on top of the LIVE drip v2 fabric
-- (migrations/drip_v2_fabric_REVISED_2026-10-20.sql, applied 2026-10-19 23:48 UTC). Additive only.
-- Source: case_work/LandTek-Corp/RESEARCH_DIGITAL_NOTARIZATION_2026-10.md (A.M. No. 24-10-14-SC, 4 Feb 2025).
-- Dry run:  (sed '$d' this_file; echo ROLLBACK;) | docker exec -i n8n-postgres-1 psql -U n8n -d n8n -v ON_ERROR_STOP=1

BEGIN;
CREATE TABLE IF NOT EXISTS instrument_notarization (
    id                   bigserial PRIMARY KEY,
    instrument_id        bigint NOT NULL REFERENCES drip_instrument(id),
    mode                 text NOT NULL CHECK (mode IN ('REN','IEN','paper','us_notary_apostille','consular')),
    act                  text NOT NULL CHECK (act IN ('jurat','acknowledgment','oath')),
    affiant              text NOT NULL,                  -- 'Jonathan Paul Zschoche (personally and as AIF)' | 'Patricia Keesey Zschoche'
    capacity_annexed     boolean NOT NULL DEFAULT false, -- SPA + apostille attached when acting as AIF
    platform             text,                           -- accredited ENF (REN/IEN)
    notary_name          text NOT NULL,
    notary_commission    text NOT NULL,                  -- number / term / issuing authority as printed on the certificate
    commission_valid_until date NOT NULL,
    affiant_id_type      text NOT NULL,
    affiant_id_expiry    date NOT NULL,
    affiant_location     text NOT NULL,                  -- REN: as disclosed + geolocated (PH)
    notarized_at         timestamptz NOT NULL,
    notarial_book_ref    text,                           -- doc / page / book / series or electronic book entry
    seal_qr_ref          text,                           -- QR / verification id
    sc_database_ref      text,
    session_video_path   text,                           -- downloaded recording (Rule IV §8), stored privately
    fee_php              numeric(10,2),                  -- feeds loss_line (cost_incurred)
    notarized_doc_id     integer REFERENCES documents(id), -- the notarized PDF, ingested
    created_at           timestamptz NOT NULL DEFAULT now(),
    CHECK (commission_valid_until >= notarized_at::date),          -- the Exh. L/M/N lesson, enforced
    CHECK (affiant_id_expiry >= notarized_at::date),
    CHECK (mode <> 'REN' OR (platform IS NOT NULL AND seal_qr_ref IS NOT NULL)),
    CHECK (affiant NOT ILIKE '%AIF%' OR capacity_annexed)
);

-- Does the receiving office take the form? (X15) Unknown is a real state, never a pass.
CREATE TABLE IF NOT EXISTS forum_intake (
    forum_code          text PRIMARY KEY,
    accepts_enotarized  text NOT NULL DEFAULT 'unknown' CHECK (accepts_enotarized IN ('yes','no','unknown','tested_yes','tested_no')),
    channel             text,                            -- email / e-filing portal / printout of the PDF / wet-ink original
    basis               text,                            -- circular, written reply, or the test-document outcome
    updated_at          timestamptz NOT NULL DEFAULT now()
);
INSERT INTO forum_intake (forum_code, accepts_enotarized, basis) VALUES
 ('LRA','yes','SC–LRA Joint Memorandum Circular 13 Oct 2026 (press: Daily Tribune 15 Oct 2026) [verify text]'),
 ('SEC','yes','SC–SEC Joint Memorandum Circular 13 Oct 2026 (press) [verify text]'),
 ('DILG-RD5','unknown',NULL), ('BLGF-RO5','unknown',NULL), ('BLGF-CO','unknown',NULL),
 ('CSC-RO5','unknown',NULL), ('OMB','unknown',NULL), ('OP','unknown',NULL), ('COA-RO5','unknown',NULL)
ON CONFLICT (forum_code) DO NOTHING;

-- Lint additions for sworn instruments, compatible with the live calm_routine register
INSERT INTO drip_lint_rule (rule_class, pattern, audiences, max_rung, action, rationale)
SELECT * FROM (VALUES
 ('characterization', '\m(intentional\w*|deliberate\w*|knowingly|wilful\w*|willful\w*|in bad faith|so as to|in order to (harass|delay|favor))\M', '{forum}'::text[], NULL::int, 'refuse', 'Sworn affidavits state what the affiant saw and what the exhibits show, never another person''s state of mind (exhibit test; perjury exposure)')
) v(rule_class, pattern, audiences, max_rung, action, rationale)
ON CONFLICT (rule_class, pattern) DO NOTHING;

COMMIT;
