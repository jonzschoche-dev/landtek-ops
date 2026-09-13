# AVI Gold Processing Plant — ancillary request letters bundle (8 instruments). Run: python3 build.py
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER

BN = "AVI GOLD PROCESSING PLANT"
DTI = "DTI Business Name No. 8480852 (Regional – Region V), valid 11 September 2026 to 11 September 2031"
SITE = "Lot 4, Psu-143364, Original Certificate of Title No. P-1616 (Registry of Deeds for Camarines Norte), Barangay Santa Rosa Sur, Jose Panganiban, Camarines Norte 4606"
HEAD = [("b", BN), ("n", "Allan V. Inocalla, Proprietor"),
        ("n", "Residence: Purok 4, Barangay Capacuan, Paracale, Camarines Norte 4605 · Plant site: " + SITE),
        ("n", "Mobile 0917 155 4782  ·  shiraction2@gmail.com  ·  TIN 200-011-253")]
SIGN = ["Respectfully yours,", "", "", "", "<b>ALLAN V. INOCALLA</b>", f"Proprietor, {BN}", ""]
RCV = "Received by: ______________________  Position: ______________  Date/Time: ______________"

def letter(title, addr, subject, paras, encl):
    return {"title": title, "addr": ["14 September 2026", ""] + addr, "subject": subject,
            "body": paras + SIGN + ([encl] if encl else []) + [RCV]}

DOCS = []

# 1. Barangay Business Clearance request — Santa Rosa Sur
DOCS.append(letter("1 · Request for Barangay Business Clearance — Barangay Santa Rosa Sur",
    ["HON. ______________________________", "Punong Barangay", "Barangay Santa Rosa Sur, Jose Panganiban, Camarines Norte", "", "Thru: The Barangay Secretary / Treasurer"],
    "SUBJECT: REQUEST FOR BARANGAY BUSINESS CLEARANCE — AVI GOLD PROCESSING PLANT (SECTION 152, RA 7160)",
    ["Dear Punong Barangay:",
     (f"Pursuant to Section 152(c) of Republic Act No. 7160, the Local Government Code of 1991, I respectfully request the issuance of a "
      f"<b>Barangay Business Clearance</b> in favor of <b>{BN}</b>, a sole proprietorship registered with the Department of Trade and "
      f"Industry under {DTI}, issued to me, Allan Villafria Inocalla."),
     (f"Nature of business: gold ore processing (mineral processing plant), gravity concentration, mercury-free and cyanide-free. "
      f"Business address: {SITE}, a lot registered solely in my name. Area to be used by the business: five thousand (5,000) square meters, initial plant footprint "
      "(portion of Lot 4, total lot area 15.2069 hectares / 152,069 square meters). Status: new business, pre-operational; the plant will operate only after the Environmental Compliance "
      "Certificate (EMB Region V) and the Mineral Processing Permit / Mineral Processor's License (MGB Region V / PMRB) are issued."),
     ("The clearance is required for the Mayor's / Business Permit application with the Municipal Business Permits and Licensing "
      "Office, and is also submitted with the applications to MGB Region V and EMB Region V. I undertake to pay the barangay clearance "
      "fee and documentary stamp tax under the Barangay's revenue ordinance, and to abide by the Barangay's ordinances on peace and "
      "order, sanitation and the environment."),
     "Attached are copies of the DTI Certificate of Business Name Registration, the certified true copy of OCT No. P-1616, a sketch of the "
     "portion of the lot to be used, and two valid identification cards."],
    "Enclosures: (1) DTI Certificate No. 8480852 and official receipt; (2) OCT No. P-1616 (certified true copy) and Tax Declaration No. ______; "
    "(3) Sketch of the business site; (4) Two valid IDs; (5) Community Tax Certificate No. ______ issued __ September 2026."))

# 2. Draft Barangay Business Clearance (for the Barangay Secretary) — mirrors the Paracale/Capacuan form (doc 1295)
DOCS.append({"title": "2 · Draft Barangay Business Clearance (for the Barangay's own form; text offered for convenience)",
    "addr": ["Republika ng Pilipinas · Lalawigan ng Camarines Norte · Bayan ng Jose Panganiban", "BARANGAY SANTA ROSA SUR", "Tanggapan ng Punong Barangay", "",
             "BARANGAY BUSINESS CLEARANCE", "", "TO WHOM IT MAY CONCERN:"],
    "subject": "",
    "body": [("Pursuant to Section 152 of RA No. 7160, otherwise known as the Local Government Code of 1991, requiring all business or activity to "
              "obtain a Barangay Clearance from the barangay where the business or activity is located before operating or commencing their "
              "trade or business, and in compliance therewith, this Barangay Business Clearance is hereby granted to:"),
             f"<b>{BN}</b>", "<b>ALLAN VILLAFRIA INOCALLA</b> — Owner/Proprietor",
             f"of {SITE},",
             "Nature of business: Gold ore processing plant (gravity concentration; mercury-free), pre-operational.",
             ("This Clearance is issued for the purpose of securing a Mayor's / Business Permit from the Municipality of Jose Panganiban and "
              "the permits required by the Mines and Geosciences Bureau and the Environmental Management Bureau, and expires on December 31, 2026 "
              "unless sooner revoked for violation of barangay ordinances."),
             "Issued this 14th day of September 2026 at Barangay Santa Rosa Sur, Jose Panganiban, Camarines Norte.", "", "", "",
             "HON. ______________________________", "Punong Barangay", "",
             "Paid under O.R. No. __________   Amount: ₱__________ (per Barangay revenue ordinance; the 2016 Capacuan precedent was ₱500.00)   Date paid: 14 September 2026   Documentary Stamp Tax paid: ₱15.00 (as in the 2016 precedent; adjust to current)",
             "(Text follows the Barangay Capacuan, Paracale clearances of 2016 in the applicant's file; the Barangay uses its own form and numbering.)"]})

# 3. Municipal Assessor — tax declaration
DOCS.append(letter("3 · Request to the Municipal Assessor — Tax Declaration for Lot 4, OCT P-1616",
    ["THE MUNICIPAL ASSESSOR", "Office of the Municipal Assessor", "Municipality of Jose Panganiban, Camarines Norte"],
    "SUBJECT: REQUEST FOR ISSUANCE / TRANSFER OF TAX DECLARATION IN THE NAME OF ALLAN V. INOCALLA AND CERTIFIED COPIES — LOT 4, PSU-143364, OCT NO. P-1616, BARANGAY SANTA ROSA SUR",
    ["Sir/Madam:",
     ("I respectfully request (1) the issuance of a Tax Declaration in my name, Allan Villafria Inocalla, for Lot 4, Psu-143364, covered by "
      "Original Certificate of Title No. P-1616 of the Registry of Deeds for Camarines Norte (Free Patent No. 225537 dated 10 May 1963), "
      "15.2069 hectares, Barangay Santa Rosa Sur (described in the 1963 patent as barrio San Rafael), or the transfer to my name of any "
      "existing tax declaration covering the lot; (2) a certification of the current tax declaration and assessed value; and (3) a "
      "certified copy of the tax map / property index number for the lot."),
     ("The title has been in my name since its issuance in 1963. The tax declaration is required for my business permit, environmental "
      "compliance and mineral-processing permit applications for AVI Gold Processing Plant, which will occupy a portion of the lot. "
      "Please also advise the real property tax due, if any, so that it may be settled at the Municipal Treasury."),
     "Attached: certified true copy of OCT No. P-1616 with technical description; two valid IDs; Community Tax Certificate."],
    "Enclosures: (1) OCT No. P-1616 (certified true copy, LRA/RD); (2) Two valid IDs; (3) CTC No. ______; (4) Sketch plan of Lot 4 if available."))

# 4. Registry of Deeds — certified true copy of OCT
DOCS.append(letter("4 · Request to the Registry of Deeds — Certified True Copy of OCT P-1616",
    ["THE REGISTER OF DEEDS", "Registry of Deeds for the Province of Camarines Norte", "Daet, Camarines Norte"],
    "SUBJECT: REQUEST FOR CERTIFIED TRUE COPY OF ORIGINAL CERTIFICATE OF TITLE NO. P-1616 (LOT 4, PSU-143364), WITH ALL ANNOTATIONS",
    ["Sir/Madam:",
     ("I respectfully request two (2) certified true copies of Original Certificate of Title No. P-1616, Book 14, Page 26, Registry of Deeds "
      "for Camarines Norte, covering Lot 4, Psu-143364, Jose Panganiban, Camarines Norte, registered in my name, Allan Villafria Inocalla, "
      "including the technical description and the complete memorandum of encumbrances up to the date of issuance, for submission to the "
      "Mines and Geosciences Bureau Region V, the Environmental Management Bureau Region V and the Municipality of Jose Panganiban."),
     "I will pay the certification fees upon assessment. Attached are two valid IDs."],
    "Enclosures: (1) Two valid IDs; (2) Photocopy of the owner's duplicate certificate."))

# 5. MPDO — zoning / locational clearance + land-use certification
DOCS.append(letter("5 · Request to the MPDO / Zoning Officer — Locational Clearance and Land-Use Certification",
    ["THE MUNICIPAL PLANNING AND DEVELOPMENT COORDINATOR / ZONING OFFICER", "Municipal Planning and Development Office", "Municipality of Jose Panganiban, Camarines Norte"],
    "SUBJECT: APPLICATION FOR LOCATIONAL / ZONING CLEARANCE AND CERTIFICATION OF LAND-USE CLASSIFICATION — PORTION OF LOT 4, PSU-143364 (OCT NO. P-1616), BARANGAY SANTA ROSA SUR, FOR AVI GOLD PROCESSING PLANT",
    ["Sir/Madam:",
     (f"I respectfully apply for a <b>Locational / Zoning Clearance</b> for a mercury-free gold gravity-concentration plant, <b>{BN}</b> "
      f"({DTI}), on a portion of about five thousand (5,000) square meters (initial plant footprint) of {SITE} (total 15.2069 hectares), registered solely in my name, and request a "
      "<b>certification of the land-use classification</b> of the lot under the Municipality's Comprehensive Land Use Plan and Zoning "
      "Ordinance, stating whether the proposed use is conforming."),
     ("The certification is a requirement of the Environmental Management Bureau for the plant's Environmental Compliance Certificate "
      "application (LGU certification of compatibility with the land-use plan) and of the Mines and Geosciences Bureau for the Mineral "
      "Processing Permit. Should the lot be classified as agricultural, I request guidance on the exemption or conversion procedure "
      "applicable to the plant footprint only."),
     ("Project summary: throughput about 10 tonnes of ore per day (under 10,000 tonnes per year); crushing and milling, classification, "
      "centrifugal rougher and concentrating tables; no mercury, no cyanide; lined tailings facility with no discharge; power from "
      "CANORECO; workers preferentially from Barangay Santa Rosa Sur."),
     "Attached: sketch / site development plan showing the portion to be used, OCT and tax declaration, DTI certificate, barangay clearance, and two IDs. I will pay the clearance fees upon assessment."],
    "Enclosures: (1) Site development plan / sketch with vicinity map; (2) OCT No. P-1616 (CTC) and Tax Declaration; (3) DTI Certificate No. 8480852; (4) Barangay Business Clearance, Santa Rosa Sur; (5) Two valid IDs."))

# 6. DENR CENRO — land classification status
DOCS.append(letter("6 · Request to DENR CENRO — Certification of Land Classification Status",
    ["THE COMMUNITY ENVIRONMENT AND NATURAL RESOURCES OFFICER", "DENR – CENRO DAET (jurisdiction over Jose Panganiban — confirm with PENRO Camarines Norte, Pamorangon, Daet, tel. (054) 440-0737)", "Camarines Norte"],
    "SUBJECT: REQUEST FOR CERTIFICATION OF LAND CLASSIFICATION STATUS — LOT 4, PSU-143364 (OCT NO. P-1616), BARANGAY SANTA ROSA SUR, JOSE PANGANIBAN",
    ["Sir/Madam:",
     ("I respectfully request a <b>Certification of Land Classification Status</b> for Lot 4, Psu-143364, covered by Original Certificate of "
      "Title No. P-1616 (Free Patent No. 225537 dated 10 May 1963) in my name, at Barangay Santa Rosa Sur, Jose Panganiban, Camarines Norte, "
      "15.2069 hectares, stating (a) whether the area is classified as alienable and disposable, timberland or forestland; (b) whether it "
      "lies within or outside any protected area under the E-NIPAS Act; and (c) whether it lies within any ancestral domain or DENR "
      "tenurial instrument."),
     ("The certification is a requirement of EMB Region V for the Environmental Compliance Certificate application of AVI Gold Processing "
      "Plant, a mercury-free gold gravity-concentration plant to be built on a portion of the lot. Attached are the certified true copy of "
      "the title with technical description and a location sketch; I will pay the certification fee upon assessment."),
     ],
    "Enclosures: (1) OCT No. P-1616 (CTC) with technical description; (2) Location sketch / tie-line to BLLM; (3) Two valid IDs."))

# 7. Authorization letter (Allan -> Jonathan / LandTek)
DOCS.append({"title": "7 · Authorization Letter (Allan V. Inocalla → representative)",
    "addr": ["14 September 2026", "", "TO WHOM IT MAY CONCERN:"], "subject": "AUTHORIZATION",
    "body": [("I, <b>ALLAN VILLAFRIA INOCALLA</b>, of legal age, Filipino, proprietor of <b>AVI GOLD PROCESSING PLANT</b> (DTI Business Name No. 8480852), "
              "with residence at Purok 4, Barangay Capacuan, Paracale, Camarines Norte, hereby authorize <b>JONATHAN ZSCHOCHE</b> "
              "(______________________ [ID type and number]) and/or <b>______________________</b> to act for me and on my behalf to:"),
             ("1. File, follow up, pay the fees for, and receive documents relating to my applications for the Barangay Business Clearance, "
              "Mayor's / Business Permit, Locational / Zoning Clearance and Tax Declaration with the Barangay of Santa Rosa Sur and the "
              "Municipality of Jose Panganiban; the certified true copy of OCT No. P-1616 with the Registry of Deeds for Camarines Norte; "
              "the Certification of Land Classification Status with the DENR CENRO concerned; the Environmental Compliance Certificate with "
              "EMB Region V (including the ECC Online account); and the Mineral Processing Permit / Mineral Processor's License with MGB "
              "Region V and the Provincial Mining Regulatory Board of Camarines Norte;"),
             ("2. Submit the Barangay and Sangguniang Bayan endorsement requests and attend hearings, consultations and orientations in "
              "connection with them; and"),
             "3. Sign receipts and acknowledgments for documents released to me by the above offices.",
             ("This authorization does not include the power to sign the applications, sworn statements or permits themselves, which I will sign "
              "personally, nor to sell, lease or encumber any property. It is valid from 14 September 2026 until 31 December 2026 unless sooner revoked in writing."),
             "", "", "", "<b>ALLAN VILLAFRIA INOCALLA</b>", "Principal · TIN 200-011-253 · ID: ______________________ No. ______________", "", "",
             "______________________________", "Representative (signature over printed name) · ID: ______________________ No. ______________",
             "", "(Attach photocopies of both IDs. Have it notarized if the receiving office requires a notarized SPA; a notarized Special Power of Attorney is needed for any act of signing on the principal's behalf.)"]})

# 8. Sworn declaration of capitalization (for the BPLO)
DOCS.append({"title": "8 · Sworn Declaration of Capitalization (for the Mayor's / Business Permit — new business)",
    "addr": ["REPUBLIC OF THE PHILIPPINES )", "PROVINCE OF CAMARINES NORTE ) S.S.", "MUNICIPALITY OF JOSE PANGANIBAN )", "", "SWORN DECLARATION OF CAPITAL INVESTMENT"],
    "subject": "",
    "body": [("I, <b>ALLAN VILLAFRIA INOCALLA</b>, of legal age, Filipino, with residence at Purok 4, Barangay Capacuan, Paracale, Camarines Norte, "
              "after having been duly sworn in accordance with law, depose and state:"),
             (f"1. That I am the proprietor of <b>{BN}</b>, registered with the Department of Trade and Industry under {DTI}, with business "
              f"address at {SITE};"),
             ("2. That the business is a new business applying for its first Mayor's / Business Permit with the Municipality of Jose Panganiban, "
              "and that under Section 143 of the Local Government Code the business tax for a newly started business is based on capital "
              "investment;"),
             ("3. That the total capital investment of the business as of the date of this declaration is <b>PESOS: FIVE HUNDRED THOUSAND "
              "(₱500,000.00)</b>, consisting of: land/site improvements (clearing, access, fencing on own land) ₱150,000.00; buildings and structures "
              "(office/store, equipment shed) ₱150,000.00; machinery and equipment (one locally fabricated concentrating table under fabrication and tools) "
              "₱100,000.00; working capital ₱100,000.00; others ₱0.00; that the land itself (Lot 4, 15.2069 hectares, OCT No. P-1616) is my own and is not "
              "counted as invested capital; and that the business is at present pre-operational (office and equipment yard), the processing plant "
              "(design 10 tonnes per day, under 10,000 tonnes per year) to operate only upon issuance of the required national permits, at which "
              "time an amended declaration will be filed;"),
             "4. That the business area to be used is five thousand (5,000) square meters, a portion of Lot 4, and the number of employees at start is three (3), to be hired preferentially from Barangay Santa Rosa Sur;",
             "5. That I execute this declaration to attest to the truth of the foregoing for the purpose of the assessment of business taxes and fees, and for whatever legal purpose it may serve.",
             "IN WITNESS WHEREOF, I have hereunto set my hand this 14th day of September 2026 at Jose Panganiban, Camarines Norte.",
             "", "", "", "<b>ALLAN VILLAFRIA INOCALLA</b>", "Affiant · TIN 200-011-253 · ID: ______________________ No. ______________", "",
             ("SUBSCRIBED AND SWORN to before me this 14th day of September 2026 at ______________, Camarines Norte, affiant exhibiting to me "
              "his ______________________ No. ______________ issued on __________ at __________."),
             "", "", "NOTARY PUBLIC", "Doc. No. ____; Page No. ____; Book No. ____; Series of 2026."]})

# ---------- DOCX ----------
doc = Document()
for s in doc.sections:
    s.top_margin = s.bottom_margin = Inches(0.9); s.left_margin = s.right_margin = Inches(1.0)
doc.styles['Normal'].font.name = 'Times New Roman'; doc.styles['Normal'].font.size = Pt(11.5)
def para(text, bold=False, align=None, size=None, space=6):
    p = doc.add_paragraph(); r = p.add_run(text.replace('<b>','').replace('</b>','')); r.bold = bold or text.startswith('<b>')
    if size: r.font.size = Pt(size)
    if align == 'c': p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif align == 'j': p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(space); return p
para("AVI GOLD PROCESSING PLANT — ANCILLARY REQUESTS BUNDLE (8 instruments) · DRAFT-HELD · prepared 13 September 2026 · dated for 14 September 2026", bold=True, align='c', size=11)
para("Contents: " + " | ".join(d["title"] for d in DOCS), align='j', size=9.5)
for d in DOCS:
    doc.add_page_break()
    for k, t in HEAD: para(t, bold=(k=='b'), align='c', size=(13 if k=='b' else 10), space=0)
    para(""); para(d["title"], bold=True, size=10, space=4)
    for t in d["addr"]: para(t, bold=(t.startswith("HON") or t.startswith("THE ") or t.isupper() and 5 < len(t) < 45), space=0)
    if d["subject"]: para(""); para(d["subject"], bold=True, align='j')
    para("")
    for t in d["body"]: para(t, align='j' if len(t) > 60 else None)
doc.save("AVI_ANCILLARY_REQUESTS_BUNDLE_2026-09.docx")

# ---------- PDF ----------
ss = getSampleStyleSheet()
J = ParagraphStyle('J', parent=ss['Normal'], fontName='Times-Roman', fontSize=11, leading=14.5, alignment=TA_JUSTIFY, spaceAfter=6)
L = ParagraphStyle('L', parent=J, alignment=0, spaceAfter=0)
C = ParagraphStyle('C', parent=J, alignment=TA_CENTER, spaceAfter=0, fontSize=10)
CB = ParagraphStyle('CB', parent=C, fontName='Times-Bold', fontSize=13)
B = ParagraphStyle('B', parent=J, fontName='Times-Bold')
T = ParagraphStyle('T', parent=J, fontName='Times-Bold', fontSize=10, textColor='#444444')
story = [Paragraph("AVI GOLD PROCESSING PLANT — ANCILLARY REQUESTS BUNDLE (8 instruments) · DRAFT-HELD · prepared 13 September 2026 · dated for 14 September 2026", B),
         Paragraph("Contents: " + " | ".join(d["title"] for d in DOCS), J)]
for d in DOCS:
    story.append(PageBreak())
    for k, t in HEAD: story.append(Paragraph(t, CB if k=='b' else C))
    story.append(Spacer(1, 8)); story.append(Paragraph(d["title"], T)); story.append(Spacer(1, 4))
    for t in d["addr"]:
        bold = t.startswith("HON") or t.startswith("THE ") or (t.isupper() and 5 < len(t) < 45)
        story.append(Paragraph(("<b>%s</b>" % t) if bold else (t or "&nbsp;"), L))
    if d["subject"]: story.append(Spacer(1, 8)); story.append(Paragraph(d["subject"], B))
    story.append(Spacer(1, 4))
    for t in d["body"]: story.append(Paragraph(t or "&nbsp;", J))
SimpleDocTemplate("AVI_ANCILLARY_REQUESTS_BUNDLE_2026-09.pdf", pagesize=A4, leftMargin=2.3*cm, rightMargin=2.3*cm, topMargin=2*cm, bottomMargin=2*cm).build(story)
print("built")
