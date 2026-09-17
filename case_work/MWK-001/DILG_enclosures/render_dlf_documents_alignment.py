#!/usr/bin/env python3
"""Render the de la Fuente family good-faith documents/alignment letter (Sep 2026) to 8.5x13 folio PDF."""
import re
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

F = "/System/Library/Fonts/Supplemental"
pdfmetrics.registerFont(TTFont("TNR", f"{F}/Times New Roman.ttf"))
pdfmetrics.registerFont(TTFont("TNR-Bold", f"{F}/Times New Roman Bold.ttf"))
pdfmetrics.registerFont(TTFont("TNR-Italic", f"{F}/Times New Roman Italic.ttf"))
pdfmetrics.registerFont(TTFont("TNR-BoldItalic", f"{F}/Times New Roman Bold Italic.ttf"))
pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-Bold",
                              italic="TNR-Italic", boldItalic="TNR-BoldItalic")

MWK = "/Users/jonathanzschoche/landtek/case_work/MWK-001"
SRC = f"{MWK}/DEMAND_DLF_DOCUMENTS_ALIGNMENT_2026-09.md"
OUT = f"{MWK}/DEMAND_DLF_DOCUMENTS_ALIGNMENT_2026-09.pdf"
FOLIO = (8.5 * inch, 13.0 * inch)
FOOT = "Zschoche (for Patricia Keesey Zschoche) — Good-faith request to the de la Fuente family, Sep 2026"


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
    "bullet": ParagraphStyle("bullet", **{**base, "leftIndent": 0.55*inch, "bulletIndent": 0.30*inch, "spaceAfter": 4}),
    "encl": ParagraphStyle("encl", **{**base, "fontSize": 10.5, "leading": 13.5}),
    "sig": ParagraphStyle("sig", **{**base, "alignment": TA_LEFT, "spaceAfter": 0, "leading": 15}),
}

lines = open(SRC).read().split("\n")
story, i, in_addr = [], 0, True
while i < len(lines):
    raw = lines[i].rstrip()
    if not raw.strip():
        i += 1; continue

    # Address / date / Re: block, until the salutation
    if in_addr:
        if raw.startswith("Dear "):
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
        if raw.startswith("[•] September 2026"):
            story.append(Spacer(1, 12))
        i += 1; continue

    # Dash bullet list (indented "  - ...")
    if re.match(r"^\s+-\s+", raw):
        txt = re.sub(r"^\s+-\s+", "", raw); i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^\s+-\s+", lines[i]) and lines[i].startswith("  "):
            txt += " " + lines[i].strip(); i += 1
        story.append(Paragraph(md_to_rl(txt), S["bullet"], bulletText="•"))
        continue

    # Ordinary paragraph (join wrapped lines)
    block = [raw.strip()]; i += 1
    while i < len(lines) and lines[i].strip() and not re.match(r"^\s+-\s+", lines[i]):
        block.append(lines[i].strip()); i += 1
    text = " ".join(block)

    if text.startswith("*Enclosure"):
        story.append(Spacer(1, 8)); story.append(Paragraph(md_to_rl(text), S["encl"]))
    elif text.startswith("With respect and good faith,"):
        story.append(Spacer(1, 6)); story.append(Paragraph("With respect and good faith,", S["sig"])); story.append(Spacer(1, 34))
    elif text.startswith("**JONATHAN PAUL ZSCHOCHE**"):
        for part in ["**JONATHAN PAUL ZSCHOCHE**", "for Patricia Keesey Zschoche",
                     "Heir, Estate of Mary Worrick Keesey", "jonzschoche@gmail.com · 0966-698-1448"]:
            story.append(Paragraph(md_to_rl(part), S["sig"]))
        story.append(Spacer(1, 10))
    else:
        story.append(Paragraph(md_to_rl(text), S["body"]))

doc = SimpleDocTemplate(OUT, pagesize=FOLIO, leftMargin=1.0*inch, rightMargin=1.0*inch,
                        topMargin=0.9*inch, bottomMargin=0.9*inch,
                        title="Good-faith request to the de la Fuente family, Sep 2026",
                        author="Jonathan Paul Zschoche (for Patricia Keesey Zschoche)")
doc.build(story, canvasmaker=NC)
print("OK", OUT)
