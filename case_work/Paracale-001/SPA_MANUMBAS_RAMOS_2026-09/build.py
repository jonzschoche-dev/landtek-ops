# -*- coding: utf-8 -*-
"""SPA pack — Manumbas & Ramos (AVI processing permits + CSSMA permits). Run: python3 build.py
Instruments: A = SPA (AVI lane, Allan personally)  ·  B = CSSMA Board Resolution + Secretary's
Certificate (association lane — the instrument that actually creates the authority)  ·
C = SPA (CSSMA lane, Allan signing as President — HOLD until incumbency is proven)  ·
D = Field briefing + annex checklist for the two representatives.
DRAFT-HELD. Nothing signed, nothing filed, nothing sent."""
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER

STAMP = ("DRAFT-HELD · prepared 17 September 2026 · nothing signed, nothing notarised, nothing filed · "
         "Paracale-001 (Allan V. Inocalla) · keep separate from MWK and NIBDC matters")

P1 = "ROMEO C. MANUMBAS"
P1D = ("Filipino, of legal age, <b>Treasurer of the Capacuan Small-Scale Miners Association</b>, with "
       "residence at Purok 4, Barangay Capacuan, Paracale, Camarines Norte, mobile 0930-407-1626")
P2 = "RAMON R. RAMOS"
P2D = ("Filipino, of legal age, <b>Secretary of the Capacuan Small-Scale Miners Association</b>, with "
       "residence at Purok 4, Barangay Capacuan, Paracale, Camarines Norte, mobile ____________________, "
       "email monraso1959@gmail.com")

BN = "AVI GOLD PROCESSING PLANT"
DTI = ("Business Name No. 8480852, Regional scope (Region V), valid 11 September 2026 to 11 September 2031, "
       "registered with the Department of Trade and Industry in my name")
SITE = ("Lot 4, Psu-143364, covered by Original Certificate of Title No. P-1616 of the Registry of Deeds for "
        "Camarines Norte, Barangay Santa Rosa Sur, Jose Panganiban, Camarines Norte")

ACK = [
    "", "REPUBLIC OF THE PHILIPPINES )",
    "_________________________________ ) S.S.", "",
    ("BEFORE ME, a Notary Public for and in _________________________, Philippines, this ____ day of "
     "______________ 2026, personally appeared the principal named above, who is personally known to me "
     "and who exhibited to me as competent evidence of identity his ______________________________ "
     "No. ____________________ issued on ____________ at ____________________, and who acknowledged to me "
     "that the foregoing instrument is his free and voluntary act and deed."),
    ("This instrument, consisting of ______ pages including this page on which this acknowledgment is written, "
     "has been signed by the principal and his instrumental witnesses on each and every page hereof."),
    "", "WITNESS MY HAND AND SEAL on the date and at the place first above written.", "", "", "",
    "NOTARY PUBLIC",
    "Doc. No. ______; Page No. ______; Book No. ______; Series of 2026.",
]

SIGBLOCK = [
    "", "", "IN WITNESS WHEREOF, I have hereunto set my hand this ____ day of ______________ 2026 "
    "at ______________________________, Philippines.", "", "", "",
    "<b>ALLAN VILLAFRIA INOCALLA</b>",
    "Principal · TIN 200-031-253", "Driver\u2019s Licence No. X01-11-002246, Land Transportation Office, valid to 12 January 2033", "", "",
    "CONFORME — accepting the trust and the limits written above:", "", "", "",
    "<b>" + P1 + "</b>                                        <b>" + P2 + "</b>",
    "Attorney-in-Fact                                                       Attorney-in-Fact", "", "",
    "SIGNED IN THE PRESENCE OF:", "",
    "______________________________                    ______________________________",
]

DOCS = []

# ───────────────────────── A · SPA — AVI lane ─────────────────────────
DOCS.append({
 "title": "INSTRUMENT A · SPECIAL POWER OF ATTORNEY — AVI GOLD PROCESSING PLANT (permit and document facilitation)",
 "note": "Allan signs in his own name as sole proprietor. This lane is squarely within his own authority — no resolution needed.",
 "head": ["REPUBLIC OF THE PHILIPPINES )", "_________________________________ ) S.S.", "",
          "<c><b>SPECIAL POWER OF ATTORNEY</b></c>", "", "KNOW ALL MEN BY THESE PRESENTS:"],
 "body": [
  ("I, <b>ALLAN VILLAFRIA INOCALLA</b>, Filipino, of legal age, with residence at Purok 4, Barangay Capacuan, "
   "Paracale, Camarines Norte, and sole proprietor of <b>" + BN + "</b>, a sole proprietorship registered under " + DTI +
   ", with plant site at " + SITE + ", do hereby NAME, CONSTITUTE and APPOINT —"),
  "<b>" + P1 + "</b>, " + P1D + "; and",
  "<b>" + P2 + "</b>, " + P2D + ",",
  ("— each of them to act <b>singly and independently of the other</b>, as my true and lawful "
   "ATTORNEYS-IN-FACT, for me and in my name, place and stead, <b>for the sole and limited purpose of "
   "facilitating the documents, clearances, permits and licences of " + BN + " and of its plant site</b>, "
   "with full power and authority to do and perform the following acts:"),
  ("<b>1. Obtain and lodge papers.</b> To secure application forms, checklists, requirements lists, orders of "
   "payment and assessment forms; to file, submit and lodge applications, letters, requests, petitions, "
   "compliance submissions, manifestations and follow-up letters in my name; and to sign the receiving copies, "
   "receiving logbooks and transmittal records <b>as the person filing on my behalf</b>."),
  ("<b>2. Pay official fees.</b> To pay filing, processing, registration, clearance, inspection and certification "
   "fees and other official charges against an official order of payment, and to demand, receive and keep the "
   "official receipts, which shall be issued in my name or in the name of " + BN + "."),
  ("<b>3. Obtain records.</b> To request and receive certified true copies, certifications, certified plans and "
   "maps, resolutions, endorsements, clearances, notices, orders and other documents relating to " + BN + ", "
   "to the plant site, and to my applications."),
  ("<b>4. Follow up and cure deficiencies.</b> To follow up the status of any application; to receive notices, "
   "orders, assessments and returns; to be informed of and to report to me any deficiency, defect or additional "
   "requirement; and to submit the curing documents that I furnish."),
  ("<b>5. Receive the issued instruments.</b> To receive the permits, licences, certificates, clearances and "
   "approvals issued, and to deliver the same to me intact."),
  ("<b>6. Attend and accompany.</b> To attend conferences, briefings, pre-assessment meetings and public "
   "consultations on my behalf; to accompany inspectors and evaluators to the plant site and to give them "
   "access to it; and to arrange the logistics of any ocular inspection."),
  ("<b>7. Before which offices.</b> The foregoing authority may be exercised before, among others: the "
   "<b>Mines and Geosciences Bureau, Regional Office No. V</b> (Rawis, Legazpi City) and the MGB Central Office; "
   "the <b>Environmental Management Bureau, Regional Office No. V</b>; the <b>Department of Environment and "
   "Natural Resources</b>, Regional Office V, PENRO and CENRO Camarines Norte; the <b>Provincial Mining "
   "Regulatory Board of Camarines Norte</b>; the <b>Provincial Government of Camarines Norte</b> and the "
   "Sangguniang Panlalawigan; the <b>Municipality of Jose Panganiban</b> (Office of the Mayor, Sangguniang Bayan, "
   "Business Permits and Licensing Office, Assessor, Treasurer, Engineering, Zoning, MENRO, Health/Sanitation) "
   "and the <b>Bureau of Fire Protection</b>; <b>Barangay Santa Rosa Sur</b>, Jose Panganiban, and "
   "<b>Barangay Capacuan</b>, Paracale; the <b>Department of Trade and Industry</b>; the <b>Bureau of Internal "
   "Revenue</b> in the district having jurisdiction; the <b>Registry of Deeds for Camarines Norte</b> and the "
   "<b>Land Registration Authority</b>, for certified copies of title only; the <b>National Mapping and Resource "
   "Information Authority</b>; the <b>National Commission on Indigenous Peoples</b>; and any other government "
   "office, agency, bureau or local government unit whose action is required for the same purpose."),
  ("<b>8. Specific transactions before the Bureau of Internal Revenue.</b> Without limiting the generality of "
   "the foregoing and for the purpose of Revenue regulations requiring that specific transactions be named, my "
   "attorneys-in-fact are expressly authorised to transact for me with the <b>Bureau of Internal Revenue</b> in "
   "the Revenue District Office having jurisdiction, specifically: to file <b>BIR Form No. 1901</b> "
   "(Application for Registration) for " + BN + " together with its Part X payment order on <b>BIR Form No. "
   "0605</b>; to file <b>BIR Form No. 1905</b> for the transfer of my registration records or the update of my "
   "registration details, should the District Office require it; to pay the documentary stamp tax and the "
   "cost of invoices and to receive the official receipts; to purchase <b>BIR Printed Invoices</b> at the New "
   "Business Registrant Counter; and to receive my <b>Certificate of Registration (BIR Form No. 2303)</b>, the "
   "invoice booklets and the received copies of the foregoing, and deliver them to me."),
  ("<b>EXPRESS LIMITS ON THIS AUTHORITY.</b> This Special Power of Attorney is strictly limited to the "
   "facilitation of documents and permits described above. My attorneys-in-fact are <b>NOT</b> authorised, and "
   "shall have no power whatsoever:"),
  "(a) to sell, convey, transfer, assign, mortgage, pledge, lease, or in any manner encumber or dispose of any land, title, permit, licence, equipment or other asset of mine or of " + BN + ";",
  "(b) to enter into, sign or agree to any contract, memorandum of agreement, joint venture, ore supply or offtake agreement, loan, investment, partnership or financial commitment, or to bind me in any obligation;",
  "(c) to receive, collect, hold or disburse any money or property for my account, except official receipts and the documents named above; and not to borrow, advance or lend money in my name;",
  "(d) to execute, sign or swear to any affidavit, sworn application, sworn statement, undertaking or declaration that requires my personal knowledge or my personal oath — those instruments I shall sign myself;",
  "(e) to waive, compromise, settle, quitclaim or release any right, claim or cause of action of mine;",
  "(f) to appoint a substitute or to delegate any part of this authority to any other person;",
  "(g) to represent me before any court, prosecutor's office, or in any adversarial, criminal or quasi-judicial contest, or to perform any act that constitutes the practice of law; and",
  "(h) to give, offer or pay anything to any public officer other than the official fees supported by an official receipt.",
  ("<b>ACCOUNTING.</b> My attorneys-in-fact shall turn over to me every document received and every official "
   "receipt within a reasonable time from receipt, and shall render an accounting of all sums advanced or paid."),
  ("<b>TERM AND REVOCATION.</b> This Special Power of Attorney shall take effect upon its notarisation and "
   "shall remain in force until <b>31 December 2027</b>, unless sooner revoked. It is revocable by me at any "
   "time and for any reason, by written notice to the attorney-in-fact concerned, and I undertake to furnish a "
   "copy of the revocation to the offices before which this instrument has been presented. Any act done in good "
   "faith by a third person in reliance on this instrument before receipt of the revocation shall be respected."),
  ("HEREBY GIVING AND GRANTING unto my said attorneys-in-fact full power and authority to do and perform every "
   "act requisite and necessary to carry out the limited purposes above, as fully to all intents and purposes "
   "as I might or could lawfully do if personally present, <b>save only the acts expressly withheld above</b>, "
   "and hereby ratifying and confirming all that my said attorneys-in-fact shall lawfully do or cause to be "
   "done under and by virtue hereof."),
 ] + SIGBLOCK + ACK})

# ───────────────────── B · CSSMA resolution + secretary's certificate ─────────────────────
DOCS.append({
 "title": ("INSTRUMENT B · CAPACUAN SMALL-SCALE MINERS ASSOCIATION — BOARD/MEMBERSHIP RESOLUTION and "
           "SECRETARY'S CERTIFICATE (the instrument that actually creates authority for the association lane)"),
 "note": ("The association's own instrument, and still the cleanest paper for the CSSMA permits. Corpus doc 4894 "
          "(Minutes of the Selection of Association Officers, 15 February 2026, three-year tenure) settles the "
          "line-up: ALLAN V. INOCALLA President, JESUS V. INOCALLA Vice-President, RAMON R. RAMOS Secretary, "
          "ROMEO C. MANUMBAS Treasurer. So the two attorneys-in-fact are the association's own Secretary and "
          "Treasurer, and the principal is its President \u2014 the 2021 \u2018Acting President\u2019 record was "
          "superseded by this reorganisation."),
 "head": ["<c><b>CAPACUAN SMALL-SCALE MINERS ASSOCIATION</b></c>",
          "<c>Purok 4, Barangay Capacuan, Paracale, Camarines Norte</c>",
          "<c>DOLE Registration No. R0500-CN-0417-019-17</c>", "",
          "<c><b>RESOLUTION NO. ______, Series of 2026</b></c>", "",
          ("<c><b>A RESOLUTION AUTHORISING ROMEO C. MANUMBAS, SR. AND RAMON ____________ RAMOS TO REPRESENT THE "
           "ASSOCIATION BEFORE GOVERNMENT AGENCIES AND TO FACILITATE ALL DOCUMENTS, CLEARANCES AND PERMITS "
           "REQUIRED FOR ITS MINAHANG BAYAN AND SMALL-SCALE MINING APPLICATIONS</b></c>"), ""],
 "body": [
  ("<b>WHEREAS</b>, the Capacuan Small-Scale Miners Association (the “Association”) is a duly registered "
   "workers'/miners' association with Department of Labor and Employment Registration No. R0500-CN-0417-019-17, "
   "with principal address at Purok 4, Barangay Capacuan, Paracale, Camarines Norte;"),
  ("<b>WHEREAS</b>, the Association has pending before the Provincial Mining Regulatory Board of Camarines "
   "Norte, through the Mines and Geosciences Bureau Regional Office No. V, its petition for the declaration of "
   "a <b>Minahang Bayan</b> over the area in Barangay Capacuan, Paracale, and has likewise written the MGB "
   "Central Office in respect of an <b>Interim Small-Scale Mining Permit / Contract</b> over the same area;"),
  ("<b>WHEREAS</b>, the prosecution of those applications requires the constant lodging, follow-up, payment and "
   "retrieval of documents before several national and local government offices, and the Association finds it "
   "necessary to designate representatives for that purpose;"),
  ("<b>NOW, THEREFORE</b>, on motion duly made and seconded, the Board of Directors/Officers, with the "
   "concurrence of the general membership in the meeting held on ____ ______________ 2026 at "
   "______________________________, at which a quorum was present, <b>RESOLVED, as it hereby RESOLVES</b>:"),
  ("<b>1.</b> To authorise <b>" + P1 + "</b> and <b>" + P2 + "</b>, each to act singly and independently of the "
   "other, to represent the Association before the Provincial Mining Regulatory Board of Camarines Norte, the "
   "Mines and Geosciences Bureau (Regional Office No. V and Central Office), the Department of Environment and "
   "Natural Resources and its Environmental Management Bureau, PENRO and CENRO Camarines Norte, the Department "
   "of Labor and Employment Regional Office No. V, the Provincial Government of Camarines Norte and the "
   "Sangguniang Panlalawigan, the Municipality of Paracale and its Sangguniang Bayan, Barangay Capacuan, the "
   "National Commission on Indigenous Peoples, and any other government office whose action is required;"),
  ("<b>2.</b> To empower them, for and on behalf of the Association, to secure and file application forms, "
   "petitions, letters, compliance submissions and follow-up letters; to sign receiving copies and logbooks as "
   "the persons filing; to pay official fees against orders of payment and to receive the official receipts in "
   "the name of the Association; to request and receive certified true copies of records, resolutions, "
   "endorsements, certifications and maps; to receive notices, orders and the permits or certificates issued; "
   "to attend conferences and public consultations; and to accompany inspectors on ocular inspections;"),
  ("<b>3.</b> That the authority so granted is <b>limited to the facilitation of documents and permits</b>. The "
   "representatives are <b>not</b> authorised to sell, transfer, mortgage or encumber any right, area or asset "
   "of the Association; to sign any contract, memorandum of agreement, joint venture, ore supply or offtake "
   "agreement, loan or financial commitment; to receive or disburse funds of the Association beyond the official "
   "fees covered by an order of payment; to sign any affidavit or sworn statement requiring the personal "
   "knowledge of an officer; to waive, compromise or settle any right of the Association; or to delegate this "
   "authority to any other person. Every document and official receipt shall be turned over to the Association, "
   "and an accounting rendered, within a reasonable time;"),
  ("<b>4.</b> That this authority shall remain in force until <b>31 December 2027</b> unless sooner revoked by "
   "the Board, notice of revocation to be given in writing to the representatives and to the offices before "
   "which this Resolution has been presented;"),
  ("<b>5.</b> That the Secretary of the Association is directed to issue a Secretary's Certificate of this "
   "Resolution and to furnish certified copies to the offices concerned."),
  "<b>APPROVED</b> this ____ day of ______________ 2026 at Barangay Capacuan, Paracale, Camarines Norte.", "",
  "______________________________                    ______________________________",
  "<b>ALLAN V. INOCALLA</b> \u00b7 President                      <b>JESUS V. INOCALLA</b> \u00b7 Vice-President", "",
  "______________________________                    ______________________________",
  "<b>RAMON R. RAMOS</b> \u00b7 Secretary                          <b>ROMEO C. MANUMBAS</b> \u00b7 Treasurer", "",
  "Directors: ______________________  ______________________  ______________________",
  "(Edwin E. Monilla \u00b7 Rogelio J. Heravan \u00b7 Dionesio N. Montalban \u00b7 Ruben C. Manumbas \u00b7 Jimuel P. Regular)", "",
  "<c><b>SECRETARY'S CERTIFICATE</b></c>", "",
  "REPUBLIC OF THE PHILIPPINES )", "_________________________________ ) S.S.", "",
  ("I, <b>RAMON R. RAMOS</b>, Filipino, of legal age, and the duly selected and incumbent <b>Secretary</b> of "
   "the <b>Capacuan Small-Scale Miners Association</b>, after having been duly sworn, hereby certify that:"),
  ("1. At a meeting of the Board of Directors/Officers of the Association, with the concurrence of the general "
   "membership, duly called and held on ____ ______________ 2026 at ______________________________, at which "
   "meeting a quorum was present and acting throughout, the foregoing <b>Resolution No. ______, Series of "
   "2026</b> was unanimously adopted;"),
  ("2. The said Resolution has not been amended, modified or revoked and is in full force and effect as of the "
   "date of this Certificate;"),
  ("3. Per the Minutes of the Selection of Association Officers held 15 February 2026, for a tenure of three "
   "(3) years, the incumbent officers and directors of the Association are: <b>President</b>, ALLAN V. "
   "INOCALLA; <b>Vice-President</b>, JESUS V. INOCALLA; <b>Secretary</b>, RAMON R. RAMOS; <b>Treasurer</b>, "
   "ROMEO C. MANUMBAS; <b>Auditor</b>, MA. SHIELA D. MENDOZA; <b>P.R.O.</b>, RAFAEL S. BARROSO; <b>Sgt. at "
   "Arms</b>, RADZ GYMSON INOCALLA; <b>Business Managers</b>, NOEL U. RIGON and ROBIN JOSHUA Z. NUELAN; and "
   "<b>Board of Directors</b>, EDWIN E. MONILLA, ROGELIO J. HERAVAN, DIONESIO N. MONTALBAN, RUBEN C. MANUMBAS "
   "and JIMUEL P. REGULAR;"),
  ("4. The specimen signatures of the authorised representatives appear below:"), "",
  "______________________________                    ______________________________",
  P1 + "                              " + P2, "",
  ("I issue this Certificate this ____ day of ______________ 2026 at ______________________________, "
   "Philippines, for whatever legal purpose it may serve."), "", "", "",
  "<b>RAMON R. RAMOS</b>", "Secretary, Capacuan Small-Scale Miners Association", "",
  ("SUBSCRIBED AND SWORN to before me this ____ day of ______________ 2026 at ______________________________, "
   "affiant exhibiting to me his/her ______________________ No. ______________ issued on __________ at "
   "__________."), "", "", "NOTARY PUBLIC",
  "Doc. No. ______; Page No. ______; Book No. ______; Series of 2026."]})

# ───────────────────── C · SPA — CSSMA lane, Allan as President (HELD) ─────────────────────
DOCS.append({
 "title": ("INSTRUMENT C · SPECIAL POWER OF ATTORNEY — CAPACUAN SMALL-SCALE MINERS ASSOCIATION "
           "(Allan signing as its President)"),
 "note": ("USE ONLY IF Allan is in fact the incumbent President of CSSMA and a board/membership resolution "
          "authorising him to appoint attorneys-in-fact is attached. Do not sign this without Instrument B or "
          "its equivalent behind it: on the corpus record Allan is President of Paracale Gold Corporation and "
          "“Representative, The Inocalla Family”, not a documented officer of CSSMA."),
 "head": ["REPUBLIC OF THE PHILIPPINES )", "_________________________________ ) S.S.", "",
          "<c><b>SPECIAL POWER OF ATTORNEY</b></c>", "", "KNOW ALL MEN BY THESE PRESENTS:"],
 "body": [
  ("I, <b>ALLAN VILLAFRIA INOCALLA</b>, Filipino, of legal age, with residence at Purok 4, Barangay Capacuan, "
   "Paracale, Camarines Norte, in my capacity as <b>President of the CAPACUAN SMALL-SCALE MINERS ASSOCIATION</b> "
   "(Purok 4, Barangay Capacuan, Paracale, Camarines Norte; DOLE Registration No. R0500-CN-0417-019-17), and by "
   "authority of <b>Resolution No. ______, Series of 2026</b> of its Board of Directors/Officers, a certified "
   "copy of which is attached and made an integral part hereof, do hereby NAME, CONSTITUTE and APPOINT —"),
  "<b>" + P1 + "</b>, " + P1D + "; and",
  "<b>" + P2 + "</b>, " + P2D + ",",
  ("— each to act singly and independently of the other, as the Association's ATTORNEYS-IN-FACT, for the sole "
   "and limited purpose of <b>facilitating the documents, clearances and permits required for the Association's "
   "Minahang Bayan petition, its small-scale mining permit or contract applications, and its registration and "
   "compliance filings</b>, with the same powers, before the same offices, and under the same express limits as "
   "are set out in paragraphs 1 to 7 and in the paragraph headed EXPRESS LIMITS of Instrument A of this pack, "
   "which are incorporated here by reference and shall be reproduced in full in the executed copy."),
  ("<b>TERM AND REVOCATION.</b> Effective upon notarisation until <b>31 December 2027</b>, unless sooner "
   "revoked by the Association by written notice to the attorney-in-fact concerned and to the offices before "
   "which this instrument has been presented."),
 ] + ["", "", "IN WITNESS WHEREOF, I have hereunto set my hand this ____ day of ______________ 2026 at "
      "______________________________, Philippines.", "", "", "",
      "<b>ALLAN VILLAFRIA INOCALLA</b>",
      "President, Capacuan Small-Scale Miners Association",
      "Driver\u2019s Licence No. X01-11-002246, Land Transportation Office, valid to 12 January 2033", "", "",
      "CONFORME:", "", "", "",
      "<b>" + P1 + "</b>                                        <b>" + P2 + "</b>",
      "Attorney-in-Fact                                                       Attorney-in-Fact"] + ACK})

# ───────────────────── D · field briefing + annexes ─────────────────────
DOCS.append({
 "title": "INSTRUMENT D · ANNEX CHECKLIST AND FIELD BRIEFING FOR THE TWO REPRESENTATIVES",
 "note": "Not a legal instrument. Print and hand to Manumbas and Ramos with the notarised originals.",
 "head": ["<c><b>WHAT TO CARRY, AND HOW TO ACT</b></c>", ""],
 "body": [
  "<b>1. What each representative carries to every office</b>",
  "(a) The <b>notarised original</b> of the Special Power of Attorney (Instrument A) — and for association business, the notarised Secretary's Certificate with the Resolution (Instrument B). Bring the original; leave a photocopy.",
  "(b) Two <b>photocopies</b> of that instrument for the office to keep and to stamp.",
  "(c) <b>Photocopy of Allan's valid government ID</b>, the same ID recited in the notarial acknowledgment, signature matching.",
  "(d) The representative's <b>own valid government ID</b>, original and photocopy.",
  "(e) For the AVI lane: DTI Certificate of Business Name Registration No. 8480852; certified true copy of OCT No. P-1616; the tax declaration; the barangay clearance if already issued.",
  "(f) For the association lane: the DOLE registration certificate, the membership roll, and the barangay and Sangguniang Bayan resolutions already on file.",
  "(g) A <b>notebook</b> and a phone with a working camera.",
  "",
  "<b>2. Rules for every visit</b>",
  "1. <b>Everything in writing.</b> Hand over the letter or application, and get the second copy stamped RECEIVED with the date and the name and position of the receiving staff. If they will not stamp it, write down the name of the person who refused, the date and the time.",
  "2. <b>Never pay without an order of payment and never leave without an official receipt.</b> No cash to a person. No “facilitation” money, no gift, no meal for a public officer. If anyone asks for one, do not argue — leave, write down what was said and who said it, and report it the same day.",
  "3. <b>Sign nothing except the receiving logbook</b> and, where required, as the person filing. No waivers, no quitclaims, no settlement papers, no contracts, no affidavits.",
  "4. <b>Do not accept a verbal answer as the answer.</b> If staff explain something verbally, take the name and say: “please put that in the written reply.”",
  "5. <b>Do not exceed the paper.</b> If an officer asks for something the SPA does not cover — a signature on an agreement, a commitment on area or royalty, an undertaking — say the authority is limited to documents and that the principal will answer, and report it the same day.",
  "6. <b>Photograph every stamped page</b> and send it in the same day, with the office, the date and the name of the receiving staff.",
  "7. Ask for the <b>name of the action officer</b> handling the file, and for the expected timeline.",
  "",
  "<b>3. Before the instruments are signed</b>",
  "(a) Fill in <b>Ramos's complete legal name, middle name, address and mobile</b> exactly as they appear on his valid ID — the name in this draft is incomplete.",
  "(b) Confirm <b>Manumbas's full name and current address</b> against his own ID; the record carries “Romeo C. Manumbas, Sr.”",
  "(c) Decide the <b>place and date</b> of signing and notarisation, and the ID each signatory will present.",
  "(d) Pay the <b>documentary stamp tax</b> on the power of attorney and have the notary affix it; confirm the current amount with the notary.",
  "(e) If Allan signs <b>outside the Philippines</b>, the instrument must be notarised before a Philippine Consul or apostilled in the country of signing — a local notary abroad alone will not be accepted.",
  "(f) Have <b>at least four notarised originals</b> made: one for each representative, one for Allan, one for the file.",
 ]})

# ───────────────────────────── renderers ─────────────────────────────
def clean(t): return t.replace('<b>','').replace('</b>','').replace('<c>','').replace('</c>','')

doc = Document()
for s in doc.sections:
    s.top_margin = s.bottom_margin = Inches(0.9); s.left_margin = s.right_margin = Inches(1.0)
doc.styles['Normal'].font.name = 'Times New Roman'; doc.styles['Normal'].font.size = Pt(11.5)
def para(text, bold=False, align=None, size=None, space=6):
    p = doc.add_paragraph(); r = p.add_run(clean(text))
    r.bold = bold or text.strip().startswith('<b>') or '<b>' == text[:3]
    if size: r.font.size = Pt(size)
    if align == 'c' or text.startswith('<c>'): p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif align == 'j': p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(space); return p
para("SPECIAL POWER OF ATTORNEY PACK — ROMEO C. MANUMBAS, SR. AND RAMON ____ RAMOS", bold=True, align='c', size=13)
para(STAMP, align='c', size=9.5)
para("Contents: " + " | ".join(clean(d["title"]) for d in DOCS), align='j', size=9.5)
for d in DOCS:
    doc.add_page_break()
    para(clean(d["title"]), bold=True, size=11, space=4)
    if d.get("note"): para("Note: " + clean(d["note"]), align='j', size=9.5, space=10)
    for t in d["head"]: para(t, align='c' if t.startswith('<c>') else None, space=2)
    para("")
    for t in d["body"]: para(t, align='j' if len(clean(t)) > 70 and not t.startswith('<c>') else None)
doc.save("SPA_MANUMBAS_RAMOS_2026-09.docx")

ss = getSampleStyleSheet()
J = ParagraphStyle('J', parent=ss['Normal'], fontName='Times-Roman', fontSize=11, leading=14.5, alignment=TA_JUSTIFY, spaceAfter=6)
L = ParagraphStyle('L', parent=J, alignment=0, spaceAfter=2)
C = ParagraphStyle('C', parent=J, alignment=TA_CENTER, spaceAfter=2)
B = ParagraphStyle('B', parent=J, fontName='Times-Bold')
T = ParagraphStyle('T', parent=J, fontName='Times-Bold', fontSize=11, textColor='#333333')
N = ParagraphStyle('N', parent=J, fontSize=9.5, leading=12, textColor='#444444')
TITLE = ParagraphStyle('TT', parent=C, fontName='Times-Bold', fontSize=13)
def pdfp(t):
    return t.replace('<c>','').replace('</c>','')
story = [Paragraph("SPECIAL POWER OF ATTORNEY PACK — ROMEO C. MANUMBAS, SR. AND RAMON ____ RAMOS", TITLE),
         Paragraph(STAMP, N), Spacer(1, 6),
         Paragraph("Contents: " + " | ".join(clean(d["title"]) for d in DOCS), N)]
for d in DOCS:
    story.append(PageBreak())
    story.append(Paragraph(clean(d["title"]), T)); story.append(Spacer(1, 4))
    if d.get("note"): story.append(Paragraph("Note: " + clean(d["note"]), N)); story.append(Spacer(1, 8))
    for t in d["head"]: story.append(Paragraph(pdfp(t) or "&nbsp;", C if t.startswith('<c>') else L))
    story.append(Spacer(1, 6))
    for t in d["body"]:
        st = C if t.startswith('<c>') else (J if len(clean(t)) > 70 else L)
        story.append(Paragraph(pdfp(t) or "&nbsp;", st))
SimpleDocTemplate("SPA_MANUMBAS_RAMOS_2026-09.pdf", pagesize=A4, leftMargin=2.3*cm, rightMargin=2.3*cm,
                  topMargin=2*cm, bottomMargin=2*cm).build(story)
print("built: SPA_MANUMBAS_RAMOS_2026-09.docx + .pdf")
