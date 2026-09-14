-- The Drip — ESCALATION RUNGS + addressees (operator decisions 2026-09-14).
--
-- "Rungs, not separate clocks": the eight target offices are NOT eight parallel demand clocks. They
-- are the ordered ladder each municipal clock climbs when it lapses — municipal officer → provincial
-- supervisor → national oversight → forum. A supervisory letter's force is "your subordinate has
-- stood in default N days", so a rung may only fire on a real, dated lapse beneath it. One lapse
-- advances ONE rung; never the same letter sideways twice (anti-circular, 8 Sep flag).
--
-- Addresses are SOURCED FROM THE CORPUS (our own sent mail + the instruments' own addressee blocks),
-- never invented. email_confidence: 'verified' = we have corresponded with it; 'routed' = the office's
-- general/known-good mailbox, attn the named officer (how the provincial packet is already addressed);
-- 'unverified' = needs confirmation before use. The drip sends nothing either way — this only
-- determines what a STAGED DRAFT is addressed to.
--
-- Engr. Balane: NO rungs, NO address. CV 26-360 defendant — every approach routes through Atty.
-- Barandon. Olaguera: NO rungs (withdrawn; no 5-Sep tender, no clock).
BEGIN;

ALTER TABLE office_obligation ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE office_obligation ADD COLUMN IF NOT EXISTS email_confidence TEXT;
ALTER TABLE office_obligation ADD COLUMN IF NOT EXISTS email_source TEXT;

CREATE TABLE IF NOT EXISTS escalation_rung (
  id               BIGSERIAL PRIMARY KEY,
  obligation_id    BIGINT NOT NULL REFERENCES office_obligation(id) ON DELETE CASCADE,
  seq              INT NOT NULL,                   -- 1 = first rung after the municipal lapse
  office           TEXT NOT NULL,
  officer          TEXT,
  email            TEXT,
  email_confidence TEXT NOT NULL DEFAULT 'unverified',
  email_source     TEXT,
  instrument_ref   TEXT,
  statutory_basis  TEXT,                           -- why this office supervises (cited, never invented)
  state            TEXT NOT NULL DEFAULT 'pending',-- pending | staged | served | performed | exhausted
  staged_at        TIMESTAMPTZ,
  notes            TEXT,
  UNIQUE (obligation_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_rung_next ON escalation_rung(obligation_id, state, seq);
COMMENT ON TABLE escalation_rung IS
  'Ordered escalation ladder per obligation. A lapse advances exactly one rung (lowest seq still '
  'pending). Rungs are never parallel demands and never carry their own clock.';

-- ── municipal addressees (from our own correspondence) ────────────────────────────────────────────
UPDATE office_obligation SET email='ablagemma@yahoo.com', email_confidence='verified',
       email_source='our own correspondence — 15 messages, latest 2026-07-12'
 WHERE officer='Abla' AND email IS NULL;
UPDATE office_obligation SET email='loidamacale@mercedes.gov.ph', email_confidence='verified',
       email_source='our own correspondence — latest 2026-07-13'
 WHERE officer='Macale' AND email IS NULL;
UPDATE office_obligation SET email='mercedesmunicipality@gmail.com', email_confidence='verified',
       email_source='our own correspondence — 44 messages, latest 2026-08-27'
 WHERE officer='Mayor Pajarillo' AND email IS NULL;
UPDATE office_obligation SET email='mercedesmunicipality@gmail.com', email_confidence='routed',
       email_source='municipality mailbox, attn Assistant to the Mayor — no direct address on record'
 WHERE officer='Teope' AND email IS NULL;
-- Engr. Balane deliberately left with NO address (Barandon-gated).

-- ── LADDER: Municipal Assessor (Abla) → Provincial Assessor → BLGF → CSC ──────────────────────────
INSERT INTO escalation_rung (obligation_id, seq, office, officer, email, email_confidence, email_source,
                             instrument_ref, statutory_basis, notes)
SELECT o.id, v.seq, v.office, v.officer, v.email, v.conf, v.src, v.instr, v.basis, v.note
  FROM office_obligation o,
  (VALUES
    (1,'Office of the Provincial Assessor, Camarines Norte','HON. MAXIMO P. MAGANA, JR., REA',
     'pgcamarinesnorte@gmail.com','routed',
     'provincial government mailbox, attn the named Provincial Assessor — as DEMAND_PROVINCIAL_OVERSIGHT_2026-09 is already addressed',
     'case_work/MWK-001: ABLA_COMPARATOR_EXHIBIT_draft.md',
     'LGC §472 — provincial assessor supervision over municipal assessors',
     'Comparator: provincial productions vs the municipal sworn impossibility. He promised in writing 1 Jul, took the titles, went silent.'),
    (2,'Bureau of Local Government Finance','HON. JESSIE B. DOCTOLERO (RD) / J.R. ENCINARE',
     'jb.doctolero@blgf.gov.ph','verified','our own correspondence — latest 2026-08-15 (cc r5@blgf.gov.ph)',
     'case_work/MWK-001: BLGF_CO_SUPERVISORY_REVIEW_rev2.md',
     'BLGF supervision over local assessment operations',NULL),
    (3,'Civil Service Commission — Regional Office V','CSC-RO V','oacl@csc.gov.ph','routed',
     'address carried in the CSC instrument itself',
     'case_work/MWK-001: CSC_COMPLAINT_ABLA_draft.md',
     'CSC jurisdiction — serious dishonesty / refusal to perform official duty',
     'FORUM rung: a verified complaint, not a letter — counsel pulls')
  ) AS v(seq,office,officer,email,conf,src,instr,basis,note)
 WHERE o.officer='Abla'
ON CONFLICT (obligation_id, seq) DO NOTHING;

-- ── LADDER: Municipal Treasurer (Macale) → Provincial Treasurer → BLGF → LBAA ─────────────────────
INSERT INTO escalation_rung (obligation_id, seq, office, officer, email, email_confidence, email_source,
                             instrument_ref, statutory_basis, notes)
SELECT o.id, v.seq, v.office, v.officer, v.email, v.conf, v.src, v.instr, v.basis, v.note
  FROM office_obligation o,
  (VALUES
    (1,'Office of the Provincial Treasurer, Camarines Norte','HON. DANTE E. MANLAPAZ',
     'pgcamarinesnorte@gmail.com','routed',
     'provincial government mailbox, attn the named Provincial Treasurer — as the provincial packet is addressed',
     'case_work/MWK-001: DEMAND_PROVINCIAL_OVERSIGHT_2026-09.md',
     'LGC §470/§471 — provincial treasurer supervision over municipal treasurers',NULL),
    (2,'Bureau of Local Government Finance','HON. JESSIE B. DOCTOLERO (RD)',
     'jb.doctolero@blgf.gov.ph','verified','our own correspondence — latest 2026-08-15',
     'case_work/MWK-001: BLGF_252_LAPSE_NOTICE_draft.md',
     'BLGF supervision over local treasury operations; §252 lapse track',NULL),
    (3,'Local Board of Assessment Appeals','LBAA',NULL,'unverified',NULL,
     'case_work/MWK-001: BLGF_RPT_ESCALATION_SPINE.md',
     'LGC §252(d)/§226 — appeal window runs from the lapse',
     'FORUM rung: an appeal, not a letter — counsel pulls')
  ) AS v(seq,office,officer,email,conf,src,instr,basis,note)
 WHERE o.officer='Macale'
ON CONFLICT (obligation_id, seq) DO NOTHING;

-- ── LADDER: Mayor (both duties) → MLGOO → DILG PD/RD → Ombudsman ─────────────────────────────────
INSERT INTO escalation_rung (obligation_id, seq, office, officer, email, email_confidence, email_source,
                             instrument_ref, statutory_basis, notes)
SELECT o.id, v.seq, v.office, v.officer, v.email, v.conf, v.src, v.instr, v.basis, v.note
  FROM office_obligation o,
  (VALUES
    (1,'DILG — MLGOO Mercedes','MLGOO GUERRERO','dilgcamarinesnorte2020@gmail.com','verified',
     'our own correspondence — 21 messages, latest 2026-07-09',
     'case_work/MWK-001: MWK-001_REITERATION_MLGOO_MayorDefault_Sep2026',
     'DILG general supervision over local chief executives',
     'ALREADY the live edition track — this rung IS that escalation, not a new letter'),
    (2,'DILG Region V / Provincial Director','ATTY. ARNALDO E. ESCOBER, JR., CESO III (RD); PD RELUCIO',
     'aeescober@dilg.gov.ph','verified','our own correspondence — latest 2026-07-22',
     'case_work/MWK-001: BRANCH_B_ESCALATION_draft.md',
     'DILG provincial/regional supervision on MLGOO-level default',
     'The 10-Sep Reiteration''s own terms support elevation here on continued default'),
    (3,'Office of the Ombudsman','—',NULL,'unverified',NULL,
     'rides the open OAC-L 270 referral',
     'RA 3019 §3(e)/§3(f); Civil Code Art. 27',
     'FORUM rung: supplemental affidavit — counsel pulls')
  ) AS v(seq,office,officer,email,conf,src,instr,basis,note)
 WHERE o.officer='Mayor Pajarillo'
ON CONFLICT (obligation_id, seq) DO NOTHING;

-- ── LADDER: Teope → Ombudsman (single rung, referral already live) ────────────────────────────────
INSERT INTO escalation_rung (obligation_id, seq, office, officer, instrument_ref, statutory_basis, notes)
SELECT o.id, 1, 'Office of the Ombudsman', '—',
       'Ombudsman referral already live (1212, §3(i))', 'RA 3019 §3(i)',
       'FORUM rung: referral already filed — verify service of the underlying demand first'
  FROM office_obligation o WHERE o.officer='Teope'
ON CONFLICT (obligation_id, seq) DO NOTHING;

COMMIT;
