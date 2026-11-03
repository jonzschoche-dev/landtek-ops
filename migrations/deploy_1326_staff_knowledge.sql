-- deploy_1326: bot training for field officers = sourced knowledge cards + a nightly exam.
-- Jonathan, 3 Nov 2026: "we need to train our bot to be well informed on all the necessary subjects".
-- Not model fine-tuning (that bakes facts in with no source). Instead:
--   staff_knowledge  short answer cards, each tied to a source (Jonathan's email, a form, a law or an official
--                    page with the date it was checked). The staff desk answers only from these + task materials.
--   staff_exam       real officer questions with mechanical pass rules (must contain / must not contain / route).
--   staff_exam_run   every exam result. A topic's draft cards go live only when all its exam questions pass.
-- Unanswered questions (staff_question) answered by Jonathan on /ops/now become live cards + exam questions.
-- Idempotent.

CREATE TABLE IF NOT EXISTS staff_knowledge (
    id               bigserial   PRIMARY KEY,
    assignee         text,                                   -- NULL = every field officer
    matter_code      text        NOT NULL,
    topic            text        NOT NULL,
    card_key         text        NOT NULL,
    fact             text        NOT NULL,                   -- the answer, in plain words
    source_kind      text        NOT NULL CHECK (source_kind IN
                     ('jonathan_email', 'jonathan_said', 'form', 'law', 'official', 'secondary', 'computed')),
    source_ref       text        NOT NULL,                   -- gmail id, form name, law section or URL
    checked_on       date        NOT NULL,
    state            text        NOT NULL DEFAULT 'draft' CHECK (state IN ('draft', 'live', 'retired')),
    from_question_id bigint,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (matter_code, topic, card_key)
);

CREATE TABLE IF NOT EXISTS staff_exam (
    id           bigserial   PRIMARY KEY,
    assignee     text        NOT NULL,
    matter_code  text        NOT NULL,
    topic        text        NOT NULL,
    focus_seq    integer,                                    -- staff_task.seq in focus when she asks
    question     text        NOT NULL,
    expect       text        NOT NULL CHECK (expect IN ('answer', 'unknown', 'route')),
    must_all     text[]      NOT NULL DEFAULT '{}',          -- each item must match; 'a|b' = either
    must_not     text[]      NOT NULL DEFAULT '{}',
    unknown_ok   boolean     NOT NULL DEFAULT false,         -- an honest "not in the papers" also passes
    route_prefix text,                                       -- expect='route': staff_desk handler result prefix
    note         text,
    active       boolean     NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (assignee, focus_seq, question)
);

CREATE TABLE IF NOT EXISTS staff_exam_run (
    id          bigserial   PRIMARY KEY,
    run_id      text        NOT NULL,
    run_at      timestamptz NOT NULL DEFAULT now(),
    exam_id     bigint      NOT NULL REFERENCES staff_exam(id) ON DELETE CASCADE,
    passed      boolean,                                     -- NULL = skipped (model unreachable)
    handled     text,
    reply       text,
    why_failed  text
);
CREATE INDEX IF NOT EXISTS staff_exam_run_exam ON staff_exam_run (exam_id, run_at DESC);

ALTER TABLE staff_question ADD COLUMN IF NOT EXISTS answered_card_id bigint;

-- ── Cards: Kristyle's company-registration work (LANDTEK-OPC-FORMATION) ───────────────────────────────────
-- Facts already in Jonathan's 2 Nov email (gmail #152157) or form 04 are carded so they are available whatever
-- task is in focus. New facts carry their outside source. Every card starts as draft; the exam promotes it.
INSERT INTO staff_knowledge (assignee, matter_code, topic, card_key, fact, source_kind, source_ref, checked_on) VALUES
('kristyle', 'LANDTEK-OPC-FORMATION', 'company', 'identity',
 'Company: LANDTEK PROPERTY MANAGEMENT SOLUTIONS OPC, a One Person Corporation. SEC Company Reg. No. 2026110274328-35, Certificate of Incorporation issued 2 November 2026. Principal office: Purok 3 Bagasbas Road, Bagasbas, Daet, Camarines Norte 4600. Industry (PSIC): L682, real estate activities on a fee or contract basis.',
 'form', '04_BIR_ORUS_AND_DAET_PERMIT_DATA_SHEET (from the COI and Articles)', '2026-11-03'),
('kristyle', 'LANDTEK-OPC-FORMATION', 'company', 'people',
 'President and sole director: Kristyle Joy Palma Cerdon. Treasurer: Kristine Andaya Palado. Corporate Secretary: Allan Villafria Inocalla. Kristyle cannot be the Corporate Secretary because the law does not allow the sole stockholder to be the Secretary.',
 'jonathan_email', 'gmail_messages:152157 step 1 + data sheet 04', '2026-11-03'),
('kristyle', 'LANDTEK-OPC-FORMATION', 'company', 'capital',
 'Capital: authorized P100,000, subscribed P25,000, paid-up P25,000 in cash. The P25,000 paid-in capital can be the initial deposit at Landbank.',
 'form', 'data sheet 04 (Articles Seventh, Eighth) + gmail_messages:152157 step 5', '2026-11-03'),
('kristyle', 'LANDTEK-OPC-FORMATION', 'company', 'corporate_tin',
 'The company does not have a corporate TIN yet. It comes from the Philippine Business Hub (business.gov.ph) or BIR. The TIN 506-955-144-000 is Kristyle''s own personal TIN, not the company''s; never write it as the company TIN.',
 'form', 'data sheet 04 ("Corporate TIN: From PBH / BIR"; Kristyle TIN under Articles Fifth)', '2026-11-03'),
('kristyle', 'LANDTEK-OPC-FORMATION', 'company', 'can_cannot',
 'Right now the company legally exists and can spend money and sign contracts through Kristyle as President. It cannot issue official invoices or bill anyone until BIR registration is done (Form 2303 and registered invoices). It should not open an office to the public until the barangay clearance and mayor''s permit are issued.',
 'jonathan_email', 'gmail_messages:152157 "What the company can and cannot do right now"', '2026-11-03'),
('kristyle', 'LANDTEK-OPC-FORMATION', 'receipts', 'receipts',
 'For every company cost (SEC fees, notary, printing, transport, permits) ask for the official receipt or invoice in the company''s name: "LandTek Property Management Solutions OPC, Purok 3 Bagasbas Road, Bagasbas, Daet, Camarines Norte". Add the corporate TIN once there is one. Log each one: date, what, amount, who paid. Without receipts in the company''s name BIR will not allow the expense.',
 'jonathan_email', 'gmail_messages:152157 step 6', '2026-11-03'),
('kristyle', 'LANDTEK-OPC-FORMATION', 'receipts', 'copies',
 'Forward Jonathan every email from SEC, BIR and the bank, and keep scans of everything you sign or receive. Until the management agreement and system license are signed, hold any new field work in the company''s name.',
 'jonathan_email', 'gmail_messages:152157 steps 7 and 8', '2026-11-03'),
('kristyle', 'LANDTEK-OPC-FORMATION', 'bir', 'rdo',
 'BIR Revenue District Office No. 64 moved from Daet to Talisay and is now "RDO No. 64-Talisay, Camarines Norte", BIR Building, Maharlika Hi-way, Talisay, Camarines Norte (Revenue Administrative Order No. 001-16, 6 June 2016). Listings show RDO 64-Talisay covers Daet, so Bagasbas should fall under RDO 64; confirm it on the ORUS screen or with BIR.',
 'official', 'RAO No. 001-16 (6 Jun 2016) via digest.ph; Daet coverage per zonal-value listings (secondary)', '2026-11-03'),
('kristyle', 'LANDTEK-OPC-FORMATION', 'bir', 'registration_fee',
 'There is no more P500 annual registration fee at BIR. The Ease of Paying Taxes Act (Republic Act No. 11976) stopped it from 22 January 2024, for new and existing businesses.',
 'secondary', 'RA 11976 (EOPT Act), as summarized in RMC No. 91-2024 commentary (batasnatin.com, respicio.ph)', '2026-11-03'),
('kristyle', 'LANDTEK-OPC-FORMATION', 'bir', 'dst',
 'The documentary stamp tax (DST) on the original issue of shares is P2.00 for every P200 of par value (1%), under Section 174 of the Tax Code as amended by the TRAIN law. On the P25,000 subscribed that works out to about P250 (25,000 / 200 x 2). It is paid with BIR Form 2000-OT; ORUS shows the exact amount when it asks for payment, and that screen controls.',
 'law', 'NIRC Sec. 174 as amended by RA 10963 (TRAIN); computed on P25,000 subscribed from data sheet 04', '2026-11-03'),
('kristyle', 'LANDTEK-OPC-FORMATION', 'bir', 'steps',
 'BIR order: first the corporate TIN through the Philippine Business Hub (business.gov.ph) using the link in the SEC approval email; then register in ORUS (orus.bir.gov.ph) as a non-individual, BIR Form 1903, copying answers from data sheet 04. Uploads: SEC Certificate of Incorporation, Articles of Incorporation, Kristyle''s valid ID, a selfie holding the ID, and proof of office address. BIR then issues the Certificate of Registration, Form 2303; send Jonathan a copy. Ask BIR about books of account and invoices. Do Task 1 (fiscal year correction) before this.',
 'jonathan_email', 'gmail_messages:152157 steps 2-3 + data sheet 04', '2026-11-03'),
('kristyle', 'LANDTEK-OPC-FORMATION', 'fao', 'deadline',
 'The officer form (FAO, "Form for Appointment for One Person Corporation", Annex A of SEC Memorandum Circular No. 10, series of 2026) is filed in SEC eFAST (efast.sec.gov.ph). Our target is 17 November 2026: the Certificate and Articles say 15 days from 2 November. The circular says 20 days (22 November). Missing the first filing carries a one-time P10,000 fine.',
 'jonathan_email', 'gmail_messages:152157 step 1; P10,000 one-time initial-filing penalty per MC 10 s.2026 summaries (ndvlaw.com, gmanetwork.com)', '2026-11-03'),
('kristyle', 'LANDTEK-OPC-FORMATION', 'fao', 'signing',
 'On the FAO: Kristine Andaya Palado signs as nominee, Allan Villafria Inocalla as alternate nominee, and Kristyle signs both pages as President. The form has a notarization part, so have it notarized before uploading if eFAST asks. Fill by hand: gender, dates of appointment of the Treasurer and Corporate Secretary, the corporate TIN if available, and the fiscal year line (blank until SEC corrects it, or 1 JANUARY - 31 DECEMBER if SEC says so). Allan''s address on the form is AVI Compound Gambrille, Bagasbas Road Purok 3; ask Allan to confirm it before anyone signs.',
 'jonathan_email', 'gmail_messages:152157 step 1; notarization part per Grant Thornton summary of MC 10 s.2026 Annex A', '2026-11-03'),
('kristyle', 'LANDTEK-OPC-FORMATION', 'fao', 'bond',
 'No surety bond is needed for LandTek. Under Section 122 of the Revised Corporation Code a bond is required only when the sole stockholder appoints herself Treasurer. LandTek''s Treasurer is Kristine Andaya Palado, not Kristyle.',
 'law', 'RA 11232 Sec. 122 (as summarized by ndvlaw.com, pnl-law.com); Treasurer per data sheet 04', '2026-11-03'),
('kristyle', 'LANDTEK-OPC-FORMATION', 'sec_fy', 'how',
 'Fiscal year correction: the Articles (Twelfth article) wrongly say the fiscal year runs 31 December to 30 December; it should be 1 January to 31 December. Log in to SEC ESPARC (esparc.sec.gov.ph), open the LandTek application and look for a "Petition for Correction" option. If there is none, sign and date letter 01_SEC_FISCAL_YEAR_CORRECTION_REQUEST and email it with the Certificate of Incorporation, the Articles and the application summary to cprd_registration@sec.gov.ph, copying Jonathan. Do it before BIR so BIR records the right year.',
 'jonathan_email', 'gmail_messages:152157 step 2', '2026-11-03'),
('kristyle', 'LANDTEK-OPC-FORMATION', 'lgu', 'permits',
 'Barangay clearance: Bagasbas Barangay Hall; bring the SEC Certificate of Incorporation, the Articles, Kristyle''s ID and proof of the office address (a lease or consent letter from the owner of the premises). Mayor''s permit: Business Permits and Licensing Office (BPLO) at the Daet Municipal Hall; ask for the new business permit form and their complete list. They usually ask for the barangay clearance, SEC papers, the lease or consent letter, a community tax certificate (cedula) for the company, and later a fire safety inspection.',
 'jonathan_email', 'gmail_messages:152157 step 4', '2026-11-03'),
('kristyle', 'LANDTEK-OPC-FORMATION', 'lgu', 'premises',
 'Jonathan needs the name of the owner of the office premises at Purok 3 Bagasbas Road so he can prepare the short lease or consent letter that the barangay clearance requires.',
 'jonathan_email', 'gmail_messages:152157 step 4', '2026-11-03'),
('kristyle', 'LANDTEK-OPC-FORMATION', 'landbank', 'account',
 'Landbank has two Daet branches: "Daet Branch" and "Daet F. Pimentel Branch"; pick the easier one. Ask them for their corporate-account checklist and their own forms for the board resolution and Secretary''s Certificate, the minimum balance for current and savings accounts, and whether they open with the corporate TIN only. The minimum balance is not in our papers; ask the branch. We open two accounts: one for operations and a separate one for client money only. Kristyle is the only signatory on both; bring two valid IDs and her TIN. Forms 02 (resolution, signed by Kristyle) and 03 (Secretary''s Certificate, signed by Allan before a notary) are attached to the email.',
 'jonathan_email', 'gmail_messages:152157 step 5', '2026-11-03')
ON CONFLICT (matter_code, topic, card_key) DO NOTHING;

-- ── Exam: real questions (Kristyle's own of 3 Nov first) + the ones an officer asks next ───────────────────
INSERT INTO staff_exam (assignee, matter_code, topic, focus_seq, question, expect, must_all, must_not, unknown_ok, route_prefix, note) VALUES
-- her actual questions, 3 Nov
('kristyle','LANDTEK-OPC-FORMATION','sec_fy',1,'Why is it necessary?','route','{"31 December"}','{}',false,'why','Kristyle 3 Nov, got "No typed stack hit"'),
('kristyle','LANDTEK-OPC-FORMATION','sec_fy',1,'Let''s pass on that , let''s go to the second task','route','{"Task 2"}','{}',false,'goto','Kristyle 3 Nov, got the dead-end line'),
('kristyle','LANDTEK-OPC-FORMATION','sec_fy',1,'What is the subject for email?','answer','{"Article Twelfth"}','{}',false,NULL,'Kristyle 3 Nov'),
('kristyle','LANDTEK-OPC-FORMATION','relay',1,'Check it for me','route','{}','{}',false,'relay','Kristyle 3 Nov'),
('kristyle','LANDTEK-OPC-FORMATION','relay',1,'Notify Jonathan to check','route','{}','{}',false,'relay','Kristyle 3 Nov'),
-- company
('kristyle','LANDTEK-OPC-FORMATION','company',1,'What is the company registration number?','answer','{"2026110274328-35"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','company',3,'Ano ang exact name ng company para sa resibo?','answer','{"Property Management Solutions OPC"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','company',2,'What address do I put for the company?','answer','{"Purok 3","Bagasbas"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','company',4,'Magkano ang paid-up capital?','answer','{"25,000|25000"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','company',6,'Who is the treasurer?','answer','{"Kristine"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','company',6,'Pwede ba ako maging corporate secretary?','answer','{"hindi|not|cannot|can''t|bawal"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','company',1,'Can the company bill clients now?','answer','{"2303|invoice"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','company',2,'Ano ang TIN ng company?','answer','{"Business Hub|PBH|BIR|wala pa|not yet|hindi pa"}','{"506-955-144"}',true,NULL,'trap: her personal TIN is on the data sheet'),
('kristyle','LANDTEK-OPC-FORMATION','receipts',2,'What should be written on the receipts?','answer','{"Property Management Solutions OPC"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','receipts',3,'Kailangan ko ba itago ang resibo ng pamasahe?','answer','{"receipt|resibo"}','{}',false,NULL,NULL),
-- SEC fiscal year (task 1)
('kristyle','LANDTEK-OPC-FORMATION','sec_fy',1,'Saan ko ise-send ang email?','answer','{"cprd_registration@sec.gov.ph"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','sec_fy',1,'What do I attach to the email?','answer','{"Certificate","Articles"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','sec_fy',1,'Should I copy Jonathan on the email?','answer','{"Jonathan"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','sec_fy',1,'Where do I look for the petition for correction?','answer','{"ESPARC|esparc"}','{}',false,NULL,'"petition" must not trigger the case branch'),
('kristyle','LANDTEK-OPC-FORMATION','sec_fy',1,'What if SEC does not reply within a week?','unknown','{}','{}',false,NULL,'not in any source'),
('kristyle','LANDTEK-OPC-FORMATION','sec_fy',1,'Magkano ang bayad sa SEC para sa correction?','unknown','{}','{}',false,NULL,'not in any source'),
-- BIR (task 2)
('kristyle','LANDTEK-OPC-FORMATION','bir',2,'Which RDO covers Bagasbas?','answer','{"64","Talisay"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','bir',2,'Saan ang BIR office?','answer','{"Talisay"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','bir',2,'Magkano ang registration fee sa BIR?','answer','{"500","11976|wala na|no more|no longer|hindi na|abolish|stopped|tinanggal"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','bir',2,'How much is the documentary stamp tax?','answer','{"250|P2"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','bir',2,'What form do I use for BIR registration?','answer','{"1903"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','bir',2,'What do I upload in ORUS?','answer','{"selfie"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','bir',2,'Where do I get the corporate TIN?','answer','{"business.gov.ph|Business Hub"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','bir',2,'Pwede ko na bang unahin ang BIR bago ang fiscal year?','answer','{"Task 1|fiscal year|before|muna|bago"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','bir',2,'What PSIC code do I use?','answer','{"L682"}','{}',false,NULL,NULL),
-- barangay / BPLO (task 3)
('kristyle','LANDTEK-OPC-FORMATION','lgu',3,'Ano ang dadalhin ko sa barangay hall?','answer','{"Certificate","ID"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','lgu',3,'Where is the BPLO?','answer','{"Municipal Hall"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','lgu',3,'Kailangan ba ng cedula?','answer','{"cedula|community tax"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','lgu',3,'How much is the barangay clearance fee?','unknown','{}','{}',false,NULL,'not in any source'),
('kristyle','LANDTEK-OPC-FORMATION','lgu',7,'Why do you need the owner''s name?','route','{"lease|consent"}','{}',false,'why',NULL),
-- Landbank (task 4)
('kristyle','LANDTEK-OPC-FORMATION','landbank',4,'Which Landbank branch should I go to?','answer','{"Pimentel"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','landbank',4,'What is the minimum balance?','answer','{"ask|itanong|tanungin|alamin|branch"}','{}',true,NULL,'must not invent a number'),
('kristyle','LANDTEK-OPC-FORMATION','landbank',4,'Ilang account ang bubuksan natin?','answer','{"two|dalawa|2"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','landbank',4,'Who will be the signatory?','answer','{"Kristyle|you|ikaw|only signatory"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','landbank',4,'How much do I deposit when opening?','answer','{"25,000|25000"}','{}',false,NULL,NULL),
-- FAO (tasks 5-6)
('kristyle','LANDTEK-OPC-FORMATION','fao',6,'When is the deadline for the FAO?','answer','{"17"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','fao',6,'Magkano ang multa kung late?','answer','{"10,000|10000"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','fao',6,'Do we need a surety bond?','answer','{"Kristine|Treasurer|treasurer"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','fao',6,'Does the FAO need to be notarized?','answer','{"notar"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','fao',6,'Who signs the FAO?','answer','{"Kristine","Allan"}','{}',false,NULL,NULL),
('kristyle','LANDTEK-OPC-FORMATION','fao',5,'What is Allan''s address on the form?','answer','{"Gambrille|AVI Compound"}','{}',false,NULL,NULL),
-- must stay unknown
('kristyle','LANDTEK-OPC-FORMATION','guard',2,'What is Jonathan''s bank account number?','unknown','{}','{}',false,NULL,'never invent'),
('kristyle','LANDTEK-OPC-FORMATION','guard',1,'What is Allan''s mobile number?','unknown','{}','{}',false,NULL,'not in the sources')
ON CONFLICT (assignee, focus_seq, question) DO NOTHING;
