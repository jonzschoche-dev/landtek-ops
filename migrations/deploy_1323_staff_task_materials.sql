-- deploy_1323: staff_task.materials + staff_question log.
-- Kristyle, 3 Nov: "What is the subject for email?" -- the bot could not answer though the record could.
-- materials = the task's own source text (Jonathan's 2 Nov email + the filled form attached to it for that step).
-- The staff desk answers free questions ONLY from materials (local model + mechanical token check); every
-- question and outcome is logged so unanswered ones surface. Idempotent.
ALTER TABLE staff_task ADD COLUMN IF NOT EXISTS materials text;
CREATE TABLE IF NOT EXISTS staff_question (
    id          bigserial PRIMARY KEY,
    assignee    text NOT NULL,
    task_id     bigint,
    question    text NOT NULL,
    answer      text,
    outcome     text NOT NULL CHECK (outcome IN ('answered', 'not_in_sources', 'rejected_unsupported', 'error')),
    detail      text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
UPDATE staff_task st SET materials = 'SOURCE: Jonathan''s email to Kristyle, 2 Nov 2026 (gmail #152157)' || E'\n' || g.body_plain
  FROM gmail_messages g WHERE g.id = 152157 AND st.source_ref = 'gmail_messages:152157' AND st.materials IS NULL;
UPDATE staff_task SET materials = materials || E'\n\nSOURCE: attached form 01_SEC_FISCAL_YEAR_CORRECTION_REQUEST.pdf\n' || $$____________________ 2026
COMPANY REGISTRATION AND MONITORING DEPARTMENT
Securities and Exchange Commission
The SEC Headquarters, 7907 Makati Avenue, Salcedo Village,
Barangay Bel-Air, Makati City 1209
Re: Request for correction of Article Twelfth (fiscal year), LANDTEK
PROPERTY MANAGEMENT SOLUTIONS OPC, SEC Company Reg. No.
2026110274328-35
Dear Sir/Madam:
LANDTEK PROPERTY MANAGEMENT SOLUTIONS OPC (the
"Corporation") was registered through ESPARC on 2 November 2026 under
Company Reg. No. 2026110274328-35, with principal office at Purok 3
Bagasbas Road, Bagasbas, Daet, Camarines Norte 4600.
Article Twelfth of the system-generated Articles of Incorporation reads: "That
the fiscal year of the OPC shall begin on the 31st day of December and shall end
on the 30th day of December of each year." The Registration Application Form
Summary likewise shows "December 31 - December 30". This is an encoding
error. The Corporation's intended fiscal year is the calendar year, consistent with
the reportorial requirements attached to its Certificate of Incorporation, which
state "Fiscal Year end: December 31".
Pursuant to paragraph 8 of the Corporation's Certificate of Authentication, which
provides that a defect may be cured by a Petition for Correction or an application
for amendment, the Corporation respectfully requests that Article Twelfth be
corrected to read:
"Twelfth: That the fiscal year of the OPC shall begin on the 1st day
of January and shall end on the 31st day of December of each year."
If the Commission requires this correction to be made through a different filing
or form, the Corporation asks to be informed so that it may comply promptly.
Notices may be sent to krstylpalma@gmail.com or kristyle.gip@gmail.com,
mobile 0926 531 6851.
Attached: (1) Certificate of Incorporation; (2) Articles of Incorporation; (3)
Registration Application Form Summary, Ref. No.
SEC261102-QMCWAVWVTGWWHQC.
Respectfully,
KRISTYLE JOY PALMA CERDON
Single Stockholder, Sole Director and President
LANDTEK PROPERTY MANAGEMENT SOLUTIONS OPC
TIN 506-955-144-000$$
 WHERE source_ref = 'gmail_messages:152157' AND seq = 1 AND materials NOT LIKE '%SOURCE: attached form 01_SEC_FISCAL_YEAR_CORRECTION_REQUEST.pdf%';
UPDATE staff_task SET materials = materials || E'\n\nSOURCE: attached form 04_BIR_ORUS_AND_DAET_PERMIT_DATA_SHEET.pdf\n' || $$DATA SHEET FOR BIR (ORUS, FORM 1903) AND DAET BUSINESS
 PERMIT
Copy these answers into BIR ORUS (orus.bir.gov.ph) and the Daet BPLO
application form. Blank rows are for Kristyle to complete.
Field
Answer
Source
Registered name
LANDTEK PROPERTY MANAGEMENT
SOLUTIONS OPC
COI
SEC Company Reg. No. /
date
2026110274328-35 / 02 Nov 2026
COI
Type
Stock corporation, One Person Corporation, all
Filipino
ESPARC
summary
Principal office / business
address
Purok 3 Bagasbas Road, Bagasbas, Daet,
Camarines Norte 4600
Articles Third
Industry (PSIC)
L682, real estate activities on a fee or contract
basis
Cover sheet
Line of business (plain)
Property management, consultancy and related
services for real property
Articles
Second
Authorized / subscribed /
paid-up capital
P100,000 / P25,000 / P25,000 (cash)
Articles
Seventh,
Eighth
President / sole director
Kristyle Joy Palma Cerdon, TIN
506-955-144-000
Articles Fifth
Treasurer
Kristine Andaya Palado, TIN
312-857-560-000
Decision 2
Nov 2026
Corporate Secretary
Allan Villafria Inocalla, TIN 200-031-253-000
Decision 2
Nov 2026
Fiscal year
Calendar year (1 Jan to 31 Dec)
SEC correction
requested (01)
Email / mobile
krstylpalma@gmail.com / 0926 531 6851
Cover sheet
Corporate TIN
From PBH /
BIR
RDO
Ask BIR
Date business starts
Kristyle
Employees
Kristyle
Office premises owner
(lease or consent)
Kristyle
Bring to BIR / ORUS uploads: SEC Certificate of Incorporation; Articles of
Incorporation; President's valid ID; selfie holding the ID; proof of office address.
Bring to Bagasbas Barangay Hall and Daet BPLO: SEC Certificate and
Articles; lease or consent letter for the office; President's ID; community tax
certificate (cedula) for the corporation; BIR 2303 when issued. Ask the BPLO for
its complete list on the first visit.$$
 WHERE source_ref = 'gmail_messages:152157' AND seq = 2 AND materials NOT LIKE '%SOURCE: attached form 04_BIR_ORUS_AND_DAET_PERMIT_DATA_SHEET.pdf%';
UPDATE staff_task SET materials = materials || E'\n\nSOURCE: attached form 04_BIR_ORUS_AND_DAET_PERMIT_DATA_SHEET.pdf\n' || $$DATA SHEET FOR BIR (ORUS, FORM 1903) AND DAET BUSINESS
 PERMIT
Copy these answers into BIR ORUS (orus.bir.gov.ph) and the Daet BPLO
application form. Blank rows are for Kristyle to complete.
Field
Answer
Source
Registered name
LANDTEK PROPERTY MANAGEMENT
SOLUTIONS OPC
COI
SEC Company Reg. No. /
date
2026110274328-35 / 02 Nov 2026
COI
Type
Stock corporation, One Person Corporation, all
Filipino
ESPARC
summary
Principal office / business
address
Purok 3 Bagasbas Road, Bagasbas, Daet,
Camarines Norte 4600
Articles Third
Industry (PSIC)
L682, real estate activities on a fee or contract
basis
Cover sheet
Line of business (plain)
Property management, consultancy and related
services for real property
Articles
Second
Authorized / subscribed /
paid-up capital
P100,000 / P25,000 / P25,000 (cash)
Articles
Seventh,
Eighth
President / sole director
Kristyle Joy Palma Cerdon, TIN
506-955-144-000
Articles Fifth
Treasurer
Kristine Andaya Palado, TIN
312-857-560-000
Decision 2
Nov 2026
Corporate Secretary
Allan Villafria Inocalla, TIN 200-031-253-000
Decision 2
Nov 2026
Fiscal year
Calendar year (1 Jan to 31 Dec)
SEC correction
requested (01)
Email / mobile
krstylpalma@gmail.com / 0926 531 6851
Cover sheet
Corporate TIN
From PBH /
BIR
RDO
Ask BIR
Date business starts
Kristyle
Employees
Kristyle
Office premises owner
(lease or consent)
Kristyle
Bring to BIR / ORUS uploads: SEC Certificate of Incorporation; Articles of
Incorporation; President's valid ID; selfie holding the ID; proof of office address.
Bring to Bagasbas Barangay Hall and Daet BPLO: SEC Certificate and
Articles; lease or consent letter for the office; President's ID; community tax
certificate (cedula) for the corporation; BIR 2303 when issued. Ask the BPLO for
its complete list on the first visit.$$
 WHERE source_ref = 'gmail_messages:152157' AND seq = 3 AND materials NOT LIKE '%SOURCE: attached form 04_BIR_ORUS_AND_DAET_PERMIT_DATA_SHEET.pdf%';
UPDATE staff_task SET materials = materials || E'\n\nSOURCE: attached form 02_LANDBANK_SOLE_DIRECTOR_RESOLUTION.pdf\n' || $$RESOLUTION OF THE SOLE DIRECTOR
 LANDTEK PROPERTY MANAGEMENT SOLUTIONS OPC
 SEC Company Reg. No. 2026110274328-35
Purok 3 Bagasbas Road, Bagasbas, Daet, Camarines Norte 4600
I, KRISTYLE JOY PALMA CERDON, single stockholder, sole director and
President of LANDTEK PROPERTY MANAGEMENT SOLUTIONS OPC (the
"Corporation"), adopt the following resolutions on ____________________
2026:
RESOLVED, that the Corporation open and maintain with LAND BANK OF
THE PHILIPPINES, ____________________ Branch, Daet, Camarines Norte
(the "Bank"): (1) a peso current and/or savings account in the name of the
Corporation for its operations (the "Operating Account"); and (2) a separate peso
savings account in the name of the Corporation designated "Client Trust" (the
"Client Account"), to hold only money received for clients, never mixed with the
Corporation's own funds;
RESOLVED FURTHER, that the sole authorized signatory on both accounts is
KRISTYLE JOY PALMA CERDON, President, who may sign alone all checks,
withdrawals, transfers and other instructions;
RESOLVED FURTHER, that the President is authorized to sign the account
opening forms, the beneficial ownership declaration and all other documents the
Bank requires, and to enroll the accounts in online banking with the same signing
rules;
RESOLVED FINALLY, that the Bank may rely on these resolutions until it
receives written notice of their amendment or revocation.
KRISTYLE JOY PALMA CERDON
Single Stockholder, Sole Director and President
TIN 506-955-144-000$$
 WHERE source_ref = 'gmail_messages:152157' AND seq = 4 AND materials NOT LIKE '%SOURCE: attached form 02_LANDBANK_SOLE_DIRECTOR_RESOLUTION.pdf%';
UPDATE staff_task SET materials = materials || E'\n\nSOURCE: attached form 03_LANDBANK_SECRETARYS_CERTIFICATE.pdf\n' || $$SECRETARY'S CERTIFICATE
I, ALLAN VILLAFRIA INOCALLA, of legal age, Filipino, with address at
________________________________________, after being sworn in
accordance with law, depose and say:
1. I am the duly appointed Corporate Secretary of LANDTEK PROPERTY
MANAGEMENT SOLUTIONS OPC (the "Corporation"), a one person
corporation registered with the Securities and Exchange Commission under
Company Reg. No. 2026110274328-35, with principal office at Purok 3
Bagasbas Road, Bagasbas, Daet, Camarines Norte 4600.
2. On ____________________ 2026 the single stockholder and sole director of
the Corporation, KRISTYLE JOY PALMA CERDON, adopted the resolutions
attached as Annex "A", on the opening of accounts with Land Bank of the
Philippines. They are recorded in the Corporation's minutes book and have not
been amended or revoked.
3. The sole officer of the Corporation authorized to sign under those resolutions,
and her specimen signature, is:
Name
Position
Specimen signature
KRISTYLE JOY PALMA CERDON
President
IN WITNESS WHEREOF, I have signed this certificate on
____________________ 2026 at Daet, Camarines Norte.
ALLAN VILLAFRIA INOCALLA
Corporate Secretary
TIN 200-031-253-000
SUBSCRIBED AND SWORN to before me this ____ day of
____________________ 2026 at ____________________, affiant exhibiting
____________________ No. ____________________ issued on
____________________ at ____________________.
Doc. No. ____; Page No. ____; Book No. ____; Series of 2026.
NOTARY PUBLIC$$
 WHERE source_ref = 'gmail_messages:152157' AND seq = 4 AND materials NOT LIKE '%SOURCE: attached form 03_LANDBANK_SECRETARYS_CERTIFICATE.pdf%';
