# Special Power of Attorney — Yohei Akihisa (Operator, Commercial Terms and Operations Agreement dated 2 June 2026) -> Allan Villafria Inocalla:
# take possession of the Annex A equipment and pursue every action to recover it. Owner + site left blank (fill by hand before notarization). Run: python3 build.py
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from reportlab.lib.units import inch, cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.lib import colors
LONG = (8.5*inch, 13*inch)  # PH long bond

B = "____________________"
EQUIP = [  # Annex A §2, transcribed as written (incl. "XIOAMI")
    ("1", "Wet Pan Mill", "1", "Henan Mingxin Machinery 1200", "Photo 1"),
    ("2", "Jaw Crusher", "1", "FTM PE200x300", "Photo 2"),
    ("3", "Excavator", "1", "YANMAR B27", "Photo 3"),
    ("4", "Boom Truck", "1", "ISUZU", "Photo 4"),
    ("5", "Elf Truck", "1", "ISUZU", "Photo 5"),
    ("6", "Road Roller", "1", "SAKAI", "Photo 6"),
    ("7", "Jack Hammer", "3", "YT4", "Photo 7"),
    ("8", "Tugger Hoist with motor", "2", "—", "Photo 8"),
    ("9", "Water Pump", "2", "(1) BX3615; (2) IW-407", "Photo 9"),
    ("10", "Diesel Engine", "1", "—", "Photo 10"),
    ("11", "Rod Mill", "4", "Milling Station", "Photo 11"),
    ("12", "CCTV", "3", "XIOAMI CW700S", "Photo 12"),
    ("13", "Welding Machine", "1", "—", "—"),
]

body = [
    ("c", "<b>SPECIAL POWER OF ATTORNEY</b>"), ("n", ""),
    ("j", (f"I, <b>YOHEI AKIHISA</b>, of legal age, citizen of {B}, Passport No. {B}, residing at {B}{B}{B}, "
           "appoint <b>ALLAN VILLAFRIA INOCALLA</b>, of legal age, Filipino, of Purok 4, Barangay Capacuan, Paracale, Camarines Norte, "
           "as my attorney-in-fact.")),
    ("j", ("<b>The equipment.</b> I am the Operator under the Commercial Terms and Operations Agreement dated 2 June 2026 with "
           "<b>JOVITO CU PALADO III</b> of Vinzons Avenue, Daet, Camarines Norte (the Owner), notarized at Daet, Camarines Norte as Doc. No. 143, "
           f"Page No. 30, Book No. 19, Series of 2026, for the site at {B}{B}{B}. I bought and paid for the equipment listed in Annex A of that Agreement "
           "(copied in Schedule 1 below; a copy of Annex A with its photo records, signature page and acknowledgment is attached), and it is mine, as the Owner acknowledged in Annex A. This power covers that equipment, any other equipment "
           "of mine at the site, and their parts, keys and papers (the \"Equipment\").")),
    ("j", "<b>Allan may, for me and in my name:</b>"),
    ("j", "1. Take possession of the Equipment, enter the site as the Agreement allows, and remove, transport and store the Equipment, with the help of the barangay and police if needed."),
    ("j", "2. Demand the return of the Equipment from the Owner or anyone holding it."),
    ("j", ("3. File and pursue any civil, criminal or administrative case to recover the Equipment or its value, including replevin, damages, and "
           "complaints for theft, estafa or carnapping; and sign all complaints, affidavits, verifications and certifications against forum shopping, post "
           "bonds, present my proof of purchase, and testify.")),
    ("j", "4. Represent me at barangay conciliation, mediation and pre-trial, with authority to make stipulations and to settle."),
    ("j", "5. Deal with the LTO, PNP and other government offices about the Equipment, including the boom truck and elf truck."),
    ("j", "6. Hire lawyers, and do everything else needed to carry out these powers."),
    ("j", ("<b>Costs.</b> All expenses are mine. Allan is not personally liable for anything he does in good faith under this power. "
           "<b>Term.</b> This power lasts until the Equipment is recovered and all cases are finished, unless I revoke it in writing.")),
    ("j", f"I confirm everything Allan lawfully does under this power. Signed on {B} at {B}."),
]
sig = [
    ("n", ""), ("n", ""), ("n", "<b>YOHEI AKIHISA</b>"), ("n", "Principal"), ("n", f"Passport No. {B}"), ("n", ""),
    ("n", "With my conformity:"), ("n", ""), ("n", ""), ("n", "<b>ALLAN VILLAFRIA INOCALLA</b>"), ("n", "Attorney-in-Fact"), ("n", ""),
    ("c", "SIGNED IN THE PRESENCE OF:"), ("n", ""),
    ("c", f"{B}{B}          {B}{B}"), ("n", ""),
]
ack = [
    ("c", "<b>ACKNOWLEDGMENT</b>"), ("n", ""),
    ("n", "REPUBLIC OF THE PHILIPPINES )"), ("n", f"{B} ) S.S."), ("n", ""),
    ("j", (f"BEFORE ME, a Notary Public for and in {B}, this {B}, personally appeared <b>YOHEI AKIHISA</b>, with Passport No. {B} "
           f"issued on {B} at {B}, and <b>ALLAN VILLAFRIA INOCALLA</b>, with {B} No. {B}, known to me (or identified through competent "
           "evidence of identity) to be the same persons who executed the foregoing Special Power of Attorney, and they acknowledged to me that "
           "it is their free and voluntary act and deed. This instrument, consisting of ____ pages including this page and Schedule 1, has been "
           "signed by the parties and their instrumental witnesses on each page.")),
    ("j", "WITNESS MY HAND AND SEAL on the date and at the place first above written."), ("n", ""), ("n", ""),
    ("n", "NOTARY PUBLIC"), ("n", ""),
    ("n", "Doc. No. ____;"), ("n", "Page No. ____;"), ("n", "Book No. ____;"), ("n", "Series of 2026."),
]
sched_head = [("c", "<b>SCHEDULE 1</b>"),
              ("c", "Equipment listed in Annex A (Equipment and Asset List) of the Commercial Terms and Operations Agreement dated 2 June 2026"),
              ("j", "Transcribed as written in Annex A. This list does not limit the Equipment covered by this power (see paragraph A).")]

def build_docx(path):
    doc = Document()
    for s in doc.sections:
        s.page_width = Inches(8.5); s.page_height = Inches(13)
        s.top_margin = Inches(0.65); s.bottom_margin = Inches(0.55); s.left_margin = s.right_margin = Inches(0.85)
    doc.styles['Normal'].font.name = 'Times New Roman'; doc.styles['Normal'].font.size = Pt(11)
    def para(k, t):
        p = doc.add_paragraph(); r = p.add_run(t.replace('<b>', '').replace('</b>', '')); r.bold = k == 'c' and t.startswith('<b>') or t.startswith('<b>') and len(t) < 60
        p.alignment = {'c': WD_ALIGN_PARAGRAPH.CENTER, 'j': WD_ALIGN_PARAGRAPH.JUSTIFY}.get(k, None)
        p.paragraph_format.space_after = Pt(5 if k == 'j' else 0); p.paragraph_format.space_before = Pt(0)
    for k, t in body + sig: para(k, t)
    doc.add_page_break()
    for k, t in ack: para(k, t)
    doc.add_page_break()
    for k, t in sched_head: para(k, t)
    tbl = doc.add_table(rows=1, cols=5); tbl.style = 'Table Grid'
    for c, h in zip(tbl.rows[0].cells, ["No.", "Equipment Description", "Qty", "Model / Serial No.", "Photo Ref"]): c.text = h
    for row in EQUIP:
        for c, v in zip(tbl.add_row().cells, row): c.text = v
    doc.save(path)

def build_pdf(path):
    ss = getSampleStyleSheet()
    J = ParagraphStyle('J', parent=ss['Normal'], fontName='Times-Roman', fontSize=11, leading=13.6, alignment=TA_JUSTIFY, spaceAfter=5)
    L = ParagraphStyle('L', parent=J, alignment=0, spaceAfter=0); C = ParagraphStyle('C', parent=J, alignment=TA_CENTER, spaceAfter=3)
    sty = {'c': C, 'j': J, 'n': L}
    from reportlab.platypus import PageBreak
    flow = [Paragraph(t or "&nbsp;", sty[k]) for k, t in body + sig] + [PageBreak()]
    flow += [Paragraph(t or "&nbsp;", sty[k]) for k, t in ack] + [PageBreak()]
    flow += [Paragraph(t, sty[k]) for k, t in sched_head] + [Spacer(1, 6)]
    T = ParagraphStyle('T', parent=L, fontSize=10, leading=12)
    data = [[Paragraph(f"<b>{h}</b>", T) for h in ["No.", "Equipment Description", "Qty", "Model / Serial No.", "Photo Ref"]]]
    data += [[Paragraph(v, T) for v in r] for r in EQUIP]
    t = Table(data, colWidths=[1.1*cm, 5.4*cm, 1.2*cm, 6.0*cm, 2.2*cm], repeatRows=1)
    t.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.black), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                           ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8e8e8'))]))
    flow.append(t)
    SimpleDocTemplate(path, pagesize=LONG, leftMargin=2.2*cm, rightMargin=2.2*cm, topMargin=1.8*cm, bottomMargin=1.6*cm).build(flow)

def attach(path):
    import fitz, glob
    from PIL import Image, ImageOps
    ROT = {"16.jpg": 270, "17.jpg": 270}  # notarial acknowledgment + Owner ID page were photographed sideways
    W, H = 8.5*72, 13*72; m = 36
    doc = fitz.open(path)
    sep = doc.new_page(width=W, height=H)
    sep.insert_textbox(fitz.Rect(m, H/2-80, W-m, H/2+80),
        "ATTACHMENT\n\nCopy of Annex A (Equipment and Asset List) with photo records, signature page, notarial acknowledgment "
        "(Doc. No. 143, Page No. 30, Book No. 19, Series of 2026, Daet, Camarines Norte) and the Owner's identification, "
        "of the Commercial Terms and Operations Agreement dated 2 June 2026", fontname="tiro", fontsize=12, align=1)
    files = sorted(glob.glob("attachments/*.jpg"))
    for i, f in enumerate(files, 1):
        im = ImageOps.exif_transpose(Image.open(f)).convert("RGB")
        r = ROT.get(f.split("/")[-1])
        if r: im = im.rotate(r, expand=True)
        tmp = f"/tmp/_att_{i}.jpg"; im.save(tmp, quality=85)
        pg = doc.new_page(width=W, height=H)
        pg.insert_text((m, m), f"Attachment page {i} of {len(files)}", fontname="tiro", fontsize=9)
        pg.insert_image(fitz.Rect(m, m+10, W-m, H-m), filename=tmp, keep_proportion=True)
    doc.saveIncr() if False else doc.save(path + ".tmp"); doc.close()
    import os; os.replace(path + ".tmp", path)

build_docx("SPA_YOHEI_AKIHISA_TO_ALLAN_INOCALLA_EQUIPMENT.docx"); build_pdf("SPA_YOHEI_AKIHISA_TO_ALLAN_INOCALLA_EQUIPMENT.pdf"); attach("SPA_YOHEI_AKIHISA_TO_ALLAN_INOCALLA_EQUIPMENT.pdf"); print("built")
