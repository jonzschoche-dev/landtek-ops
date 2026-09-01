#!/usr/bin/env python3
"""Build the bound Botor trial-brief PDF from the package markdown.

Usage: python3 build_bound_pdf.py [outpath]
Renders: cover -> 01..04 + 05 message -> court-order transcription -> annex index -> order scan.
Markdown subset: #/##/### headings, tables, blockquotes, lists, bold/italic/backtick code, ---.
"""
import os, re, sys, html

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, PageBreak,
                                Table, TableStyle, HRFlowable, Image)

HERE = os.path.dirname(os.path.abspath(__file__))
ORDERS = os.path.join(HERE, "..", "court_orders")

PARTS = [
    ("PART 1 — Counsel Brief", "01_COUNSEL_BRIEF_BOTOR.md"),
    ("PART 2 — Trial Document Index", "02_TRIAL_DOCUMENT_INDEX.md"),
    ("PART 3 — Testimony Preparation (9 Sep 2026)", "03_TESTIMONY_PREP_SEPT9.md"),
    ("PART 4 — Campaign-Pattern Memo", "04_CAMPAIGN_PATTERN_MEMO.md"),
    ("PART 5 — Cover Message (draft)", "05_MESSAGE_TO_BOTOR.md"),
    ("PART 6 — MTC Order of 28 Aug 2026 (transcription)",
     os.path.join(ORDERS, "ORDER_2026-08-28_trial_setting.md")),
    ("PART 7 — Annex Index (Google Drive folder)", "ANNEX_INDEX.md"),
]

S = getSampleStyleSheet()
BODY = ParagraphStyle("Body", parent=S["Normal"], fontSize=9.2, leading=12.6,
                      spaceAfter=4)
H1 = ParagraphStyle("H1x", parent=S["Heading1"], fontSize=14, leading=17,
                    spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#1a1a2e"))
H2 = ParagraphStyle("H2x", parent=S["Heading2"], fontSize=11.5, leading=14.5,
                    spaceBefore=8, spaceAfter=4, textColor=colors.HexColor("#1a1a2e"))
H3 = ParagraphStyle("H3x", parent=S["Heading3"], fontSize=10, leading=13,
                    spaceBefore=6, spaceAfter=3)
QUOTE = ParagraphStyle("Quote", parent=BODY, leftIndent=14, textColor=colors.HexColor("#333355"),
                       borderPadding=3, backColor=colors.HexColor("#f2f2f8"), spaceAfter=5)
CELL = ParagraphStyle("Cell", parent=BODY, fontSize=7.8, leading=10, spaceAfter=0)
CELLH = ParagraphStyle("CellH", parent=CELL, fontName="Helvetica-Bold")
LIST = ParagraphStyle("List", parent=BODY, leftIndent=14, bulletIndent=4)
PARTP = ParagraphStyle("Part", parent=S["Title"], fontSize=18, spaceBefore=200)


def inline(md: str) -> str:
    t = html.escape(md, quote=False)
    t = re.sub(r"`([^`]+)`", r'<font face="Courier" size="8">\1</font>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"~~([^~]+)~~", r"<strike>\1</strike>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", t)  # drop link targets
    return t


def md_to_flow(text: str):
    flows, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1; continue
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|?\s*$", lines[i+1]):
            rows = [ln]; i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i]); i += 1
            data = []
            for r_i, r in enumerate(rows):
                cells = [c.strip() for c in r.strip().strip("|").split("|")]
                sty = CELLH if r_i == 0 else CELL
                data.append([Paragraph(inline(c), sty) for c in cells])
            ncols = max(len(r) for r in data)
            for r in data:
                r += [Paragraph("", CELL)] * (ncols - len(r))
            avail = A4[0] - 3.4*cm
            t = Table(data, colWidths=[avail/ncols]*ncols, repeatRows=1)
            t.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#aaaaaa")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            flows += [Spacer(1, 3), t, Spacer(1, 5)]
            continue
        if ln.startswith("> "):
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i].lstrip(">").strip()); i += 1
            for para in re.split(r"\n\s*\n", "\n".join(buf)):
                if para.strip():
                    flows.append(Paragraph(inline(para.replace("\n", " ")), QUOTE))
            continue
        if re.match(r"^-{3,}\s*$", ln):
            flows.append(HRFlowable(width="100%", thickness=0.6,
                                    color=colors.HexColor("#888888"), spaceBefore=6, spaceAfter=6))
            i += 1; continue
        m = re.match(r"^(#{1,4})\s+(.*)$", ln)
        if m:
            lvl, txt = len(m.group(1)), m.group(2)
            flows.append(Paragraph(inline(txt), {1: H1, 2: H2}.get(lvl, H3)))
            i += 1; continue
        m = re.match(r"^(\s*)([-*]|\d+\.|\[ \]|- \[ \])\s+(.*)$", ln)
        if m:
            while i < len(lines):
                mm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
                if not mm:
                    break
                item = mm.group(3); i += 1
                while i < len(lines) and lines[i].strip() and not re.match(
                        r"^(\s*)([-*]|\d+\.|\||#|>)", lines[i]):
                    item += " " + lines[i].strip(); i += 1
                bullet = "•" if mm.group(2) in "-*" else mm.group(2)
                flows.append(Paragraph(f"{bullet} {inline(item)}", LIST))
            continue
        para = [ln]; i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||>|[-*] |\d+\. |-{3,}\s*$)", lines[i]):
            para.append(lines[i].strip()); i += 1
        flows.append(Paragraph(inline(" ".join(para)), BODY))
    return flows


def build(outpath: str):
    doc = SimpleDocTemplate(outpath, pagesize=A4, leftMargin=1.7*cm, rightMargin=1.7*cm,
                            topMargin=1.6*cm, bottomMargin=1.6*cm,
                            title="CV 26-360 Trial Brief for Atty. Botor",
                            author="Jonathan Paul Zschoche (LandTek work product)")
    story = [
        Spacer(1, 5*cm),
        Paragraph("Civil Case No. 26-360 — Zschoche v. Balane, et al.", S["Title"]),
        Paragraph("MTC Mercedes, Camarines Norte · Trial begins 9 September 2026, 1:30 PM", H2),
        Spacer(1, 1*cm),
        Paragraph("TRIAL BRIEFING PACKAGE for ATTY. ADAN MARCELO B. BOTOR", H1),
        Paragraph("Prepared for Jonathan Paul Zschoche, Attorney-in-Fact of plaintiff "
                  "Patricia Keesey Zschoche · 2026-08-30", BODY),
        Spacer(1, 0.6*cm),
        Paragraph("<b>PRIVILEGED &amp; CONFIDENTIAL — ATTORNEY WORK PRODUCT.</b> Internal work "
                  "product for counsel. Facts cite corpus document ids; items marked "
                  "PENDING VERIFICATION / [HV] / draft are not court-grade until confirmed "
                  "against the primary record. Nothing herein has been filed or served.", QUOTE),
        Paragraph("Supporting documents: Google Drive folder "
                  "<b>“CV26360 - Trial Brief for Atty. Botor (2026-08-30)”</b> "
                  "(Annexes A1–E15; index at Part 7).", BODY),
    ]
    for label, fn in PARTS:
        path = fn if os.path.isabs(fn) or os.sep in fn else os.path.join(HERE, fn)
        story.append(PageBreak())
        story.append(Paragraph(label, H1))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a1a2e"),
                                spaceAfter=8))
        with open(path, encoding="utf-8") as f:
            story += md_to_flow(f.read())
    scan = os.path.join(ORDERS, "ORDER_2026-08-28_trial_setting_scan.jpg")
    if os.path.exists(scan):
        story.append(PageBreak())
        story.append(Paragraph("PART 8 — MTC Order of 28 Aug 2026 (scan)", H1))
        img = Image(scan)
        maxw, maxh = A4[0] - 3.4*cm, A4[1] - 5*cm
        ratio = min(maxw / img.imageWidth, maxh / img.imageHeight)
        img.drawWidth, img.drawHeight = img.imageWidth * ratio, img.imageHeight * ratio
        story.append(img)
    doc.build(story)
    print(outpath, os.path.getsize(outpath), "bytes")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        HERE, "MWK_CV26360_Trial_Brief_for_Atty_Botor.pdf")
    build(out)
