# Authorization letter (not notarized) — Allan V. Inocalla (own name + as CSSMA President) -> Marlon Malaluan: inquire / request / receive at MGB-V, DENR EMB-V, DENR Surveys & Mapping. Records only; everything surrendered to Allan. Run: python3 build.py
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from reportlab.lib.units import inch
LONG = (8.5*inch, 13*inch)  # PH long bond
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER

B = "____________________"
spa = [
    ("c", "<b>AUTHORIZATION</b>"), ("n", ""),
    ("n", "Date: 5 October 2026"), ("n", ""),
    ("j", "TO: The Mines and Geosciences Bureau, Regional Office No. V; the DENR Environmental Management Bureau, Regional Office No. V; the Surveys and Mapping Division, DENR Regional Office No. V; and the National Commission on Indigenous Peoples (NCIP), Regional Office No. V and Provincial Office of Camarines Norte — and to whom it may concern:"),
    ("j", ("I, <b>ALLAN VILLAFRIA INOCALLA</b>, of legal age, Filipino, with address at Purok 4, Barangay Capacuan, Paracale, Camarines Norte, "
           "acting in my own name and as President and authorized representative of the <b>CAPACUAN SMALL-SCALE MINERS ASSOCIATION</b> "
           "(DOLE Registration No. R0500-CN-0417-019-17), hereby authorize <b>MARLON MALALUAN</b>, of legal age, Filipino, with address at "
           f"{B}{B}, as my representative, for me and in my name and in the name of the Association, to do the following acts <b>only</b>:")),
    ("j", ("1. <b>Mines and Geosciences Bureau.</b> To appear before the Mines and Geosciences Bureau, Regional Office No. V, and the Provincial Mining "
           "Regulatory Board of Camarines Norte, to inquire into the status of the Association's application for the declaration of a "
           "<b>Minahang Bayan</b> at Barangay Capacuan, Paracale, Camarines Norte (as filed and as may be amended); and to request, pay the lawful fees for, "
           "and receive certified or plain copies of the <b>map(s), sketch plan(s), technical description(s), land-status / tenement overlay</b>, "
           "and any other record, order, notice or correspondence pertaining to that application or to my mining interests.")),
    ("j", ("2. <b>DENR Environmental Management Bureau.</b> To appear before the Environmental Management Bureau, Regional Office No. V, to inquire "
           "into, follow up, and receive copies of records, notices and correspondence pertaining to any environmental application, permit, "
           "certificate or compliance matter filed by me or by the Association.")),
    ("j", ("3. <b>DENR Surveys and Mapping.</b> To appear before the Surveys and Mapping Division of the DENR Regional Office No. V and the "
           "PENRO / CENRO having jurisdiction, to request, pay the lawful fees for, and receive certified copies of survey plans, technical descriptions, "
           "land-classification maps, cadastral and lot data, and verification or certification of any parcel in which I or the Association have an interest.")),
    ("j", ("4. <b>National Commission on Indigenous Peoples.</b> To appear before the NCIP Regional Office No. V and the NCIP Provincial Office "
           "of Camarines Norte, to inquire into the status of, and to request, pay the lawful fees for, and receive copies of any Certificate of "
           "Non-Overlap, Certification Precondition, field-based investigation report, ancestral-domain map or CADT/CALT data, and any FPIC-related "
           "record or correspondence pertaining to the Minahang Bayan area or any other area in which I or the Association have an interest.")),
    ("j", ("5. <b>Surrender of all documents.</b> Every document, map, plan, receipt and copy that my representative receives under this authorization "
           "is received <b>for me and on my behalf, and shall be surrendered to me, ALLAN V. INOCALLA, in full and without delay</b>, together with "
           "the official receipts for any fees paid. My representative shall keep no copy, and shall not show, give or transmit any of them to any "
           "other person, without my prior written consent.")),
    ("j", ("6. <b>Limits.</b> This authorization is limited to inquiring, requesting, following up and receiving. It does <b>not</b> authorize my representative "
           "to sign, file, amend or withdraw any application, petition or document; to give consent (including any FPIC consent), waiver or undertaking; to receive any payment; "
           "or to enter into any agreement or commitment for me or for the Association. Any such act is void as against me unless I sign it myself.")),
    ("j", (f"7. <b>Term.</b> This authorization is valid until <b>31 December 2026</b> unless I revoke it earlier in writing. Notice of revocation given to the office "
           "concerned is effective as to that office upon receipt.")),
    ("j", "Please extend to him the courtesy of your office. He will present a valid ID together with this authorization and a copy of my ID."),
    ("n", ""), ("n", ""),
    ("n", "<b>ALLAN VILLAFRIA INOCALLA</b>"), ("n", "In his own name and as President, Capacuan Small-Scale Miners Association"),
    ("n", "Purok 4, Barangay Capacuan, Paracale, Camarines Norte · TIN 200-031-253"),
    ("n", "Mobile 0917 155 4782 · shiraction2@gmail.com"), ("n", ""),
    ("n", "CONFORME — I accept this authorization and its limits, including the duty to surrender all documents to Allan V. Inocalla:"), ("n", ""), ("n", ""), ("n", ""),
    ("n", "<b>MARLON MALALUAN</b>"), ("n", "Authorized Representative"), ("n", f"ID: {B} No. {B}"),
]

def build_docx(path):
    doc = Document()
    for s in doc.sections:
        s.page_width = Inches(8.5); s.page_height = Inches(13)
        s.top_margin = Inches(0.65); s.bottom_margin = Inches(0.55); s.left_margin = s.right_margin = Inches(0.85)
    doc.styles['Normal'].font.name = 'Times New Roman'; doc.styles['Normal'].font.size = Pt(10)
    for k, t in spa:
        p = doc.add_paragraph(); r = p.add_run(t.replace('<b>','').replace('</b>','')); r.bold = k == 'c' or t.startswith('<b>')
        p.alignment = {'c': WD_ALIGN_PARAGRAPH.CENTER, 'j': WD_ALIGN_PARAGRAPH.JUSTIFY}.get(k, None)
        p.paragraph_format.space_after = Pt(4 if k == 'j' else 0); p.paragraph_format.space_before = Pt(0)
    doc.save(path)

def build_pdf(path):
    ss = getSampleStyleSheet()
    J = ParagraphStyle('J', parent=ss['Normal'], fontName='Times-Roman', fontSize=10.4, leading=12.9, alignment=TA_JUSTIFY, spaceAfter=4.5)
    L = ParagraphStyle('L', parent=J, alignment=0, spaceAfter=0); C = ParagraphStyle('C', parent=J, alignment=TA_CENTER, spaceAfter=4)
    sty = {'c': C, 'j': J, 'n': L}
    SimpleDocTemplate(path, pagesize=LONG, leftMargin=2.2*cm, rightMargin=2.2*cm, topMargin=1.6*cm, bottomMargin=1.4*cm).build(
        [Paragraph(t or "&nbsp;", sty[k]) for k, t in spa])

build_docx("AUTHORIZATION_ALLAN_TO_MARLON_MALALUAN_MGB_DENR.docx"); build_pdf("AUTHORIZATION_ALLAN_TO_MARLON_MALALUAN_MGB_DENR.pdf"); print("built")
