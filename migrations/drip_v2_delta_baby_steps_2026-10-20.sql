-- APPLIED 2026-10-20 on the VPS (Jonathan: 'program constant movement'); dry-run first; drip_event logged.
-- DRAFT DELTA (NOT APPLIED) — BABY STEPS: the sleep doctrine's path to the legal and financial goals (Jonathan, 20 Oct 2026:
-- "we need to baby step to our legal and financial goals"). On top of the live drip v2 fabric + sleep delta. Additive.
-- Each step is ONE routine ask that earns ONE record element a goal needs. Strategic instruments are the LAST step of a
-- ladder, reached only when the earlier elements are on record. Spec: agent_specs/005_drip.md "BABY-STEP LADDERS".
-- Dry run:  (sed '$d' this_file; echo ROLLBACK;) | docker exec -i n8n-postgres-1 psql -U n8n -d n8n -v ON_ERROR_STOP=1
BEGIN;

CREATE TABLE IF NOT EXISTS step_plan (
    id                   bigserial PRIMARY KEY,
    client_code          text NOT NULL,                       -- A5
    matter_code          text NOT NULL,
    serves_objective_id  integer REFERENCES matter_objectives(id),
    ladder               text NOT NULL,                       -- e.g. 'LGU-COMPOUND', 'MACALE-RPT', 'ABLA-SERVICE', 'CV6839-COLLECT'
    seq                  integer NOT NULL,
    step_kind            text NOT NULL CHECK (step_kind IN ('routine_ask','courtesy_edition','financial_act','strategic_rung')),
    addressee            text NOT NULL,
    the_ask              text NOT NULL,                       -- one small ask, in plain words (internal paraphrase)
    earns_element        text NOT NULL,                       -- the record element this step adds (receipt, an answer, an admission, silence)
    goal_element         text NOT NULL,                       -- what that element is FOR (legal / financial), internal only
    goal_kind            text NOT NULL CHECK (goal_kind IN ('legal','financial','both')),
    gate                 text NOT NULL,                       -- when it may go: 'after step N proven receipt + 15 working days' | 'Jonathan go' | ...
    if_answered          text,                                -- what we do with a reply
    if_silent            text,                                -- what silence earns, and the next step
    instrument_path      text,                                -- draft path once built
    obligation_id        bigint REFERENCES office_obligation(id),
    state                text NOT NULL DEFAULT 'planned' CHECK (state IN ('planned','drafted','approved','served','answered','silent','skipped','done')),
    history_ref          text,
    send_account         text CHECK (send_account IS NULL OR send_account IN ('jonzschoche@gmail.com','jonathan@hayuma.org','paper')),  -- the thread's origin account
    thread_ref           text,                                -- Gmail thread / message id to reply in; NULL only when no prior thread exists                                -- X16: the prior asks/answers/refusals this step was planned from (doc/gmail ids)
    notes                text,
    updated_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (ladder, seq),
    -- the sleep doctrine, structurally: a strategic rung is never the first step of a ladder
    CHECK (step_kind <> 'strategic_rung' OR seq > 1)
);

-- The next baby step per ladder: the lowest step not yet served/done/skipped. The pick (Stage 5) reads this.
CREATE OR REPLACE VIEW v_next_baby_step AS
SELECT DISTINCT ON (ladder) client_code, matter_code, ladder, seq, step_kind, addressee, the_ask, earns_element,
       goal_element, goal_kind, gate, state, instrument_path
  FROM step_plan
 WHERE state IN ('planned','drafted','approved')
 ORDER BY ladder, seq;

COMMENT ON TABLE step_plan IS
  'INTERNAL. Baby-step ladders: each routine ask earns one record element toward a legal/financial goal. goal_element never renders outward (internal_goal_leak).';

-- Seed: four ladders (internal plan; every outward text still passes the sleep lint before it can be approved)
INSERT INTO step_plan (client_code, matter_code, serves_objective_id, ladder, seq, step_kind, addressee, the_ask, earns_element, goal_element, goal_kind, gate, if_answered, if_silent, instrument_path, notes) VALUES
-- LGU compound (rebuilt 20 Oct from the ask history: Mayor cited 1953 deed + Res. 21 + 1966 TD on 21 May 2025, doc 304; copies asked 23/28 May 2025, doc 343, never produced)
 ('MWK-001','MWK-LGU-RECOVERY',58,'LGU-COMPOUND',1,'routine_ask','Mayor Pajarillo','Only the identifying particulars of the three documents his 21 May 2025 letter cited (deed date + notary/doc-page-book; Res. 21 date + series; 1966 TD number), so we can get certified copies from the custodians ourselves','His own particulars on record — or none, which shows the cited documents cannot be identified','Legal: locks the asserted basis to checkable particulars (void/unregistered track); no-particulars = the basis is unsupported on his own file','legal','Jonathan go; serve after the 25 Oct DILG edition (stagger)','Request certified copies from each custodian (steps 2–4) using his particulars','Courtesy edition referring to this letter by date',
  'case_work/MWK-001/SCHEDULE_SERVICE_LGU_2026-10/01_Routine_Request_Mayor_Compound_Record.md','v2 drafted 20 Oct after Jonathan critique; sleep lint PASS'),
 ('MWK-001','MWK-LGU-RECOVERY',58,'LGU-COMPOUND',2,'routine_ask','Registrar of Deeds, Camarines Norte','A certification of the annotations on TCT No. T-32911 (or a certified copy), for the estate''s records','The RD''s own statement of what is (and is not) annotated','Legal: no donation annotated = no registered conveyance (registry record, not our assertion)','legal','any time (different office cluster); pairs with office_obligation #8','—','Courtesy edition',NULL,'Alternate custodian; no mention of the Mayor'),
 ('MWK-001','MWK-LGU-RECOVERY',58,'LGU-COMPOUND',3,'routine_ask','Provincial Assessor Magana','The assessment history of the municipal hall site (Lots 401/403/405), including any 1966 declaration, for the estate''s records','The Province''s record of whether a 1966 declaration exists','Legal: tests the 1966 TD claim at the supervising office (he has produced records before)','legal','after step 2 sent (stagger)','—','Courtesy edition',NULL,'Alternate custodian; warm ally'),
 ('MWK-001','MWK-LGU-RECOVERY',58,'LGU-COMPOUND',4,'routine_ask','Clerk of Court (notarial section), RTC Daet','A certified copy of the 1953 deed from the notarial records, using the particulars from step 1 (or a certification that none is found)','The notarial archive''s record','Legal: an archive certification of no such deed = decisive; a found copy is examined (signature/appearance)','legal','after step 1 particulars, or after step 1 silence + 15 working days (search by year)','—','Courtesy edition',NULL,NULL),
 ('MWK-001','MWK-LGU-RECOVERY',58,'LGU-COMPOUND',5,'strategic_rung','Mayor Pajarillo','The Schedule of Reasonable Compensation (₱59,521.00/mo on the LGU''s own declarations)','The DEMAND (Art. 1169): compensation starts accruing from receipt','Financial: the ₱59,521/mo stream begins; Legal: due demand for Art. 27 / §3(f)','both','Jonathan go ONLY; after steps 1–4 on record','Monthly calm statements','R1 to supervisor after 15 working days',
  'case_work/MWK-001/SCHEDULE_SERVICE_LGU_2026-10/HELD_LATER_RUNG/','Trade-off: each month before this step is ₱59,521 not claimable later')
-- (MACALE / ABLA / CV6839 seeds removed 20 Oct: replaced by the history-checked ladders in ops/drip/ladders/*.json, loaded by scripts/drip_draft_queue.py --load)
ON CONFLICT (ladder, seq) DO NOTHING;

COMMIT;
