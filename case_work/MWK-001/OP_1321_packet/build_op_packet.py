#!/usr/bin/env python3
"""Bind the OP petition packet for CTN SL-2026-0209-1321 — 8.5x13 throughout.
Petition + Index of Annexes + Annexes A-G, every annex page stamped."""
import io, os, re
from pypdf import PdfReader, PdfWriter, Transformation, PageObject
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.lib.colors import Color, black
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
MWK = os.path.dirname(HERE)
SRC = os.path.join(HERE, "source")
FOLIO = (8.5 * 72, 13.0 * 72)

F = "/System/Library/Fonts/Supplemental"
pdfmetrics.registerFont(TTFont("TNR", f"{F}/Times New Roman.ttf"))
pdfmetrics.registerFont(TTFont("TNR-Bold", f"{F}/Times New Roman Bold.ttf"))
pdfmetrics.registerFont(TTFont("TNR-Italic", f"{F}/Times New Roman Italic.ttf"))
pdfmetrics.registerFont(TTFont("TNR-BoldItalic", f"{F}/Times New Roman Bold Italic.ttf"))
pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-Bold",
                              italic="TNR-Italic", boldItalic="TNR-BoldItalic")


def md_to_rl(s):
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", s, flags=re.S)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s, flags=re.S)
    s = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", s, flags=re.S)
    return s


BASE = dict(fontName="TNR", fontSize=11.5, leading=15, spaceAfter=8, alignment=TA_JUSTIFY)
S = {
    "h1": ParagraphStyle("h1", fontName="TNR-Bold", fontSize=14.5, leading=18, alignment=TA_CENTER, spaceBefore=4, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName="TNR-Bold", fontSize=12.5, leading=16, spaceBefore=8, spaceAfter=5),
    "h3": ParagraphStyle("h3", fontName="TNR-Bold", fontSize=11.5, leading=15, spaceBefore=6, spaceAfter=4),
    "body": ParagraphStyle("body", **BASE),
    "addr": ParagraphStyle("addr", **{**BASE, "alignment": TA_LEFT, "spaceAfter": 0, "leading": 14.5}),
    "re": ParagraphStyle("re", **{**BASE, "alignment": TA_LEFT, "leftIndent": 0.5 * inch, "spaceBefore": 6, "spaceAfter": 10}),
    "num": ParagraphStyle("num", **{**BASE, "leftIndent": 0.5 * inch, "spaceAfter": 5}),
    "bullet": ParagraphStyle("bullet", **{**BASE, "leftIndent": 0.4 * inch, "bulletIndent": 0.18 * inch, "spaceAfter": 5}),
    "cell": ParagraphStyle("cell", fontName="TNR", fontSize=8.6, leading=11),
    "sig": ParagraphStyle("sig", **{**BASE, "alignment": TA_LEFT, "spaceAfter": 0, "leading": 14.5}),
    "encl": ParagraphStyle("encl", **{**BASE, "fontSize": 10, "leading": 12.8}),
}


def render_md(md_path, out_path, footer, letter_mode=False):
    lines = open(md_path).read().split("\n")
    story, i = [], 0
    in_addr = letter_mode
    while i < len(lines):
        raw = lines[i].rstrip()
        if not raw.strip():
            i += 1
            continue
        if raw.startswith("> **INTERNAL"):
            break  # strip internal block from filings
        if in_addr:
            if raw.startswith("Dear "):
                in_addr = False
                story.append(Spacer(1, 8))
                story.append(Paragraph(md_to_rl(raw), S["body"]))
                i += 1
                continue
            if raw.startswith("Re:"):
                block = [raw]
                i += 1
                while i < len(lines) and lines[i].strip():
                    block.append(lines[i].strip())
                    i += 1
                story.append(Spacer(1, 6))
                story.append(Paragraph(md_to_rl(" ".join(block)), S["re"]))
                continue
            story.append(Paragraph(md_to_rl(raw), S["addr"]))
            if raw.startswith("___ September") or raw.startswith("*Copy furnished"):
                story.append(Spacer(1, 12))
            i += 1
            continue
        if raw.startswith("# "):
            story.append(Paragraph(md_to_rl(raw[2:]), S["h1"]))
            i += 1
            continue
        if raw.startswith("## "):
            story.append(Paragraph(md_to_rl(raw[3:]), S["h2"]))
            i += 1
            continue
        if raw.startswith("### "):
            story.append(Paragraph(md_to_rl(raw[4:]), S["h3"]))
            i += 1
            continue
        if raw.strip() == "---":
            story.append(Spacer(1, 8))
            i += 1
            continue
        if raw.lstrip().startswith("|"):
            tbl = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                tbl.append(lines[i].strip())
                i += 1
            rows = []
            for tl in tbl:
                cells = [c.strip() for c in tl.strip("|").split("|")]
                if all(re.fullmatch(r"-{3,}:?|:-{2,}:?", c) for c in cells if c):
                    continue
                rows.append([Paragraph(md_to_rl(c), S["cell"]) for c in cells])
            if rows:
                n = len(rows[0])
                widths = {2: [1.5 * inch, 5.0 * inch], 3: [1.7 * inch, 2.2 * inch, 2.7 * inch]}.get(n)
                t = Table(rows, colWidths=widths, repeatRows=1)
                t.setStyle(TableStyle([
                    ("GRID", (0, 0), (-1, -1), 0.5, black),
                    ("BACKGROUND", (0, 0), (-1, 0), Color(0.93, 0.93, 0.93)),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
                story.append(Spacer(1, 4))
                story.append(t)
                story.append(Spacer(1, 6))
            continue
        if raw.lstrip().startswith("- "):
            story.append(Paragraph(md_to_rl(raw.lstrip()[2:]), S["bullet"], bulletText="•"))
            i += 1
            continue
        if raw.lstrip().startswith("> "):
            block = [raw.lstrip()[2:]]
            i += 1
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                block.append(lines[i].lstrip().lstrip(">").strip())
                i += 1
            story.append(Paragraph(md_to_rl(" ".join(b for b in block if b)),
                                   ParagraphStyle("q", **{**BASE, "leftIndent": 0.4 * inch, "rightIndent": 0.25 * inch, "fontName": "TNR-Italic"})))
            continue
        m = re.match(r"^\s{2,}(\d+|[a-z]|[ivx]+)[\.\)]\s+(.*)$", raw)
        if m:
            txt = m.group(2)
            i += 1
            while i < len(lines) and lines[i].strip() and lines[i].startswith("  ") and not re.match(r"^\s{2,}(\d+|[a-z]|[ivx]+)[\.\)]\s", lines[i]):
                txt += " " + lines[i].strip()
                i += 1
            story.append(Paragraph(f"<b>{m.group(1)}.</b> " + md_to_rl(txt), S["num"]))
            continue
        block = [raw.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].lstrip().startswith(("|", "- ", "#", ">")) \
                and lines[i].strip() != "---" and not re.match(r"^\s{2,}(\d+|[a-z]|[ivx]+)[\.\)]\s", lines[i]):
            block.append(lines[i].strip())
            i += 1
        text = " ".join(block)
        if text.startswith("*Annexes:*"):
            story.append(Spacer(1, 6))
            story.append(Paragraph(md_to_rl(text), S["encl"]))
        elif text.startswith("Respectfully,"):
            story.append(Spacer(1, 4))
            story.append(Paragraph("Respectfully,", S["sig"]))
            story.append(Spacer(1, 34))
        elif text.startswith("**JONATHAN PAUL ZSCHOCHE**"):
            for part in ["**JONATHAN PAUL ZSCHOCHE**", "Attorney-in-Fact for Patricia Keesey Zschoche",
                         "Heir, Estate of Mary Worrick Keesey",
                         "Dasmariñas Street, Barangay 8, Daet, Camarines Norte",
                         "jonzschoche@gmail.com · 0966-698-1448"]:
                story.append(Paragraph(md_to_rl(part), S["sig"]))
            story.append(Spacer(1, 8))
        else:
            story.append(Paragraph(md_to_rl(text), S["body"]))

    class NC(pdfcanvas.Canvas):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._saved = []

        def showPage(self):
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            n = len(self._saved)
            for st in self._saved:
                self.__dict__.update(st)
                if n > 1:
                    self.setFont("TNR", 9)
                    self.drawCentredString(FOLIO[0] / 2, 0.5 * inch, f"Page {self._pageNumber} of {n}")
                    self.setFont("TNR-Italic", 7.5)
                    self.drawCentredString(FOLIO[0] / 2, 0.36 * inch, footer)
                super().showPage()
            super().save()

    doc = SimpleDocTemplate(out_path, pagesize=FOLIO, leftMargin=1.0 * inch, rightMargin=1.0 * inch,
                            topMargin=0.9 * inch, bottomMargin=0.85 * inch, title=footer)
    doc.build(story, canvasmaker=NC)
    return out_path


def normalize(pg, rot=0):
    pw, ph = float(pg.mediabox.width), float(pg.mediabox.height)
    if rot == 0 and pw > ph:
        rot = 90
    tgt = PageObject.create_blank_page(width=FOLIO[0], height=FOLIO[1])
    t = Transformation()
    if rot == 90:
        t = t.rotate(90).translate(ph, 0)
        pw, ph = ph, pw
    s = min(FOLIO[0] / pw, FOLIO[1] / ph)
    t = t.scale(s).translate((FOLIO[0] - pw * s) / 2, (FOLIO[1] - ph * s) / 2)
    tgt.merge_transformed_page(pg, t)
    return tgt


def stamp(pg, label):
    pw, ph = float(pg.mediabox.width), float(pg.mediabox.height)
    ov = io.BytesIO()
    c = pdfcanvas.Canvas(ov, pagesize=(pw, ph))
    text = f'ANNEX "{label}"'
    fs = 13
    pad = fs * 0.5
    c.setFont("Helvetica-Bold", fs)
    tw = c.stringWidth(text, "Helvetica-Bold", fs)
    bw, bh = tw + 2 * pad, fs + 2 * pad
    m = 18
    x, y = pw - bw - m, m
    c.setFillColor(Color(1, 1, 1, alpha=0.85))
    c.setStrokeColor(black)
    c.setLineWidth(1.3)
    c.roundRect(x, y, bw, bh, radius=3, stroke=1, fill=1)
    c.setFillColor(black)
    c.drawCentredString(x + bw / 2, y + pad, text)
    c.showPage()
    c.save()
    ov.seek(0)
    pg.merge_page(PdfReader(ov).pages[0])
    return pg


def jpeg_to_pdf_page(jpg_path):
    img = Image.open(jpg_path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "PDF")
    buf.seek(0)
    return PdfReader(buf).pages[0]


def index_page(entries):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=FOLIO, leftMargin=1.0 * inch, rightMargin=1.0 * inch,
                            topMargin=1.0 * inch, bottomMargin=0.9 * inch)
    st = [Paragraph("INDEX OF ANNEXES", S["h1"]),
          Paragraph("Petition for Supervisory Review and Corrective Action — ARTA CTN SL-2026-0209-1321<br/>(Zschoche v. Abla, Municipal Assessor, Mercedes, Camarines Norte)", ParagraphStyle("sub", fontName="TNR", fontSize=11, leading=14, alignment=TA_CENTER, spaceAfter=14))]
    rows = [[Paragraph("<b>Annex</b>", S["cell"]), Paragraph("<b>Document</b>", S["cell"]), Paragraph("<b>Pages</b>", S["cell"])]]
    for letter, desc, pages in entries:
        rows.append([Paragraph(f'"{letter}"', S["cell"]), Paragraph(desc, S["cell"]), Paragraph(str(pages), S["cell"])])
    t = Table(rows, colWidths=[0.7 * inch, 5.2 * inch, 0.7 * inch])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, black),
        ("BACKGROUND", (0, 0), (-1, 0), Color(0.92, 0.92, 0.92)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    st.append(t)
    st.append(Spacer(1, 8))
    st.append(Paragraph("Each annex page carries a boxed ANNEX label at the lower right.", S["body"]))
    doc.build(st)
    buf.seek(0)
    return PdfReader(buf)


def main():
    # 1) render petition + Annex B + Annex D
    pet_pdf = render_md(os.path.join(MWK, "OP_PETITION_1321_2026-09.md"),
                        os.path.join(HERE, "petition.pdf"),
                        "Zschoche — Petition for Supervisory Review, ARTA CTN SL-2026-0209-1321", letter_mode=True)
    axb_pdf = render_md(os.path.join(HERE, "AnnexB_comparator.md"),
                        os.path.join(HERE, "AnnexB_comparator.pdf"),
                        'Annex "B" — Comparator Exhibit (CTN SL-2026-0209-1321)')
    axd_pdf = render_md(os.path.join(HERE, "AnnexD_email.md"),
                        os.path.join(HERE, "AnnexD_email.pdf"),
                        'Annex "D" — Email of 1 October 2025')

    # 2) trim resolution to the resolution proper (11 pp)
    r = PdfReader(os.path.join(SRC, "AnnexA_resolution_part1.pdf"))
    axa_pages = [r.pages[i] for i in range(11)]

    annexes = [
        ("A", "ARTA Resolution dated 25 August 2026 (resolution proper; annexes of record with ARTA), as received 27 August 2026", [("pages", axa_pages)]),
        ("B", "Comparator Exhibit — the respondent's sworn position vs. the Provincial Assessor's actual productions", [("pdf", axb_pdf)]),
        ("C", 'Respondent\'s letter of 16 June 2025 ("cannot possibly be done in just 15 working days")', [("jpeg", os.path.join(SRC, "AnnexC_doc895_16jun_letter.jpeg"))]),
        ("D", "Petitioner's email to the respondent, 1 October 2025 (records obtained from the Provincial Assessor's Office)", [("pdf", axd_pdf)]),
        ("E", "Specimen productions of the Provincial Assessor's Office: TD No. 1693 (Provincial Form 140); Brgy 5 and Brgy 1 transaction-history ledgers; representative computerized Declarations of Real Property (Brgys 1, 3, 5, incl. the municipal-hall parcel ARP)",
         [("pdf", os.path.join(SRC, "AnnexE_doc561_TD1693.pdf")),
          ("pdf", os.path.join(SRC, "AnnexE_doc115_ledger_brgy5.pdf")),
          ("pdf", os.path.join(SRC, "AnnexE_doc116_ledger_brgy1.pdf")),
          ("pdf", os.path.join(SRC, "AnnexE_doc467_brgy5_arps.pdf")),
          ("pdf", os.path.join(SRC, "AnnexE_doc151_munhall_arp.pdf")),
          ("pdf", os.path.join(SRC, "AnnexE_doc105.pdf"))]),
        ("F", "Respondent's Counter-Affidavit, sworn 28 May 2026", [("pdf", os.path.join(SRC, "AnnexF_doc1046_counter_affidavit.pdf"))]),
        ("G", "Petitioner's Reply-Affidavit", [("pdf", os.path.join(SRC, "AnnexG_doc1158_reply_affidavit.pdf"))]),
    ]

    # 3) stamp + count
    stamped = []
    index_entries = []
    for letter, desc, parts in annexes:
        pages = []
        for kind, src in parts:
            if kind == "pdf":
                pages += list(PdfReader(src).pages)
            elif kind == "jpeg":
                pages.append(jpeg_to_pdf_page(src))
            else:
                pages += src
        pages = [stamp(normalize(p), letter) for p in pages]
        stamped.append(pages)
        index_entries.append((letter, desc, len(pages)))

    # 4) bind
    out = PdfWriter()
    for pg in PdfReader(pet_pdf).pages:
        out.add_page(normalize(pg))
    for pg in index_page(index_entries).pages:
        out.add_page(normalize(pg))
    for pages in stamped:
        for pg in pages:
            out.add_page(pg)

    OUT = os.path.join(MWK, "OP_1321_Petition_Packet_8.5x13.pdf")
    with open(OUT, "wb") as f:
        out.write(f)
    r = PdfReader(OUT)
    sizes = {(round(float(p.mediabox.width)), round(float(p.mediabox.height))) for p in r.pages}
    print("BOUND:", OUT, len(r.pages), "pp, sizes:", sizes)
    for e in index_entries:
        print("  Annex", e[0], "-", e[2], "pp")


if __name__ == "__main__":
    main()
