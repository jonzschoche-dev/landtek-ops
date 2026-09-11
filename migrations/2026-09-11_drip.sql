-- The Drip (agent_specs/005) — obligation-clock engine. Additive, idempotent.
-- Clocks start ONLY at proof of receipt; lapse stages the PRE-BUILT consequence (never another
-- letter); editions advance counters from the record; NOTHING sends itself (A21 — drafts + work
-- orders only). Encodes the operator's 2026-09-08 process flag; seeds = the live September ledger.
BEGIN;

CREATE TABLE IF NOT EXISTS office_obligation (
  id              BIGSERIAL PRIMARY KEY,
  matter_code     TEXT NOT NULL,
  officer         TEXT NOT NULL,
  office          TEXT,
  obligation      TEXT NOT NULL,            -- the ONE demanded act (sub-items numbered inside)
  instrument_ref  TEXT,                     -- the demand instrument (case_work path / doc id)
  served_at       DATE,                     -- ONLY from proof of receipt; NULL = clock NOT running
  service_proof   TEXT,                     -- 'received-stamp <date>' / registry-card ref
  clock_rule      TEXT,                     -- statutory basis, cited; required if due_at is set
  due_at          DATE,                     -- served_at + period; NULL while unserved
  day_math        TEXT NOT NULL DEFAULT 'calendar—NEEDS-COUNSEL-VERIFICATION',
  state           TEXT NOT NULL DEFAULT 'draft_held',
    -- draft_held | held_counsel_route | withdrawn | served_running | replied_not_performed
    -- | partial | performed | lapsed | consequence_staged | consequence_filed
  consequence_ref TEXT,                     -- the PRE-BUILT consequence instrument (path)
  counsel_gate    TEXT,                     -- per-matter counsel who must pull (never defaulted)
  excluded_scope  TEXT,                     -- e.g. 'Municipal Hall parcel + estate compensation → Atty. Botor'
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT drip_no_invented_period CHECK (due_at IS NULL OR (served_at IS NOT NULL AND clock_rule IS NOT NULL)),
  CONSTRAINT drip_dedup UNIQUE (matter_code, officer, instrument_ref)
);

CREATE TABLE IF NOT EXISTS drip_edition (
  id               BIGSERIAL PRIMARY KEY,
  track            TEXT NOT NULL,            -- 'DILG-supervision', ...
  matter_code      TEXT NOT NULL,
  instrument_ref   TEXT NOT NULL,
  edition_date     DATE NOT NULL,
  next_edition_due DATE,
  counters         JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {row_label: anchor_date} — days recompute per edition
  state            TEXT NOT NULL DEFAULT 'cleared_pending_service',
  notes            TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT drip_edition_dedup UNIQUE (track, edition_date)
);

CREATE TABLE IF NOT EXISTS drip_event (       -- APPEND-ONLY audit (A39)
  id          BIGSERIAL PRIMARY KEY,
  kind        TEXT NOT NULL,                  -- tick | lapse | stage_consequence | edition_drafted | reply_recorded | state_change
  obligation_id BIGINT,
  edition_id  BIGINT,
  detail      JSONB,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION drip_append_only() RETURNS trigger AS $fn$
BEGIN
  RAISE EXCEPTION 'append-only ledger: % on drip_event is forbidden', TG_OP;
END; $fn$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_drip_event_append_only ON drip_event;
CREATE TRIGGER trg_drip_event_append_only BEFORE UPDATE OR DELETE ON drip_event
  FOR EACH ROW EXECUTE FUNCTION drip_append_only();

-- ── SEEDS — the live September ledger (states honored EXACTLY; nothing served yet ⇒ no clock runs) ──
INSERT INTO office_obligation
  (matter_code, officer, office, obligation, instrument_ref, clock_rule, state, consequence_ref, counsel_gate, excluded_scope, notes)
VALUES
  ('MWK-001','Mayor Pajarillo','Office of the Mayor, Mercedes',
   '(1) institute §444(b)(1)(x) proceedings re Teope/Balane or state justification; (2) withdraw all-heirs SPA or cite its enactment',
   'case_work/MWK-001: DEMAND_Mayor_444b1x_SPA',
   'RA 3019 §3(f) due demand; instrument D+15 from receipt',
   'draft_held',
   'Ombudsman supplemental affidavit (rides open OAC-L 270 referral; elective → OMB)',
   'NEEDS-COUNSEL at trigger',
   'Municipal Hall parcel + estate compensation → Atty. Botor',
   'Master instrument 05-Sep absorbs Abla/Mayor items at Jonathan''s call at service time'),
  ('MWK-001','Mayor Pajarillo','Office of the Mayor, Mercedes',
   '§444(b)(3)(vi) duty: (1) certified list of permits on the scheduled parcels; (2) issue the requirement to each unpermitted-structure owner; (3) order demolition/removal where neither permit nor instrument of right exists — starting with the Teope structure',
   'case_work/MWK-001: DEMAND_Mayor_Demolition_444b3vi',
   'PD 1096 §§301–302 + LGC §444(b)(3)(vi); RA 3019 §3(f) due demand; instrument D+15 from receipt',
   'draft_held',
   'Same Ombudsman supplement: §3(f) favoring-own-interest + §3(e) unwarranted benefit. ENCL REQUIRED AT SERVICE: Schedule of Declared Parcels (ESTATE_DECLARED_PARCELS_2026-09)',
   'NEEDS-COUNSEL at trigger',
   'Municipal Hall parcel + estate compensation → Atty. Botor',
   'THE HEAVY CLOCK. One duty, three numbered sub-items — stays ONE letter per the splitting rule'),
  ('MWK-001','Abla','Municipal Assessor, Mercedes',
   'Render the chartered service paid 20 Jun 2025 (O.R. 7383466) in full, or record-specific written disposition',
   'case_work/MWK-001: DEMAND_Abla_CharteredService',
   'RA 3019 §3(f) due demand; instrument D+15 from receipt',
   'draft_held',
   'CSC-RO V verified complaint (CSC_COMPLAINT_ABLA_draft — serious dishonesty + refusal counts)',
   'NEEDS-COUNSEL at trigger', NULL, NULL),
  ('MWK-001','Macale','Municipal Treasurer, Mercedes',
   '§252 lapse notice — elects §252(d)/LBAA remedies, preserves BLGF tracks + claims (a notice, not a demand)',
   'case_work/MWK-001: NOTICE_Macale_252Lapse',
   'LGC §252(d)/§226 — LBAA appeal window runs from the lapse',
   'draft_held',
   'LBAA appeal (counsel); Art. 27/§3(f) already preserved in ¶4(e)',
   'NEEDS-COUNSEL at trigger', NULL,
   'Fire on/after 6 Sep; confirm no decision arrived 5 Sep; service not yet recorded'),
  ('MWK-001','Teope','Assistant to the Mayor',
   'Per DEMAND_TEOPE_FINAL_2026-08-26',
   'case_work/MWK-001: DEMAND_TEOPE_FINAL_2026-08-26',
   'RA 3019 §3(f) due demand; instrument D+15 from receipt',
   'draft_held',
   'Ombudsman referral already live (1212, §3(i))',
   'NEEDS-COUNSEL at trigger', NULL,
   'VERIFY whether already served (other desk) before recording service'),
  ('MWK-001','Olaguera','SB Secretary, Mercedes',
   'Fee assessment + requirements; release/inspection incl. members'' manifestations; per-session adoption status; enactment number',
   'case_work/MWK-001: DEMAND_Olaguera_FinalDemand_469c — NOT FOR SERVICE',
   NULL,
   'withdrawn',
   NULL,
   'HELD for counsel reassessment', NULL,
   'WITHDRAWN 08-Sep: no 5-Sep acceptance/tender occurred; no clock, no automatic CSC trigger; any future period needs a separately authorized request + proof of receipt'),
  ('MWK-001','Engr. Balane','Municipal Building Official, Mercedes',
   'Building-official duty re the unpermitted Teope structure (NOT BUILT)',
   '(none — not built)',
   NULL,
   'held_counsel_route',
   NULL,
   'Atty. Barandon ONLY — CV 26-360 defendant', NULL,
   'HOLD: any demand to him routes through Barandon first; this row exists so the hold is visible, it can never tick')
ON CONFLICT ON CONSTRAINT drip_dedup DO NOTHING;

-- Edition track: the DILG Reiteration (counters = anchor dates DERIVED from the 10-Sep letter's own
-- day-counts; 'MWK Street' anchor 2025-05-22 independently matches doc 302 first written notice.
-- VERIFY each anchor against the letter at next edition build — derived, not yet letter-quoted.)
INSERT INTO drip_edition (track, matter_code, instrument_ref, edition_date, next_edition_due, counters, state, notes)
VALUES ('DILG-supervision','MWK-001',
        'case_work/MWK-001: MWK-001_REITERATION_MLGOO_MayorDefault_Sep2026 (DOCX+PDF)',
        '2026-09-10','2026-09-25',
        '{"Donation instrument production (demand)":"2026-08-26",
          "Donation instrument production (first notice)":"2026-07-24",
          "§444(b)(1)(x) proceedings":"2026-06-24",
          "All-heirs SPA withdrawal":"2026-01-26",
          "MWK Street / Road Lot 6":"2025-05-22",
          "Records production (original ask)":"2026-02-11",
          "Records production (renewed)":"2026-08-25",
          "Enactment number":"2026-09-01"}'::jsonb,
        'cleared_pending_service',
        'FINAL, cleared by Jonathan; NOT served — no clock until receipt. To MLGOO Guerrero, cc PD Relucio + RD Escober. Next edition ~25 Sep: same schedule, counters advanced, PERFORMED rows marked; persistent default supports elevation to the Provincial Director per the letter''s own terms')
ON CONFLICT ON CONSTRAINT drip_edition_dedup DO NOTHING;

COMMIT;
