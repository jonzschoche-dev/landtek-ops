# MGB Form 16-04 — CEMCRR application for AVI Gold Processing Plant (new plant) + sworn statement + cover letter. Run: python3 build.py
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.lib import colors

BN = "AVI GOLD PROCESSING PLANT"
SITE = "Lot 4, Psu-143364, OCT No. P-1616, Barangay Santa Rosa Sur, Jose Panganiban, Camarines Norte 4606"

# ---------- PAGE 1: the form (mirrors MGB Form 16-04 as filed in 2014, corpus doc 1280) ----------
form_head = ["Republic of the Philippines", "Department of Environment and Natural Resources", "MINES AND GEOSCIENCES BUREAU",
             "Regional Office No. V, Rawis, Legazpi City", "", "MGB Form No. 16-04", "",
             "APPLICATION FOR CERTIFICATE OF ENVIRONMENTAL MANAGEMENT AND COMMUNITY RELATIONS RECORD"]
form_fields = [
    ("Application No.", "____________________ (assigned by MGB RO-V)"),
    ("Applicant / Company", f"{BN} — Allan Villafria Inocalla, Proprietor (sole proprietorship; DTI Business Name No. 8480852, Regional – Region V, 11 Sep 2026 – 11 Sep 2031)"),
    ("Address", f"Plant: {SITE}.  Mailing: Purok 4, Barangay Capacuan, Paracale, Camarines Norte 4605"),
    ("Phone No.", "0917 155 4782"), ("Fax No.", "None"),
    ("E-mail", "shiraction2@gmail.com"),
    ("Contact Person(s)", "Mr. Allan V. Inocalla, Proprietor"),
    ("Purpose of Application", "[  ] EPA     [  ] SMP     [  ] MPSA     [  ] FTAA     [ X ] MPP (Mineral Processing Permit — new gold gravity-concentration plant, 10 tonnes/day design, mercury-free, cyanide-free)"),
]
rights_rows = [["", "Project", "Location", "Date Granted", "Commodity", "Status*"],
               ["1.", "Not applicable — no mining right, permit or contract has been granted to the applicant", "—", "—", "—", "—"],
               ["2.", "", "", "", "", ""], ["3.", "", "", "", "", ""]]
rights_note = "* Exploration / Development / Commercial Operation / Suspended / Rehabilitation / Others, please specify"
form_conditions = [
    ("In accordance with the provisions of the Philippine Mining Act of 1995 and the revised rules and regulations promulgated "
     "thereunder, the undersigned, for and in behalf of the above-cited applicant, hereby applies for a Certificate of Environmental "
     "Management and Community Relations Record subject to the following conditions:"),
    ("1. The statements made in this application or made later in support thereof shall be considered as conditions and essential parts "
     "of the Certificate that may be granted, and any omission of facts which may alter, change or affect substantially the facts set "
     "forth in said statements shall be sufficient cause for cancellation of the Certificate granted."),
    ("2. The applicant further binds itself to submit additional requirements should the Director and/or the Regional Director deem it "
     "necessary for purposes of determining its qualification for the grant of the Certificate being applied for."),
    "3. The application is filed for the exclusive use and benefit of the applicant and neither directly nor indirectly for the benefit of any person, corporation or partnership.",
    "4. The foregoing statements are hereby certified to be true to the best of the applicant's knowledge.",
    ("I, <b>ALLAN VILLAFRIA INOCALLA</b>, the person executing this application, hereby depose and say: That I have read or have caused the "
     "foregoing application to be read to me, that I thoroughly understand the same, and that each and every statement in said application "
     "is true and correct."),
    "", "", "BY:  <b>ALLAN VILLAFRIA INOCALLA</b>", "Applicant / Proprietor · TIN 200-011-253 · ID: ______________________ No. ______________", "",
    "<b>ACKNOWLEDGEMENT</b>",
    "Republic of the Philippines )   Province of Camarines Norte )   ______________________ ) S.S.",
    ("SUBSCRIBED AND SWORN to before me at the place aforesaid, this ____ day of ____________ 2026, the affiant exhibiting to me his "
     "______________________ No. ______________ issued on __________ at __________."),
    "", "", "NOTARY PUBLIC", "Doc. No. ____; Page No. ____; Book No. ____; Series of 2026.",
]
form_instructions = [
    "<b>INSTRUCTIONS (as printed on the form)</b>",
    "1. This application shall be accomplished in triplicate, one copy to be retained by the applicant and the remaining copies to be submitted to the MGB.",
    "2. All pertinent information required should be provided, inapplicable words cancelled and all blanks filled in. Any erasure would automatically deem this Application Form invalid.",
    "3. For applicants with mining rights in any area, a certification on the environmental management and community relations performance from the EMB and MGB Regional Office/s concerned should be attached.",
    "4. For applicants without previous/present resource-use ventures, a sworn statement stating among others the date of incorporation/registration and that it has not yet ventured into any resource extractive/use activity should be attached.",
    "5. Applications that lack the required attachments shall not be acted upon by the MGB.",
    "6. As per DAO 2005-08, an application fee of PhP 5,000.00 shall be paid by the applicant (plus PhP 20.00 PD 1856 documentary stamp per the MGB Citizen's Charter 2026). A photocopy of the Official Receipt must be attached; the original OR is presented upon claiming the CEMCRR or Certificate of Exemption.",
]

# ---------- PAGE 2: sworn statement (instruction 4) ----------
sworn = [
    "REPUBLIC OF THE PHILIPPINES )", "PROVINCE OF CAMARINES NORTE ) S.S.", "______________________ )", "",
    "<b>SWORN STATEMENT IN SUPPORT OF APPLICATION FOR CEMCRR / CERTIFICATE OF EXEMPTION</b>", "",
    ("I, <b>ALLAN VILLAFRIA INOCALLA</b>, of legal age, Filipino, born 12 January 1955 at Paracale, Camarines Norte, with residence at Purok 4, "
     "Barangay Capacuan, Paracale, Camarines Norte, after having been duly sworn in accordance with law, depose and state:"),
    (f"1. That I am the proprietor of <b>{BN}</b>, a sole proprietorship registered with the Department of Trade and Industry under Business "
     "Name No. 8480852 (Regional – Region V) on <b>11 September 2026</b>, valid until 11 September 2031;"),
    (f"2. That {BN} is a <b>new</b> mineral processing project — a mercury-free, cyanide-free gold gravity-concentration plant with a design "
     f"input of ten (10) tonnes of ore per day (below 10,000 tonnes per year) — to be established on a portion of {SITE}, an agricultural lot "
     "of 15.2069 hectares registered solely in my name under Free Patent No. 225537 (10 May 1963); that no structure of the plant has yet "
     "been built and no processing has been undertaken on the site;"),
    ("3. That neither I nor the business has ever been granted, nor presently holds, any Exploration Permit, Mineral Agreement, Financial or "
     "Technical Assistance Agreement, Quarry or Sand and Gravel Permit, Mineral Processing Permit, Small-Scale Mining Contract or other "
     "mining right in any area, and that the business has not ventured into any resource extractive or mineral resource use activity;"),
    ("4. That I undertake to comply with all environmental management and community relations obligations under RA No. 7942, RA No. 7076, "
     "DAO No. 2010-21, DAO No. 2022-03 and the conditions of the Environmental Compliance Certificate to be issued for the new plant, and to "
     "submit such additional documents as the Regional Director may require;"),
    ("5. That I execute this statement in support of my application for a Certificate of Environmental Management and Community Relations "
     "Record, or in the alternative a Certificate of Exemption therefrom, in connection with my application for a Mineral Processing Permit "
     "with MGB Regional Office No. V, and to attest to the truth of the foregoing."),
    "IN WITNESS WHEREOF, I have hereunto set my hand this ____ day of ____________ 2026 at ______________, Camarines Norte.",
    "", "", "", "<b>ALLAN VILLAFRIA INOCALLA</b>", "Affiant · TIN 200-011-253 · ID: ______________________ No. ______________", "",
    ("SUBSCRIBED AND SWORN to before me this ____ day of ____________ 2026 at ______________, Camarines Norte, affiant exhibiting to me his "
     "______________________ No. ______________ issued on __________ at __________."),
    "", "", "NOTARY PUBLIC", "Doc. No. ____; Page No. ____; Book No. ____; Series of 2026.",
]

# ---------- PAGE 3: cover letter to MGB RO-V ----------
cover = [
    f"<b>{BN}</b>", "Allan V. Inocalla, Proprietor", f"Plant site: {SITE} · Mailing: Purok 4, Brgy. Capacuan, Paracale, Camarines Norte 4605",
    "Mobile 0917 155 4782 · shiraction2@gmail.com · TIN 200-011-253", "",
    "____ September 2026", "",
    "<b>ENGR. GUILLERMO A. MOLINA JR. IV</b>", "Regional Director", "Mines and Geosciences Bureau, Regional Office No. V", "Rawis, Legazpi City", "",
    "Attention: Chief, Mine Safety, Environment and Social Development Division (MSESDD) / Mine Environmental Management Section", "",
    ("<b>SUBJECT: APPLICATION FOR CERTIFICATE OF ENVIRONMENTAL MANAGEMENT AND COMMUNITY RELATIONS RECORD (CEMCRR) — MGB FORM NO. 16-04 — "
     "AVI GOLD PROCESSING PLANT (NEW PLANT), BARANGAY SANTA ROSA SUR, JOSE PANGANIBAN, CAMARINES NORTE, IN CONNECTION WITH AN APPLICATION "
     "FOR A MINERAL PROCESSING PERMIT</b>"), "",
    "Sir:",
    ("I respectfully submit, in three (3) hard copies and one soft copy, my application on MGB Form No. 16-04 for a Certificate of "
     f"Environmental Management and Community Relations Record for <b>{BN}</b>, a new mercury-free gold gravity-concentration plant to be "
     "established on my own titled land at Barangay Santa Rosa Sur, Jose Panganiban, in connection with my forthcoming application for a "
     "Mineral Processing Permit with your Office (project cost below ₱200 million)."),
    ("No mining right, permit or contract has ever been granted to me or to the business, and the business has not ventured into any resource "
     "extractive activity; the attached sworn statement so states, in accordance with Instruction No. 4 of the form. Should your Office find "
     "that the applicant qualifies for a Certificate of Exemption in lieu of the CEMCRR, I respectfully request that the same be issued."),
    ("I undertake to pay the application fee of ₱5,000.00 and the ₱20.00 documentary stamp upon receipt of the Order of Payment, within seven "
     "(7) working days as provided in the MGB Citizen's Charter, and any registration or validation fee that may be assessed under DAO No. "
     "2005-08. Kindly acknowledge receipt on the enclosed copy, as the duly received application is an acceptance requirement of the "
     "Mineral Processing Permit application."),
    "Enclosures: (1) MGB Form No. 16-04, accomplished and notarized, in triplicate; (2) Sworn statement (Instruction No. 4); (3) DTI Certificate "
    "of Business Name Registration No. 8480852 and official receipt; (4) Certified true copy of OCT No. P-1616 (Lot 4, Psu-143364); "
    "(5) Location sketch of the plant site; (6) Project description (process, capacity, tailings management); (7) Two valid IDs.",
    "", "Respectfully,", "", "", "", "<b>ALLAN V. INOCALLA</b>", f"Proprietor, {BN}", "",
    "Received by: ______________________  Position: ______________  Date/Time: ______________",
]

# ---------- DOCX ----------
doc = Document()
for s in doc.sections:
    s.top_margin = s.bottom_margin = Inches(0.8); s.left_margin = s.right_margin = Inches(0.9)
doc.styles['Normal'].font.name = 'Times New Roman'; doc.styles['Normal'].font.size = Pt(11)
def para(text, bold=False, align=None, size=None, space=5):
    p = doc.add_paragraph(); r = p.add_run(text.replace('<b>','').replace('</b>','')); r.bold = bold or text.startswith('<b>')
    if size: r.font.size = Pt(size)
    if align == 'c': p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif align == 'j': p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(space); return p
for t in form_head: para(t, bold=(t.isupper() and len(t) > 3), align='c', space=0)
para("")
tbl = doc.add_table(rows=0, cols=2); tbl.style = 'Table Grid'
for k, v in form_fields:
    c = tbl.add_row().cells; c[0].text = k; c[1].text = v
para(""); para("List of Mining Rights Granted:", bold=True)
t2 = doc.add_table(rows=0, cols=6); t2.style = 'Table Grid'
for row in rights_rows:
    c = t2.add_row().cells
    for i, v in enumerate(row): c[i].text = v
para(rights_note, size=9); para("")
for t in form_conditions: para(t, align='j' if len(t) > 60 else None)
para("")
for t in form_instructions: para(t, align='j', size=9.5, space=2)
doc.add_page_break()
for t in sworn: para(t, align='j' if len(t) > 60 else None)
doc.add_page_break()
for t in cover: para(t, align='j' if len(t) > 60 else None)
doc.save("AVI_CEMCRR_FORM16-04_APPLICATION.docx")

# ---------- PDF ----------
ss = getSampleStyleSheet()
J = ParagraphStyle('J', parent=ss['Normal'], fontName='Times-Roman', fontSize=10.5, leading=13.5, alignment=TA_JUSTIFY, spaceAfter=5)
S = ParagraphStyle('S', parent=J, fontSize=9, leading=11, spaceAfter=2)
C = ParagraphStyle('C', parent=J, alignment=TA_CENTER, spaceAfter=0)
CB = ParagraphStyle('CB', parent=C, fontName='Times-Bold', fontSize=11.5)
B = ParagraphStyle('B', parent=J, fontName='Times-Bold')
def P(t, st=J): return Paragraph(t if t else "&nbsp;", st)
story = []
for t in form_head: story.append(P(t, CB if (t.isupper() and len(t) > 3) else C))
story.append(Spacer(1, 8))
ft = Table([[P("<b>%s</b>" % k, S), P(v, S)] for k, v in form_fields], colWidths=[4.2*cm, 12.3*cm])
ft.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.black), ('VALIGN', (0,0), (-1,-1), 'TOP')]))
story.append(ft); story.append(Spacer(1, 6)); story.append(P("<b>List of Mining Rights Granted:</b>"))
rt = Table([[P(c, S) for c in row] for row in rights_rows], colWidths=[0.8*cm, 6.7*cm, 3*cm, 2.3*cm, 2*cm, 1.7*cm])
rt.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.black), ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#eeeeee'))]))
story.append(rt); story.append(P(rights_note, S)); story.append(Spacer(1, 6))
for t in form_conditions: story.append(P(t))
story.append(Spacer(1, 6))
for t in form_instructions: story.append(P(t, S))
story.append(PageBreak())
for t in sworn: story.append(P(t))
story.append(PageBreak())
for t in cover: story.append(P(t))
SimpleDocTemplate("AVI_CEMCRR_FORM16-04_APPLICATION.pdf", pagesize=A4, leftMargin=2.2*cm, rightMargin=2.2*cm, topMargin=1.8*cm, bottomMargin=1.8*cm).build(story)
print("built")
