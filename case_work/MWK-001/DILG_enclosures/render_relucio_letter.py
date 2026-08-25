#!/usr/bin/env python3
"""Render the DILG PD Relucio follow-up letter (26 Aug 2026) to 8.5x13 folio PDF."""
import re
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.colors import black, Color

F = "/System/Library/Fonts/Supplemental"
pdfmetrics.registerFont(TTFont("TNR", f"{F}/Times New Roman.ttf"))
pdfmetrics.registerFont(TTFont("TNR-Bold", f"{F}/Times New Roman Bold.ttf"))
pdfmetrics.registerFont(TTFont("TNR-Italic", f"{F}/Times New Roman Italic.ttf"))
pdfmetrics.registerFont(TTFont("TNR-BoldItalic", f"{F}/Times New Roman Bold Italic.ttf"))
pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-Bold",
                              italic="TNR-Italic", boldItalic="TNR-BoldItalic")

MWK = "/Users/jonathanzschoche/landtek/case_work/MWK-001"
SRC = f"{MWK}/DILG_PD_RELUCIO_FOLLOWUP_2026-08-26.md"
OUT = f"{MWK}/DILG_PD_RELUCIO_FOLLOWUP_2026-08-26.pdf"
FOLIO = (8.5 * inch, 13.0 * inch)
FOOT = "Zschoche (AIF, Keesey Zschoche) — Follow-up on 17 Mar 2026 Referral to the Office of the Governor, 26 Aug 2026"


def md_to_rl(s):
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", s, flags=re.S)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s, flags=re.S)
    s = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", s, flags=re.S)
    return s


class NC(pdfcanvas.Canvas):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw); self._saved = []
    def showPage(self):
        self._saved.append(dict(self.__dict__)); self._startPage()
    def save(self):
        n = len(self._saved)
        for st in self._saved:
            self.__dict__.update(st)
            if n > 1:
                self.setFont("TNR", 9)
                self.drawCentredString(FOLIO[0]/2, 0.55*inch, f"Page {self._pageNumber} of {n}")
                self.setFont("TNR-Italic", 8)
                self.drawCentredString(FOLIO[0]/2, 0.40*inch, FOOT)
            super().showPage()
        super().save()


base = dict(fontName="TNR", fontSize=12, leading=15.6, spaceBefore=0, spaceAfter=9, alignment=TA_JUSTIFY)
S = {
    "body": ParagraphStyle("body", **base),
    "addr": ParagraphStyle("addr", **{**base, "alignment": TA_LEFT, "spaceAfter": 0, "leading": 15}),
    "re": ParagraphStyle("re", **{**base, "alignment": TA_LEFT, "leftIndent": 0.55*inch, "spaceBefore": 6, "spaceAfter": 10}),
    "ask": ParagraphStyle("ask", **{**base, "leftIndent": 0.55*inch, "spaceAfter": 5}),
    "encl": ParagraphStyle("encl", **{**base, "fontSize": 10.5, "leading": 13.5}),
    "sig": ParagraphStyle("sig", **{**base, "alignment": TA_LEFT, "spaceAfter": 0, "leading": 15}),
    "cell": ParagraphStyle("cell", fontName="TNR", fontSize=9, leading=11.5),
}

lines = open(SRC).read().split("\n")
story, i, in_addr = [], 0, True
while i < len(lines):
    raw = lines[i].rstrip()
    if not raw.strip():
        i += 1; continue
    if in_addr:
        if raw.startswith("Dear Director"):
            in_addr = False
            story.append(Spacer(1, 8)); story.append(Paragraph(md_to_rl(raw), S["body"]))
            i += 1; continue
        if raw.startswith("Re:"):
            block = [raw]; i += 1
            while i < len(lines) and lines[i].strip():
                block.append(lines[i].strip()); i += 1
            story.append(Spacer(1, 6)); story.append(Paragraph(md_to_rl(" ".join(block)), S["re"]))
            continue
        story.append(Paragraph(md_to_rl(raw), S["addr"]))
        if raw == "26 August 2026" or raw.startswith("*(re:"):
            story.append(Spacer(1, 12))
        i += 1; continue
    if raw.lstrip().startswith("|"):
        tbl = []
        while i < len(lines) and lines[i].lstrip().startswith("|"):
            tbl.append(lines[i].strip()); i += 1
        rows = []
        for tl in tbl:
            cells = [c.strip() for c in tl.strip("|").split("|")]
            if all(re.fullmatch(r"-{3,}:?|:-{2,}:?", c) for c in cells if c):
                continue
            rows.append([Paragraph(md_to_rl(c), S["cell"]) for c in cells])
        if rows:
            w = {3: [2.35*inch, 1.35*inch, 2.8*inch]}.get(len(rows[0]))
            t = Table(rows, colWidths=w)
            t.setStyle(TableStyle([
                ("GRID", (0,0), (-1,-1), 0.5, black),
                ("BACKGROUND", (0,0), (-1,0), Color(0.93,0.93,0.93)),
                ("VALIGN", (0,0), (-1,-1), "TOP"),
                ("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),
                ("TOPPADDING",(0,0),(-1,-1),2.5),("BOTTOMPADDING",(0,0),(-1,-1),2.5)]))
            story.append(Spacer(1,4)); story.append(t); story.append(Spacer(1,6))
        continue
    m2 = re.match(r"^\s{2,}\((\w)\)\s+(.*)$", raw)
    if m2:
        txt = m2.group(2); i += 1
        while i < len(lines) and lines[i].strip() and lines[i].startswith("  ") and not re.match(r"^\s{2,}\(\w\)\s", lines[i]):
            txt += " " + lines[i].strip(); i += 1
        story.append(Paragraph(f"({m2.group(1)}) " + md_to_rl(txt), S["ask"]))
        continue
    block = [raw.strip()]; i += 1
    while i < len(lines) and lines[i].strip() and not lines[i].lstrip().startswith("|") \
            and not re.match(r"^\s{2,}\(\w\)\s", lines[i]):
        block.append(lines[i].strip()); i += 1
    text = " ".join(block)
    if text.startswith("*Attachments:*"):
        story.append(Spacer(1,8)); story.append(Paragraph(md_to_rl(text), S["encl"]))
    elif text.startswith("Respectfully,"):
        story.append(Spacer(1,6)); story.append(Paragraph("Respectfully,", S["sig"])); story.append(Spacer(1,34))
    elif text.startswith("**JONATHAN PAUL ZSCHOCHE**"):
        for part in ["**JONATHAN PAUL ZSCHOCHE**", "Attorney-in-Fact for Patricia Keesey Zschoche",
                     "Heir, Estate of Mary Worrick Keesey", "jonzschoche@gmail.com · 0966-698-1448"]:
            story.append(Paragraph(md_to_rl(part), S["sig"]))
        story.append(Spacer(1,10))
    else:
        if re.match(r"^\*\*\d+\.", text):
            story.append(Spacer(1,4))
        story.append(Paragraph(md_to_rl(text), S["body"]))

doc = SimpleDocTemplate(OUT, pagesize=FOLIO, leftMargin=1.0*inch, rightMargin=1.0*inch,
                        topMargin=0.9*inch, bottomMargin=0.9*inch,
                        title="Follow-up on 17 Mar 2026 Referral to the Office of the Governor — Zschoche to DILG-PD Camarines Norte, 26 Aug 2026",
                        author="Jonathan Paul Zschoche (AIF, Patricia Keesey Zschoche)")
doc.build(story, canvasmaker=NC)
print("OK", OUT)
