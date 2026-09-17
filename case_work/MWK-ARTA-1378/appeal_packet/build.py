#!/usr/bin/env python3
"""Render the 1378 OP filing — Petition for Supervisory Review, alt. Notice of Appeal — 8.5x13 folio.

Body only. Annexes "A"-"H-1" are bound separately once the appeal fee receipt (Annex "F") and the
Affidavit of Service (Annex "G") exist.

  python3 build.py
"""
import os
import re

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

HERE = os.path.dirname(os.path.abspath(__file__))
MD = os.path.join(os.path.dirname(HERE), "OP_PETITION_SUPERVISORY_1378_draft.md")
OUT = os.path.join(HERE, "ARTA_1378_OP_Petition_Supervisory_Review_8.5x13.pdf")
FOLIO = (8.5 * 72, 13.0 * 72)
FOOTER = "Zschoche v. Engr. Erwin H. Balane — Petition for Supervisory Review (alt. Notice of Appeal), CTN SL-2026-0218-1378"

F = "/System/Library/Fonts/Supplemental"
for nm, fn in (("TNR", "Times New Roman.ttf"), ("TNR-Bold", "Times New Roman Bold.ttf"),
               ("TNR-Italic", "Times New Roman Italic.ttf"), ("TNR-BoldItalic", "Times New Roman Bold Italic.ttf")):
    pdfmetrics.registerFont(TTFont(nm, f"{F}/{fn}"))
pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-Bold", italic="TNR-Italic", boldItalic="TNR-BoldItalic")

BASE = dict(fontName="TNR", fontSize=11.5, leading=14.8, spaceAfter=7, alignment=TA_JUSTIFY)
S = {
    "h1": ParagraphStyle("h1", fontName="TNR-Bold", fontSize=14, leading=18, alignment=TA_CENTER, spaceBefore=12, spaceAfter=9),
    "h2": ParagraphStyle("h2", fontName="TNR-Bold", fontSize=12.2, leading=15.5, spaceBefore=11, spaceAfter=5),
    "h3": ParagraphStyle("h3", fontName="TNR-Bold", fontSize=11.5, leading=15, spaceBefore=9, spaceAfter=4),
    "h4": ParagraphStyle("h4", fontName="TNR-BoldItalic", fontSize=11.3, leading=14.6, spaceBefore=8, spaceAfter=4),
    "body": ParagraphStyle("body", **BASE),
    "num": ParagraphStyle("num", **{**BASE, "leftIndent": 0.42 * inch, "spaceAfter": 6}),
    "sub": ParagraphStyle("sub", **{**BASE, "leftIndent": 0.7 * inch, "spaceAfter": 5}),
    "addr": ParagraphStyle("addr", **{**BASE, "alignment": TA_LEFT, "spaceAfter": 0, "leading": 14.4}),
    "re": ParagraphStyle("re", **{**BASE, "leftIndent": 0.45 * inch, "spaceBefore": 8, "spaceAfter": 11}),
    "annex": ParagraphStyle("annex", **{**BASE, "fontSize": 10, "leading": 12.8, "leftIndent": 0.42 * inch,
                                        "bulletIndent": 0.18 * inch, "spaceAfter": 3}),
    "sig": ParagraphStyle("sig", **{**BASE, "alignment": TA_LEFT, "spaceAfter": 0, "leading": 14.4}),
}
SIG = ["**JONATHAN PAUL ZSCHOCHE**", "Petitioner (Complainant below)",
       "Attorney-in-Fact for Patricia Keesey Zschoche, Heir, Estate of Mary Worrick Keesey",
       "Dasmariñas Street, Barangay 8, Daet, Camarines Norte", "jonzschoche@gmail.com · 0966-698-1448"]


def md_to_rl(s):
    s = re.sub(r"`\[FILL[^`]*\]`", "__________", s)
    s = re.sub(r"`\[VERIFY[^`]*\]`", "", s)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", s, flags=re.S)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s, flags=re.S)
    s = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", s, flags=re.S)
    s = re.sub(r"`([^`]*)`", r"\1", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def story():
    lines = open(MD).read().split("\n")
    out, i, letter = [], 0, True
    while i < len(lines):
        ln = lines[i].rstrip()
        if ln.startswith("> **INTERNAL"):
            break
        if ln.startswith("> **DRAFT"):
            i += 1
            continue
        if not ln.strip() or ln.strip() == "---":
            i += 1
            continue
        if letter:
            if ln.startswith("Re:"):
                blk = [ln]
                i += 1
                while i < len(lines) and lines[i].strip():
                    blk.append(lines[i].strip())
                    i += 1
                out.append(Paragraph(md_to_rl(" ".join(blk)), S["re"]))
                letter = False
                continue
            out.append(Paragraph(md_to_rl(ln), S["addr"]))
            if ln.startswith("____ September") or ln.startswith("*Served by"):
                out.append(Spacer(1, 11))
            i += 1
            continue
        if ln.startswith("### "):
            out.append(Paragraph(md_to_rl(ln[4:]), S["h3"]))
            i += 1
            continue
        if ln.startswith("## "):
            out.append(Paragraph(md_to_rl(ln[3:]), S["h2"]))
            i += 1
            continue
        if ln.startswith("# "):
            out.append(Paragraph(md_to_rl(ln[2:]), S["h1"]))
            i += 1
            continue
        if re.match(r"^\*\*[A-D]\.\d\.", ln):                       # B.1 / B.2 sub-headings
            out.append(Paragraph(md_to_rl(ln), S["h4"]))
            i += 1
            continue
        if ln.lstrip().startswith("- "):                            # annex / bullet list
            out.append(Paragraph(md_to_rl(ln.lstrip()[2:]), S["annex"], bulletText="•"))
            i += 1
            continue
        m = re.match(r"^(\s*)(\d+)\.\s+(.*)$", ln)                  # numbered paragraphs
        if m:
            indent, n, txt = m.group(1), m.group(2), m.group(3)
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r"^\s*(\d+\.|-\s|#)", lines[i]) \
                    and not lines[i].startswith("**"):
                txt += " " + lines[i].strip()
                i += 1
            out.append(Paragraph(f"<b>{n}.</b> " + md_to_rl(txt), S["sub"] if indent else S["num"]))
            continue
        if re.match(r"^\s+-\s+\*\*\(", ln):                         # lettered sub-items in the verification
            out.append(Paragraph(md_to_rl(ln.strip()[2:]), S["sub"]))
            i += 1
            continue
        blk = [ln.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "- ", ">")) \
                and lines[i].strip() != "---" and not re.match(r"^\s*\d+\.\s", lines[i]) \
                and not re.match(r"^\*\*[A-D]\.\d\.", lines[i]):
            blk.append(lines[i].strip())
            i += 1
        txt = " ".join(blk)
        if txt.startswith("**JONATHAN PAUL ZSCHOCHE**"):
            out.append(Spacer(1, 38))
            for part in SIG:
                out.append(Paragraph(md_to_rl(part), S["sig"]))
            out.append(Spacer(1, 10))
            continue
        if txt.startswith("Respectfully submitted"):
            out.append(Paragraph("Respectfully submitted.", S["body"]))
            continue
        if txt.startswith("**Annexes:**"):
            out.append(Spacer(1, 4))
            out.append(Paragraph("<b>Annexes:</b>", S["body"]))
            continue
        out.append(Paragraph(md_to_rl(txt), S["body"]))
    return out


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
            self.setFont("TNR", 9)
            self.drawCentredString(FOLIO[0] / 2, 0.5 * inch, f"Page {self._pageNumber} of {n}")
            self.setFont("TNR-Italic", 7.3)
            self.drawCentredString(FOLIO[0] / 2, 0.36 * inch, FOOTER)
            super().showPage()
        super().save()


if __name__ == "__main__":
    SimpleDocTemplate(OUT, pagesize=FOLIO, leftMargin=1.0 * inch, rightMargin=1.0 * inch,
                      topMargin=0.85 * inch, bottomMargin=0.85 * inch, title=FOOTER).build(story(), canvasmaker=NC)
    from pypdf import PdfReader
    print("BUILT:", OUT, len(PdfReader(OUT).pages), "pp")
