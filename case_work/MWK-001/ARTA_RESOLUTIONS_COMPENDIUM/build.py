#!/usr/bin/env python3
"""Bind every ARTA resolution in the Mercedes cluster into one reference volume (8.5x13 folio).

Resolution BODIES only — annexes are left in their source files. Each page carries a footer naming the
docket, the resolution date and the source document id, so any page can be traced back to the corpus.

  python3 build.py

Internal reference volume. NOT a filing.
"""
import io
import os

from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from reportlab.lib.colors import Color, black
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "source")
FOLIO = (8.5 * 72, 13.0 * 72)

F = "/System/Library/Fonts/Supplemental"
pdfmetrics.registerFont(TTFont("TNR", f"{F}/Times New Roman.ttf"))
pdfmetrics.registerFont(TTFont("TNR-Bold", f"{F}/Times New Roman Bold.ttf"))
pdfmetrics.registerFont(TTFont("TNR-Italic", f"{F}/Times New Roman Italic.ttf"))
pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-Bold", italic="TNR-Italic")

# (tab, docket, date, caption, disposition, file, first_page, last_page, source_doc)
ITEMS = [
    ("I", "CTN SL-2025-1008-0690 & SL-2025-1104-0792", "07 April 2026",
     "Zschoche v. Engr. Erwin H. Balane, Municipal Engineer",
     "Closure — no prima facie §21(a)(b)(d)(e); §4(f) decided on citizenship; RA 6713 referral noted",
     "res_719.pdf", 1, 8, "doc 719 (= doc 706 packet)"),
    ("II", "CTN SL-2025-1021-0747", "29 April 2026",
     "Zschoche v. Hon. Alexander L. Pajarillo, Municipal Mayor",
     "Closure — no prima facie §21(b)/(d)/(e)",
     "res_967.pdf", 1, 7, "doc 967"),
    ("III", "CTN SL-2026-0128-1210", "13 May 2026",
     "Zschoche v. Hon. Alexander L. Pajarillo and Loida E. Macale, Municipal Treasurer",
     "Closure (Notice of Closure) — no prima facie §21(d)/(e)",
     "res_624.pdf", 1, 6, "doc 624"),
    ("III-A", "CTN SL-2026-0128-1210", "21 May 2026",
     "Litigation Division — Response to Manifestation of Legal Position and Request for Written Clarification",
     "Findings maintained; §4(f) test articulated; citizenship discussion narrowed; property remedies not foreclosed",
     "clarification_1210_21May2026.pdf", 1, 5, "doc 972"),
    ("IV", "CTN SL-2026-0128-1212", "01 June 2026",
     "Zschoche v. Vice Mayor Yapyuco, Councilors Ong and Torralba (Sangguniang Bayan)",
     "Closure, with referral",
     "res_1614.pdf", 1, 7, "doc 1614"),
    ("V", "CTN SL-2026-0209-1319", "25 August 2026",
     "Zschoche v. Fortuno (PENR Officer) and Engr. Remoto, DENR-PENRO Camarines Norte",
     "Closure — no prima facie §21(e); ENDORSED to the Operations Group for reengineering of PENRO's Citizen's Charter",
     "res_8160.pdf", 1, 12, "doc 8160"),
    ("VI", "CTN SL-2026-0209-1321", "25 August 2026",
     "Zschoche v. Gemma P. Abla, Municipal Assessor",
     "Closure — request HELD to be a government service chartered as 'Research/Verify History of Records of "
     "Tax Declaration'; delay excused for due cause",
     "res_1321.pdf", 1, 11, "doc 6908 (Part 1 of 2)"),
    ("VII", "CTN SL-2026-0218-1378", "09 September 2026",
     "Zschoche v. Engr. Erwin H. Balane, Municipal Engineer",
     "Closure — no prima facie §21(b)/(e); records request held NOT a government service under §4(f); "
     "threat letter REFERRED to CSC Regional Office V",
     "res_1378.pdf", 1, 10, "doc 14205"),
]

TITLE = "ANTI-RED TAPE AUTHORITY — RESOLUTIONS IN THE MERCEDES CLUSTER"
SUB = "Heirs of Mary Worrick Keesey · Jonathan Paul Zschoche, complainant · seven dockets, April–September 2026"

S = {
    "h1": ParagraphStyle("h1", fontName="TNR-Bold", fontSize=15, leading=19, alignment=TA_CENTER, spaceAfter=6),
    "h2": ParagraphStyle("h2", fontName="TNR", fontSize=11, leading=14.5, alignment=TA_CENTER, spaceAfter=16),
    "cell": ParagraphStyle("cell", fontName="TNR", fontSize=9.2, leading=11.6),
    "note": ParagraphStyle("note", fontName="TNR-Italic", fontSize=9.4, leading=12.5, alignment=TA_LEFT, spaceBefore=12),
    "tab": ParagraphStyle("tab", fontName="TNR-Bold", fontSize=26, leading=32, alignment=TA_CENTER, spaceBefore=200, spaceAfter=18),
    "tabsub": ParagraphStyle("tabsub", fontName="TNR", fontSize=13, leading=18, alignment=TA_CENTER),
}


def cover(out):
    st = [Paragraph(TITLE, S["h1"]), Paragraph(SUB, S["h2"])]
    rows = [[Paragraph(f"<b>{h}</b>", S["cell"]) for h in ("Tab", "Docket", "Dated", "Respondent(s)", "Disposition", "Pp.")]]
    for tab, docket, date, caption, disp, _f, a, b, _src in ITEMS:
        rows.append([Paragraph(f"<b>{tab}</b>", S["cell"]), Paragraph(docket, S["cell"]), Paragraph(date, S["cell"]),
                     Paragraph(caption, S["cell"]), Paragraph(disp, S["cell"]), Paragraph(str(b - a + 1), S["cell"])])
    t = Table(rows, colWidths=[0.45 * inch, 1.45 * inch, 0.85 * inch, 1.75 * inch, 1.95 * inch, 0.35 * inch], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, black), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (-1, 0), Color(0.93, 0.93, 0.93)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    st.append(t)
    st.append(Paragraph(
        "Scope: the resolution bodies only, as transmitted by the Authority. Annexes stay in the source files. "
        "Every page footer names the docket, the date and the corpus document id it was taken from. "
        "Tab III-A is not a resolution but the Litigation Division's clarification letter, included because the "
        "§4(f) test it states is relied on across the later dockets. "
        "Internal reference volume — not a filing.", S["note"]))
    doc = SimpleDocTemplate(out, pagesize=FOLIO, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                            topMargin=0.9 * inch, bottomMargin=0.85 * inch, title=TITLE)
    doc.build(st)
    return out


def tab_page(item, out):
    tab, docket, date, caption, disp, _f, a, b, src = item
    st = [Paragraph(f"TAB {tab}", S["tab"]),
          Paragraph(f"<b>{docket}</b>", S["tabsub"]),
          Paragraph(caption, S["tabsub"]), Spacer(1, 10),
          Paragraph(f"Resolution dated <b>{date}</b>", S["tabsub"]), Spacer(1, 10),
          Paragraph(disp, ParagraphStyle("d", fontName="TNR-Italic", fontSize=11, leading=15, alignment=TA_CENTER)),
          Spacer(1, 24),
          Paragraph(f"Source: {src}, pp. {a}–{b}", ParagraphStyle("s", fontName="TNR", fontSize=9.5, leading=13, alignment=TA_CENTER))]
    SimpleDocTemplate(out, pagesize=FOLIO, leftMargin=1 * inch, rightMargin=1 * inch,
                      topMargin=1 * inch, bottomMargin=1 * inch, title=f"Tab {tab}").build(st)
    return out


def normalize(pg):
    pw, ph = float(pg.mediabox.width), float(pg.mediabox.height)
    rot = 90 if pw > ph else 0
    tgt = PageObject.create_blank_page(width=FOLIO[0], height=FOLIO[1])
    t = Transformation()
    if rot == 90:
        t = t.rotate(90).translate(ph, 0)
        pw, ph = ph, pw
    s = min(FOLIO[0] / pw, FOLIO[1] / ph) * 0.97
    t = t.scale(s).translate((FOLIO[0] - pw * s) / 2, (FOLIO[1] - ph * s) / 2)
    tgt.merge_transformed_page(pg, t)
    return tgt


def footer(pg, text):
    ov = io.BytesIO()
    c = pdfcanvas.Canvas(ov, pagesize=FOLIO)
    c.setFont("TNR-Italic", 7.8)
    c.setFillColor(Color(0.15, 0.15, 0.15))
    c.drawCentredString(FOLIO[0] / 2, 0.36 * inch, text)
    c.showPage()
    c.save()
    ov.seek(0)
    pg.merge_page(PdfReader(ov).pages[0])
    return pg


def main():
    out = PdfWriter()
    for p in PdfReader(cover(os.path.join(HERE, "_cover.pdf"))).pages:
        out.add_page(p)
    total = 0
    for item in ITEMS:
        tab, docket, date, _cap, _d, fn, a, b, src = item
        for p in PdfReader(tab_page(item, os.path.join(HERE, f"_tab_{tab}.pdf"))).pages:
            out.add_page(p)
        rd = PdfReader(os.path.join(SRC, fn))
        for i in range(a, b + 1):
            pg = normalize(rd.pages[i - 1])
            out.add_page(footer(pg, f"{docket} — Resolution dated {date} — page {i - a + 1} of {b - a + 1} — source {src}"))
            total += 1
        os.remove(os.path.join(HERE, f"_tab_{tab}.pdf"))
    dest = os.path.join(HERE, "ARTA_Resolutions_Compendium_2026-09-16.pdf")
    with open(dest, "wb") as fh:
        out.write(fh)
    os.remove(os.path.join(HERE, "_cover.pdf"))
    r = PdfReader(dest)
    print("BOUND:", dest, len(r.pages), "pp,", total, "resolution pages +", len(ITEMS), "tabs + 1 cover")
    print("sizes:", {(round(float(p.mediabox.width)), round(float(p.mediabox.height))) for p in r.pages})


if __name__ == "__main__":
    main()
