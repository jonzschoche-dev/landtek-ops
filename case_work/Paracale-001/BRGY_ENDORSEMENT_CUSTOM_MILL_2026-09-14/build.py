# Builds the request letter (EN) + draft Kapasyahan (FIL) as DOCX and PDF. Run: python3 build.py
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER

DATE = "14 September 2026"
BN = "AVI GOLD PROCESSING PLANT"
BN_NO = "DTI Business Name No. 8480852 (Regional – Region V), valid 11 September 2026 to 11 September 2031"

# ---------- LETTER (English) ----------
letter_head = [
    ("b", BN),
    ("n", "Allan V. Inocalla, Proprietor"),
    ("n", "Purok 4, Barangay Capacuan, Paracale, Camarines Norte 4605 (residence) · Plant site: Lot 4, Psu-143364, OCT No. P-1616, Barangay Santa Rosa Sur, Jose Panganiban, Camarines Norte 4606"),
    ("n", "Mobile 0917 155 4782  ·  shiraction2@gmail.com"),
]
letter_addr = [
    DATE, "",
    "HON. ______________________________",
    "Punong Barangay",
    "and the Members of the Sangguniang Barangay",
    "Barangay Santa Rosa Sur, Jose Panganiban, Camarines Norte",
    "",
    "Thru: The Barangay Secretary",
]
letter_subject = ("SUBJECT: REQUEST FOR A BARANGAY RESOLUTION ENDORSING THE APPLICATION OF AVI GOLD PROCESSING PLANT "
                  "FOR A CUSTOM MILL / MINERAL PROCESSOR'S LICENSE WITH THE PROVINCIAL MINING REGULATORY BOARD, "
                  "DENR–MGB REGION V AND THE MUNICIPAL GOVERNMENT OF JOSE PANGANIBAN, AND FOR THE DESIGNATION OF THE PLANT SITE "
                  "AS A MINERAL PROCESSING ZONE")
letter_body = [
    "Dear Punong Barangay and Honorable Kagawads:",
    ("I respectfully request the Sangguniang Barangay of Santa Rosa Sur to adopt a Resolution endorsing, and interposing no objection to, "
     "my application for a Custom Mill / Mineral Processor's License (mineral processing permit) for the operation of "
     f"<b>{BN}</b>, a gold processing plant to be established on my own titled land at Barangay Santa Rosa Sur, Jose Panganiban, Camarines Norte, "
     "to be filed with the Provincial Mining Regulatory Board of Camarines Norte through the DENR – Mines and Geosciences Bureau, "
     "Regional Office No. V, and with the Municipal Government of Jose Panganiban."),
    ("The plant site is Lot 4, Psu-143364, covered by Original Certificate of Title No. P-1616 of the Registry of Deeds for "
     "Camarines Norte (Free Patent No. 225537 issued 10 May 1963), an agricultural lot of 15.2069 hectares situated in this "
     "Barangay and registered solely in my name, Allan Villafria Inocalla. The plant will occupy only a portion of the lot. "
     f"The business is registered with the Department of Trade and Industry as {BN}, {BN_NO}. The plant is a new facility: "
     "its application for an Environmental Compliance Certificate with EMB Region V and its application for the mineral "
     "processing permit with MGB Region V are being prepared, and both require the endorsement of the host barangay and of the "
     "Sangguniang Bayan."),
    ("Under Republic Act No. 7076 (People's Small-Scale Mining Act of 1991) and DENR Administrative Order No. 2022-03, "
     "small-scale mineral processing is undertaken in custom mills within a Mineral Processing Zone designated by the local "
     "government unit upon the recommendation of the Provincial Mining Regulatory Board, under a Mineral Processor's License "
     "issued by the Board through MGB Region V. The Board and the Municipal Government look to the host barangay's resolution "
     "of endorsement as part of the application. The plant will serve the registered small-scale miners of Jose Panganiban and "
     "the Paracale–Jose Panganiban gold district, including the Minahang Bayan already declared in neighbouring Barangay Santa "
     "Rosa Norte and the Minahang Bayan applied for by the Capacuan Small-Scale Miners Association over the Inocalla properties "
     "in Paracale–Jose Panganiban (pending with MGB Region V and MGB Central Office since June 2026)."),
    "I therefore respectfully ask the Sangguniang Barangay to resolve:",
    ("1. To endorse and interpose no objection to the application of Allan V. Inocalla / AVI Gold Processing Plant for a "
     "Custom Mill / Mineral Processor's License for the processing plant on Lot 4, Psu-143364 (OCT No. P-1616), Barangay Santa "
     "Rosa Sur, before the Provincial Mining Regulatory Board of Camarines Norte, DENR–MGB Region V, and the Municipal "
     "Government of Jose Panganiban;"),
    ("2. To recommend to the Sangguniang Bayan of Jose Panganiban and to the Provincial Mining Regulatory Board the designation "
     "of the plant site on Lot 4, Psu-143364, Barangay Santa Rosa Sur as a Mineral Processing Zone under Section 15 of DAO No. "
     "2022-03, and to endorse the plant's Environmental Compliance Certificate application with EMB Region V;"),
    ("3. To issue the Barangay Business Clearance for AVI Gold Processing Plant under Section 152 of the Local Government Code; and"),
    ("4. To furnish certified copies of the Resolution to the undersigned, to the Sangguniang Bayan of Jose Panganiban, and to the "
     "Provincial Mining Regulatory Board / MGB Region V, Rawis, Legazpi City."),
    "In support of this request, I commit to the Barangay that the plant will:",
    ("(a) use gravity concentration only — no mercury at any stage, as required by DAO No. 2022-03, and no cyanide; "
     "(b) process only ore from registered small-scale miners and lawful mining-rights holders, and sell all gold produced to the "
     "Bangko Sentral ng Pilipinas or its accredited traders; (c) give preference in employment to residents of Barangay Santa Rosa Sur; "
     "(d) contain all tailings within the plant's lined tailings facility and comply with the conditions of the ECC, the Board's "
     "Potential Environmental Impact Management Plan, Community Development and Management Plan and Annual Safety and Health "
     "Program, and DAO No. 97-30 on small-scale mine safety; and (e) coordinate with the Barangay on any concern raised by residents."),
    ("A draft Resolution is attached for the Sanggunian's consideration, together with copies of the DTI Certificate of Business "
     "Name Registration, the certified true copy of OCT No. P-1616, and a sketch of the plant site."),
    "Thank you for your continued support of lawful, mercury-free processing for the small-scale miners of our Barangay.",
    "Respectfully yours,", "", "", "",
    "<b>ALLAN V. INOCALLA</b>",
    f"Proprietor, {BN}",
    "TIN 200-011-253",
    "",
    "Enclosures: (1) Draft Barangay Resolution; (2) DTI Certificate of Business Name Registration No. 8480852 and official receipt; "
    "(3) Certified true copy of OCT No. P-1616 (Lot 4, Psu-143364) and Tax Declaration; "
    "(4) Sketch plan of the plant site, Barangay Santa Rosa Sur; (5) Two valid IDs of the applicant.",
    "Received by: ______________________  Position: ______________  Date/Time: ______________",
]

# ---------- DRAFT KAPASYAHAN (Filipino, in the Sanggunian's own format) ----------
kap_head = [
    "Republika ng Pilipinas", "Lalawigan ng Camarines Norte", "Bayan ng Jose Panganiban", "Barangay SANTA ROSA SUR",
    "TANGGAPAN NG PUNONG BARANGAY", "",
    "SIPI NG KATITIKAN MULA SA ______________ NA PAGPUPULONG NG SANGGUNIANG BARANGAY NG SANTA ROSA SUR, JOSE PANGANIBAN, "
    "CAMARINES NORTE NA GINANAP NOONG IKA-____ NG ____________, 2026 SA BAHAY PULUNGAN NG BARANGAY SANTA ROSA SUR.",
    "",
    "DUMALO: ____________________________________________________________________________",
    "Liban: __________________",
    "",
]
kap_title = ("KAPASYAHAN BLG. ____ S-2026 — ISANG KAPASYAHAN NG SANGGUNIANG BARANGAY SANTA ROSA SUR NA NAG-EENDORSO AT WALANG "
             "TUTOL SA APLIKASYON NI G. ALLAN V. INOCALLA / AVI GOLD PROCESSING PLANT PARA SA CUSTOM MILL / MINERAL PROCESSOR'S "
             "LICENSE SA PROVINCIAL MINING REGULATORY BOARD (PMRB), DENR–MINES AND GEOSCIENCES BUREAU REGION V AT SA PAMAHALAANG "
             "BAYAN NG JOSE PANGANIBAN PARA SA PLANTA SA LOT 4, PSU-143364 (OCT BLG. P-1616), BARANGAY SANTA ROSA SUR, JOSE PANGANIBAN, "
             "CAMARINES NORTE, AT HINIHILING SA SANGGUNIANG BAYAN NG JOSE PANGANIBAN AT SA PMRB NA ITALAGA ANG NASABING LUGAR BILANG MINERAL PROCESSING ZONE")
kap_body = [
    ("SAPAGKAT, ayon sa RA 7076 o ang People's Small-Scale Mining Act of 1991, patakaran ng Estado na itaguyod, paunlarin, "
     "protektahan at gawing makatuwiran ang maliliit na aktibidad sa pagmimina upang makabuo ng mas maraming oportunidad sa "
     "trabaho at magbigay ng pantay na pagbabahagi ng likas na yaman ng bansa;"),
    ("SAPAGKAT, ayon sa DENR Administrative Order Blg. 2022-03 (Revised Implementing Rules and Regulations ng RA 7076), Seksyon 14 "
     "at 15, ang pagpoproseso ng mineral ng maliliit na minero ay isasagawa lamang sa loob ng Mineral Processing Zone na itinatalaga "
     "ng pamahalaang lokal sa rekomendasyon ng Provincial Mining Regulatory Board, sa ilalim ng Mineral Processor's License na "
     "ipinagkakaloob ng Lupon sa pamamagitan ng MGB Regional Office, at ipinagbabawal ang paggamit ng mercury sa anumang yugto nito;"),
    ("SAPAGKAT, may idineklara nang Minahang Bayan sa karatig na Barangay Santa Rosa Norte ng bayang ito (2024), at nakabinbin sa "
     "MGB Region V at MGB Central Office ang aplikasyon ng Capacuan Small-Scale Miners Association para sa Minahang Bayan sa mga "
     "lupang Inocalla sa Paracale–Jose Panganiban (Hunyo 2026), na nangangailangan ng lehitimo at mercury-free na custom mill;"),
    ("SAPAGKAT, si G. Allan V. Inocalla, may-ari ng Lot 4, Psu-143364 na sakop ng Original Certificate of Title Blg. P-1616 "
     "(Free Patent Blg. 225537, ika-10 ng Mayo 1963), 15.2069 ektarya, na matatagpuan sa Barangay na ito at nakatala sa kaniyang "
     "pangalan lamang, ay nag-aaplay ng Custom Mill / Mineral Processor's License para sa bagong planta ng pagpoproseso ng ginto "
     "na AVI GOLD PROCESSING PLANT (DTI Business Name Blg. 8480852) sa bahagi ng nasabing lote, at inihahanda ang aplikasyon "
     "nito sa Environmental Compliance Certificate sa EMB Region V, upang magsilbi sa mga rehistradong maliliit na minero ng "
     "Barangay at ng karatig-pook;"),
    ("SAPAGKAT, nangako ang aplikante na gagamit lamang ng gravity concentration at hindi gagamit ng mercury o cyanide, "
     "magbibigay ng prayoridad sa trabaho sa mga residente ng Barangay Santa Rosa Sur, ipagbibili ang lahat ng ginto sa Bangko Sentral "
     "ng Pilipinas o sa mga akreditadong mamimili nito, at susunod sa mga kondisyon ng ECC at sa mga alituntunin ng PMRB at ng "
     "DAO 97-30 hinggil sa kaligtasan;"),
    ("SAPAGKAT, ang isang lehitimo at mercury-free na custom mill sa loob ng Barangay ay makatutulong sa kabuhayan, kalusugan "
     "at kaligtasan ng mga residente at sa pangangalaga ng kapaligiran;"),
    ("KUNG KAYA'T, matapos ang masusing talakayan ng Sangguniang Barangay ng Santa Rosa Sur, iminungkahi ni Kgd. ______________________ "
     "at pinangalawahan ni Kgd. ______________________, na:"),
    ("NAPAGPASYAHAN, na i-endorso at ipahayag ang walang tutol ng Sangguniang Barangay ng Santa Rosa Sur sa aplikasyon ni G. Allan "
     "V. Inocalla / AVI Gold Processing Plant para sa Custom Mill / Mineral Processor's License para sa planta sa Lot 4, Psu-143364 "
     "(OCT Blg. P-1616), Barangay Santa Rosa Sur, Jose Panganiban, Camarines Norte, sa harap ng Provincial Mining Regulatory Board "
     "ng Camarines Norte, DENR–MGB Region V, at ng Pamahalaang Bayan ng Jose Panganiban, at gayundin ang aplikasyon nito sa "
     "Environmental Compliance Certificate sa EMB Region V;"),
    ("NAPAGPASYAHAN PA, na hilingin sa Sangguniang Bayan ng Jose Panganiban at sa Provincial Mining Regulatory Board na italaga "
     "ang nasabing lugar ng planta sa Lot 4, Psu-143364, Barangay Santa Rosa Sur bilang Mineral Processing Zone alinsunod sa "
     "Seksyon 15 ng DAO 2022-03;"),
    ("NAPAGPASYAHAN PA, na ipagkaloob kay G. Allan V. Inocalla / AVI Gold Processing Plant ang Barangay Business Clearance "
     "alinsunod sa Seksyon 152 ng RA 7160, sa pagbabayad ng kaukulang bayarin;"),
    ("NAPAGPASYAHAN SA WAKAS, na padalhan ng sipi ng Kapasyahang ito ang aplikante, ang Sangguniang Bayan ng Jose Panganiban, ang "
     "Tanggapan ng Punong Bayan ng Jose Panganiban, at ang Provincial Mining Regulatory Board / DENR-MGB Region V, Rawis, Legazpi City, "
     "para sa kanilang kaalaman at angkop na aksyon."),
    "NAPAGPASYAHAN AT SINANG-AYUNAN NG LAHAT.",
    "",
    "Pinatutunayan ko ang kawastuhan ng kapasyahang ito.",
    "", "",
    "______________________________", "Kalihim sa Sanggunian", "", "",
    "Pinagtibay ni:", "", "",
    "HON. ______________________________", "Punong Barangay", "",
    "SINANG-AYUNAN NG MGA KAGAWAD:", "",
    "HON. ______________________________, Brgy. Kagawad        HON. ______________________________, Brgy. Kagawad",
    "HON. ______________________________, Brgy. Kagawad        HON. ______________________________, Brgy. Kagawad",
    "HON. ______________________________, Brgy. Kagawad        HON. ______________________________, Brgy. Kagawad",
    "HON. ______________________________, Brgy. Kagawad        HON. ______________________________, SK Chairperson",
    "",
    "(Draft na inihanda ng aplikante para sa konsiderasyon ng Sanggunian; pakilagay ang pangalan ng mga opisyal at ang bilang "
    "ng Kapasyahan.)",
]

# ---------- DOCX ----------
doc = Document()
for s in doc.sections:
    s.top_margin = s.bottom_margin = Inches(0.9); s.left_margin = s.right_margin = Inches(1.0)
st = doc.styles['Normal']; st.font.name = 'Times New Roman'; st.font.size = Pt(11.5)
def para(text, bold=False, align=None, size=None, space=6):
    p = doc.add_paragraph(); r = p.add_run(text.replace('<b>','').replace('</b>','')); r.bold = bold or text.startswith('<b>')
    if size: r.font.size = Pt(size)
    if align == 'c': p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif align == 'j': p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(space); return p
for kind, t in letter_head: para(t, bold=(kind=='b'), align='c', size=(13 if kind=='b' else 10.5), space=0)
para(""); 
for t in letter_addr: para(t, bold=t.isupper() and t.startswith("HON"), space=0)
para(""); para(letter_subject, bold=True, align='j'); para("")
for t in letter_body: para(t, align='j')
doc.add_page_break()
for t in kap_head: para(t, bold=t.isupper() and len(t) < 40, align='c' if len(t) < 40 else 'j', space=0)
para(kap_title, bold=True, align='j'); para("")
for t in kap_body: para(t, align='j' if len(t) > 60 else None, bold=(t.isupper() and 5 < len(t) < 40))
doc.save("BRGY_SANTA_ROSA_SUR_ENDORSEMENT_REQUEST_CUSTOM_MILL_2026-09-14.docx")

# ---------- PDF ----------
ss = getSampleStyleSheet()
J = ParagraphStyle('J', parent=ss['Normal'], fontName='Times-Roman', fontSize=11, leading=14.5, alignment=TA_JUSTIFY, spaceAfter=6)
L = ParagraphStyle('L', parent=J, alignment=0, spaceAfter=0)
C = ParagraphStyle('C', parent=J, alignment=TA_CENTER, spaceAfter=0)
CB = ParagraphStyle('CB', parent=C, fontName='Times-Bold', fontSize=13)
B = ParagraphStyle('B', parent=J, fontName='Times-Bold')
story = []
for kind, t in letter_head: story.append(Paragraph(t, CB if kind=='b' else C))
story.append(Spacer(1, 10))
for t in letter_addr: story.append(Paragraph(("<b>%s</b>" % t) if t.startswith("HON") else t, L))
story.append(Spacer(1, 8)); story.append(Paragraph(letter_subject, B)); story.append(Spacer(1, 4))
for t in letter_body: story.append(Paragraph(t if t else "&nbsp;", J))
story.append(PageBreak())
for t in kap_head: story.append(Paragraph(("<b>%s</b>" % t) if (t.isupper() and len(t) < 40) else (t or "&nbsp;"), C if len(t) < 40 else J))
story.append(Spacer(1, 6)); story.append(Paragraph(kap_title, B)); story.append(Spacer(1, 4))
for t in kap_body: story.append(Paragraph(("<b>%s</b>" % t) if (t.isupper() and 5 < len(t) < 40) else (t or "&nbsp;"), J))
SimpleDocTemplate("BRGY_SANTA_ROSA_SUR_ENDORSEMENT_REQUEST_CUSTOM_MILL_2026-09-14.pdf", pagesize=A4,
                  leftMargin=2.3*cm, rightMargin=2.3*cm, topMargin=2*cm, bottomMargin=2*cm).build(story)
print("built")
