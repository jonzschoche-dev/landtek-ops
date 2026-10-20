-- Drip PRE-DRAFT GATE data (Jonathan, 20 Oct 2026: "line it up better so our answers are not so sporadic").
-- Substance checks become DATA, not recall: who holds what (custodian map), which legal premises are verified against the
-- law corpus (legal_premise → legal_chunks), and the canonical facts per matter (drip_fact). Additive.
BEGIN;

CREATE TABLE IF NOT EXISTS drip_custodian (
    record_type     text PRIMARY KEY,               -- what is being asked for
    custodian       text NOT NULL,                  -- the office that keeps / decides it
    level           text NOT NULL,                  -- municipal | provincial | regional | national | court | bank
    alternate       text,                           -- who else holds a copy (route here when the custodian is a respondent, X17)
    basis           text NOT NULL,                  -- statute (legal_premise id) or record (doc/gmail id) or Jonathan's ruling
    verified        boolean NOT NULL DEFAULT false, -- true only when the basis is a statute chunk or a document
    notes           text
);
INSERT INTO drip_custodian VALUES
 ('rpt_protest_252','Provincial Treasurer (municipality outside Metro Manila)','provincial',NULL,'LGC §252(a), legal_chunks 2353: protest "to the provincial, city treasurer or municipal treasurer, in the case of a municipality within Metropolitan Manila Area"',true,'Payment first; protest within 30 days of payment; decided within 60 days'),
 ('rpt_refund_253','Provincial Treasurer','provincial',NULL,'LGC §253, legal_chunks 2354',true,'Refund/credit of taxes AND interest within 2 years of the adjustment; decided within 60 days'),
 ('assessment_appeal','Local Board of Assessment Appeals (provincial)','provincial',NULL,'LGC §226, legal_chunks 2343',true,'Appeal from the ASSESSOR''s assessment, within 60 days of the written notice of assessment'),
 ('declaration_of_improvements','Municipal Assessor','municipal','Subpoena duces tecum via the court (when the Municipal Assessor is a respondent)','Jonathan ruling 20 Oct 2026 (drip_feedback); municipal assessor keeps the declarations',false,'Provincial Assessor does NOT handle improvements'),
 ('land_declaration_history','Municipal Assessor','municipal','Provincial Assessor (certified copies of provincial records: doc 411, doc 115)','doc 411 (Magana certified ARP 00256); doc 115 (Brgy 5 ledger)',true,NULL),
 ('tax_map','Municipal Assessor','municipal','Provincial Assessor (tax-mapping division; his 13 Jul 2026 referral, gmail 19f5a08deae0fdbc)','Magana e-mails 1 and 13 Jul 2026',true,NULL),
 ('rpt_bill_and_receipts','Municipal Treasurer','municipal',NULL,'doc 1616 (2026 assessment); ORs 0434682-84',true,NULL),
 ('building_permit','Municipal Building Official (Office of the Municipal Engineer)','municipal','Mayor (supervision) / counsel subpoena: the MBO is a CV 26-360 defendant','PD 1096 §301 (not yet in legal_premise); doc 837',false,NULL),
 ('sb_records','Secretary to the Sangguniang Bayan','municipal',NULL,'LGC §469(c) (not yet in legal_premise); docs 765, gmail 96462',false,NULL),
 ('title_ctc_annotations','Registry of Deeds, Camarines Norte','provincial','LRA (e-copies)','docs 2539, 17',true,NULL),
 ('notarial_records','Clerk of Court & Ex-Officio Sheriff, RTC Daet (notarial section)','court',NULL,'2004 Rules on Notarial Practice (not yet in legal_premise)',false,NULL),
 ('court_orders_case','Branch Clerk of Court of the branch hearing the case','court','Office of the Clerk of Court','docs 575, 1035 (OCC stamp)',true,NULL),
 ('just_compensation_payment_status','Land Bank FSSC V, Legazpi','bank',NULL,'gmail 31 (FSSC5 reply 11 Jul 2025)',true,NULL),
 ('survey_plans','DENR Region V Surveys & Mapping (regional Psd); LRA (LRC/LRA plans)','regional',NULL,'DENR-TS-OSS-2026-1092 (doc 14192); 00_PLAN_REGISTER',true,NULL),
 ('death_record','Local Civil Registrar of the place of death','municipal','PSA','—',false,NULL)
ON CONFLICT (record_type) DO NOTHING;

CREATE TABLE IF NOT EXISTS legal_premise (
    id            bigserial PRIMARY KEY,
    key           text UNIQUE NOT NULL,
    statement     text NOT NULL,                 -- the premise, in one line
    legal_chunk_id integer,                      -- legal_chunks.id holding the text
    excerpt       text,                          -- verbatim words relied on
    verified      boolean NOT NULL DEFAULT false,
    verified_at   timestamptz
);
INSERT INTO legal_premise (key, statement, legal_chunk_id, excerpt, verified, verified_at) VALUES
 ('LGC252a','RPT protest: pay first; written protest within 30 days of payment to the provincial treasurer (outside Metro Manila); decided within 60 days',2353,'No protest shall be entertained unless the taxpayer first pays the tax … within thirty (30) days from payment of the tax to the provincial, city treasurer … who shall decide the protest within sixty (60) days from receipt.',true,now()),
 ('LGC252d','Denial or lapse of the 60 days opens the Chapter 3 remedies',2353,'In the event that the protest is denied or upon the lapse of the sixty day period … the taxpayer may avail of the remedies as provided for in Chapter 3, Title II, Book II',true,now()),
 ('LGC253','Refund/credit of taxes and interest within 2 years of the adjustment; provincial treasurer decides within 60 days',2354,'… may file a written claim for refund or credit for taxes and interests with the provincial or city treasurer within two (2) years from the date the taxpayer is entitled to such reduction or adjustment.',true,now()),
 ('LGC226','LBAA hears appeals from the ASSESSOR''s assessment, within 60 days of the written notice of assessment',2343,'… not satisfied with the action of the provincial, city or municipal assessor in the assessment of his property may, within sixty (60) days from the date of receipt of the written notice of assessment, appeal …',true,now()),
 ('LGC234a','Property OWNED by the government is exempt (not privately-owned land it occupies)',2348,'Real property owned by the Republic of the Philippines or any of its political subdivisions except when the beneficial use thereof has been granted … to a taxable person',true,now()),
 ('RA6713_5a','Officials reply to letters within 15 working days of receipt, stating the action taken',133,'within fifteen (15) working days from receipt thereof, respond to letters … The reply must contain the action taken',true,now()),
 ('ROC39_6','Execution by motion within 5 years of entry of judgment; after that, by action within the prescriptive period',3885,'… may be executed on motion within five (5) years from the date of its entry …',false,NULL)
ON CONFLICT (key) DO NOTHING;

CREATE TABLE IF NOT EXISTS drip_fact (
    id          bigserial PRIMARY KEY,
    matter_code text NOT NULL,
    key         text NOT NULL,
    value       text NOT NULL,
    source      text NOT NULL,                 -- doc / gmail id; no source, no fact
    as_of       date,
    UNIQUE (matter_code, key)
);
INSERT INTO drip_fact (matter_code, key, value, source, as_of) VALUES
 ('MWK-001','rpt2026.arp_count','22 ARPs billed for CY 2026 (29 parcels in the heirs'' names in the corpus schedule)','doc 1616; ESTATE_DECLARED_PARCELS_2026-09.md','2026-04-30'),
 ('MWK-001','rpt2026.total','₱198,646.78 (2026, 22 ARPs)','doc 1616','2026-04-30'),
 ('MWK-001','rpt2026.paid_advance','₱30,640.08 (ARP 003-00256)','doc 1616','2026-04-30'),
 ('MWK-001','rpt2026.paid_dec2025','₱112,496.64 (December 2025; tendered under protest per e-mails of 20 and 29 Dec 2025 to MT Macale)','doc 1616; gmail 4288, 4289, 4284','2025-12-31'),
 ('MWK-001','rpt2026.paid_apr2026','₱41,118.56 (wired ₱41,119.00 on 5 Apr, credited 7 Apr; ORs 0434682-84 issued 7 Jul 2026 annotated paid under protest)','doc 1616; gmail 102528, 95599','2026-07-07'),
 ('MWK-001','rpt2026.balance_claimed','₱14,391.50 = ₱10,279.64 discount removed + ₱4,111.86 interest, all placed on ARP 001-00249; UNPAID','doc 1616; doc 2929; gmail 102528','2026-07-07'),
 ('MWK-001','rpt.arp_00249','ARP 001-00249 = PIN 025-07-001-01-004, 19,399 sq m, AV ₱1,932,140, 2026 tax ₱38,642.80; bounded by Road Lot 1','docs 1616, 1079, 51; ROAD_LOT_DONATION deep dive','2026-04-30'),
 ('MWK-001','rpt.protest_13jul','13 Jul 2026 letter to PT Manlapaz + BLGF R5 disputes the UNPAID ₱14,391.50; it is a supervisory request, not a §252 protest. No §252 clock is running.','doc 2929; legal_premise LGC252a','2026-10-20'),
 ('MWK-001','road_lots.area','8 road lots, 10,208 sq m, donated 14 Apr 1980 (perfected, unregistered except Road Lot 2); area never deducted from the heirs'' declarations','ROAD_LOT_DONATION_T32917_DEEP_DIVE_2026-09-09.md; memory project-road-lot-donation','2026-09-09'),
 ('MWK-001','compound.declaration','Lot 2-A / T-32911 carries no declaration in the heirs'' names; the Municipality declares 8,951 sq m in its own name (ARP …-005-00045, exempt)','ESTATE_DECLARED_PARCELS_2026-09.md; doc 151','2026-09-04')
ON CONFLICT (matter_code, key) DO NOTHING;

ALTER TABLE step_plan
  ADD COLUMN IF NOT EXISTS record_type   text REFERENCES drip_custodian(record_type),
  ADD COLUMN IF NOT EXISTS premise_keys  text[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS fact_keys     text[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS strategy_file text;

COMMIT;
