-- deploy_1317: officer task list (staff_task) — errands that are not drip letters.
-- Product interview 2026-11-03: "this should be a live corpus, every piece of information should create a
-- ripple throughout the corpus, so all pertinent info goes to the proper table." Kristyle's real work came in
-- Jonathan's email of 2 Nov 2026 (gmail_messages #152157) and lived nowhere the bot could read; readiness
-- failed because of it. Every row carries its source; every due date carries the basis it was taken from.
-- Idempotent.

CREATE TABLE IF NOT EXISTS staff_task (
    id            bigserial   PRIMARY KEY,
    assignee      text        NOT NULL,                 -- staff_desk_members.assignee_key
    matter_code   text        NOT NULL,
    seq           integer     NOT NULL DEFAULT 0,       -- order within the source's list
    title         text        NOT NULL,                 -- what to do, one line
    how           text,                                 -- where to go / how, from the source
    proof_needed  text,                                 -- what to send back
    due_date      date,
    due_basis     text,                                 -- where the date comes from (never invented)
    state         text        NOT NULL DEFAULT 'open'
                  CHECK (state IN ('open', 'done_awaiting_check', 'done', 'cancelled')),
    proof_doc_id  integer,
    source_ref    text        NOT NULL,                 -- e.g. 'gmail_messages:152157'
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_ref, seq)
);

ALTER TABLE approval_asks DROP CONSTRAINT IF EXISTS approval_asks_kind_check;
ALTER TABLE approval_asks ADD CONSTRAINT approval_asks_kind_check
    CHECK (kind IN ('service_proof', 'task_assign', 'staff_task_done'));

-- Kristyle's tasks from Jonathan's email of 2 Nov 2026 23:29 UTC (gmail_messages #152157,
-- case_work/LandTek-Corp/KRISTYLE_TASKS_EMAIL_2026-11-02_DRAFT.txt). "This week" = by Sun 8 Nov 2026.
INSERT INTO staff_task (assignee, matter_code, seq, title, how, proof_needed, due_date, due_basis, source_ref) VALUES
('kristyle', 'LANDTEK-OPC-FORMATION', 1,
 'Fix the fiscal year with SEC (should be 1 January to 31 December)',
 'SEC ESPARC (esparc.sec.gov.ph): look for a Petition for Correction. If none, sign and date letter 01_SEC_FISCAL_YEAR_CORRECTION_REQUEST and email it with the Certificate, Articles and application summary to cprd_registration@sec.gov.ph, copying Jonathan. Do this before BIR.',
 'SEC''s reply on the correction', '2026-11-08', 'Jonathan''s 2 Nov email: "This week: fix the fiscal year (step 2)"', 'gmail_messages:152157'),
('kristyle', 'LANDTEK-OPC-FORMATION', 2,
 'Get the corporate TIN, then register with BIR (Form 1903)',
 'Philippine Business Hub (business.gov.ph) via the link in the SEC approval email for the TIN; then BIR ORUS (orus.bir.gov.ph), non-individual, Form 1903, answers from data sheet 04. Upload Certificate, Articles, ID, selfie with ID; pay DST online. Ask which RDO covers Bagasbas.',
 'The corporate TIN, then the BIR Form 2303', '2026-11-08', 'Jonathan''s 2 Nov email: "This week: ... start the TIN and BIR registration (step 3)" (start date, not completion)', 'gmail_messages:152157'),
('kristyle', 'LANDTEK-OPC-FORMATION', 3,
 'Ask Bagasbas Barangay Hall and Daet BPLO for their requirement lists',
 'Barangay clearance at Bagasbas Barangay Hall; new business permit at the BPLO, Daet Municipal Hall. Ask for the complete lists so you only go back once.',
 'Photos of both requirement lists', '2026-11-08', 'Jonathan''s 2 Nov email: "This week: ... ask the barangay and BPLO for their lists (step 4)"', 'gmail_messages:152157'),
('kristyle', 'LANDTEK-OPC-FORMATION', 4,
 'Call Landbank Daet about the corporate account',
 'Daet Branch or Daet F. Pimentel Branch. Ask for their corporate-account checklist and own forms (board resolution, Secretary''s Certificate), minimum balances for current and savings, and whether they open with the TIN only.',
 'The bank''s checklist', '2026-11-08', 'Jonathan''s 2 Nov email: "This week: ... call Landbank (step 5)"', 'gmail_messages:152157'),
('kristyle', 'LANDTEK-OPC-FORMATION', 5,
 'Ask Allan to confirm his address for the officer form',
 'The form uses AVI Compound Gambrille, Bagasbas Road Purok 3. Ask Allan if that is right before anyone signs.',
 'Allan''s confirmation', '2026-11-17', 'Needed before the FAO is signed; FAO deadline 17 Nov (Jonathan''s 2 Nov email, step 1)', 'gmail_messages:152157'),
('kristyle', 'LANDTEK-OPC-FORMATION', 6,
 'File the officer form (FAO) in SEC eFAST',
 'Fill by hand: gender, appointment dates, TIN if available, fiscal year line. Kristine signs as nominee, Allan as alternate, you sign both pages as President; notarize if asked. Upload at efast.sec.gov.ph. Late filing fine P10,000.',
 'The filed FAO and the eFAST acknowledgment', '2026-11-17', 'Jonathan''s 2 Nov email: "By 17 November 2026: officer form (FAO) filed in eFAST (step 1)"', 'gmail_messages:152157'),
('kristyle', 'LANDTEK-OPC-FORMATION', 7,
 'Tell Jonathan who owns the office premises (Purok 3 Bagasbas Road)',
 'Needed for the lease or consent letter that the barangay clearance requires.',
 'The owner''s name', NULL, 'No date in Jonathan''s 2 Nov email; needed for the barangay clearance (step 4)', 'gmail_messages:152157')
ON CONFLICT (source_ref, seq) DO NOTHING;
