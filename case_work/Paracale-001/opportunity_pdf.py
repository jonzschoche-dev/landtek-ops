#!/usr/bin/env python3
"""Render the whole mining-opportunity package (Wave-1 sheet + vehicle structure memo) as ONE bound PDF.
Usage: python3 opportunity_pdf.py   → MINING_OPPORTUNITY_PACKAGE_2026-09.pdf (same folder)
Markdown-driven: edit the .md files, re-run. House style follows strategy_mandate_pdf.py / lab_x_deck.py."""
import re, html, datetime, os
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, PageBreak, Preformatted, KeepTogether)

HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = [
    ("PART A — IMMEDIATE OPPORTUNITIES", "IMMEDIATE_OPPORTUNITIES_SMBC_CASALUGAN_2026-09.md"),
    ("PART B — THE INVESTMENT VEHICLE", "MINING_INVESTMENT_VEHICLE_STRUCTURE_2026-09.md"),
]
OUT = os.path.join(HERE, "MINING_OPPORTUNITY_PACKAGE_2026-09.pdf")

SUP = "/System/Library/Fonts/Supplemental"
pdfmetrics.registerFont(TTFont("Ar", f"{SUP}/Arial.ttf"))
pdfmetrics.registerFont(TTFont("ArB", f"{SUP}/Arial Bold.ttf"))
pdfmetrics.registerFont(TTFont("ArI", f"{SUP}/Arial Italic.ttf"))
pdfmetrics.registerFont(TTFont("ArBI", f"{SUP}/Arial Bold Italic.ttf"))
pdfmetrics.registerFont(TTFont("Mono", f"{SUP}/Courier New.ttf"))
pdfmetrics.registerFont(TTFont("MonoB", f"{SUP}/Courier New Bold.ttf"))
pdfmetrics.registerFontFamily("Ar", normal="Ar", bold="ArB", italic="ArI", boldItalic="ArBI")
pdfmetrics.registerFontFamily("Mono", normal="Mono", bold="MonoB", italic="Mono", boldItalic="MonoB")

NAVY = colors.HexColor("#1a2e4a"); ACCENT = colors.HexColor("#8a6d1f")
GRAY = colors.HexColor("#555555"); LIGHT = colors.HexColor("#f2f0ea"); RULE = colors.HexColor("#c9c4b6")

S = {
 "cover_t": ParagraphStyle("ct", fontName="ArB", fontSize=22, leading=27, textColor=NAVY),
 "cover_s": ParagraphStyle("cs", fontName="ArB", fontSize=13, leading=17, textColor=ACCENT),
 "part":    ParagraphStyle("pt", fontName="ArB", fontSize=18, leading=22, textColor=NAVY, spaceAfter=6),
 "h1":      ParagraphStyle("h1", fontName="ArB", fontSize=15, leading=19, textColor=NAVY, spaceBefore=4, spaceAfter=4),
 "h1sub":   ParagraphStyle("h1s", fontName="ArB", fontSize=11, leading=14.5, textColor=ACCENT, spaceAfter=4),
 "h2":      ParagraphStyle("h2", fontName="ArB", fontSize=12, leading=15, textColor=NAVY, spaceBefore=12, spaceAfter=4),
 "h3":      ParagraphStyle("h3", fontName="ArB", fontSize=10.5, leading=13.5, textColor=NAVY, spaceBefore=8, spaceAfter=3),
 "meta":    ParagraphStyle("meta", fontName="ArI", fontSize=8, leading=10.5, textColor=GRAY, spaceAfter=6),
 "body":    ParagraphStyle("body", fontName="Ar", fontSize=9.6, leading=13.2, spaceAfter=5),
 "quote":   ParagraphStyle("q", fontName="Ar", fontSize=9.4, leading=13, leftIndent=12, borderPadding=(4,6,4,6),
                           backColor=LIGHT, spaceAfter=8),
 "bul":     ParagraphStyle("bul", fontName="Ar", fontSize=9.6, leading=13.2, leftIndent=16, bulletIndent=4, spaceAfter=3),
 "num":     ParagraphStyle("num", fontName="Ar", fontSize=9.6, leading=13.2, leftIndent=20, firstLineIndent=-20, spaceAfter=4),
 "cell":    ParagraphStyle("cell", fontName="Ar", fontSize=8.3, leading=10.6),
 "cellh":   ParagraphStyle("cellh", fontName="ArB", fontSize=8.3, leading=10.6, textColor=colors.white),
 "code":    ParagraphStyle("code", fontName="Mono", fontSize=6.4, leading=8.2, backColor=LIGHT,
                           borderPadding=(5,6,5,6), spaceBefore=4, spaceAfter=8),
}

def glyphfix(t):
    return t.replace("▶", ">").replace("✔", "[x]").replace("☐", "[ ]")

def inline(t):
    t = glyphfix(html.escape(t, quote=False))
    t = re.sub(r"`([^`]+)`", r'<font name="Mono" size="8.3">\1</font>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", t)  # links → text
    return t

def para(t, st="body"): return Paragraph(inline(t), S[st])

def table(rows, width):
    hdr = rows[0]; body = rows[1:]
    has_hdr = any(c.strip() for c in hdr)
    ncol = max(len(r) for r in rows)
    rows = [r + [""]*(ncol-len(r)) for r in rows]
    if ncol == 2 and not has_hdr:
        k = 1.6*inch if S["body"].fontSize >= 13 else 1.35*inch
        widths = [k, width-k]
    elif ncol == 2:
        k = 2.7*inch if S["body"].fontSize >= 13 else 2.2*inch
        widths = [k, width-k]
    else:
        first = min(1.7*inch, width*0.28)
        widths = [first] + [(width-first)/(ncol-1)]*(ncol-1)
    data = []
    for i, r in enumerate(rows):
        st = "cellh" if (i == 0 and has_hdr) else "cell"
        if i == 0 and not has_hdr: continue
        data.append([Paragraph(inline(c.strip()), S[st]) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1 if has_hdr else 0)
    ts = [("GRID", (0,0), (-1,-1), 0.4, RULE), ("VALIGN", (0,0), (-1,-1), "TOP"),
          ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4),
          ("TOPPADDING", (0,0), (-1,-1), 3), ("BOTTOMPADDING", (0,0), (-1,-1), 3)]
    if has_hdr:
        ts += [("BACKGROUND", (0,0), (-1,0), NAVY)]
        for k in range(1, len(data)):
            if k % 2 == 0: ts.append(("BACKGROUND", (0,k), (-1,k), LIGHT))
    else:
        ts += [("BACKGROUND", (0,0), (0,-1), LIGHT), ("FONTNAME", (0,0), (0,-1), "ArB")]
        for k in range(len(data)):
            data[k][0] = Paragraph("<b>" + inline(rows[k+1][0].strip()) + "</b>", S["cell"])
    t.setStyle(TableStyle(ts)); t.spaceAfter = 8
    return t

def render_md(md, width, story):
    lines = md.splitlines(); i = 0; first_h1 = True
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("<!--"): i += 1; continue
        if ln.startswith("```"):
            buf = []; i += 1
            while i < len(lines) and not lines[i].startswith("```"): buf.append(lines[i]); i += 1
            story.append(Preformatted(glyphfix("\n".join(buf)), S["code"], maxLineLength=100, splitChars=" ", newLineChars="        ")); i += 1; continue
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r"\s*:?-+:?\s*", c) for c in cells): rows.append(cells)
                i += 1
            story.append(table(rows, width)); continue
        if ln.startswith("# "):
            story.append(para(ln[2:], "h1" if first_h1 else "h2")); first_h1 = False; i += 1; continue
        if ln.startswith("## ") and i == 1 and lines[0].startswith("# "):
            story.append(para(ln[3:], "h1sub")); i += 1; continue
        if ln.startswith("## "): story.append(para(ln[3:], "h2")); i += 1; continue
        if ln.startswith("### "): story.append(para(ln[4:], "h3")); i += 1; continue
        if ln.strip() == "---":
            story.append(HRFlowable(width="100%", thickness=0.8, color=RULE, spaceBefore=4, spaceAfter=6)); i += 1; continue
        if ln.startswith("> "):
            buf = []
            while i < len(lines) and lines[i].startswith(">"): buf.append(lines[i][1:].strip()); i += 1
            story.append(para(" ".join(buf), "quote")); continue
        if re.match(r"^\s*- ", ln):
            buf = []
            while i < len(lines) and re.match(r"^\s*- ", lines[i]):
                item = re.sub(r"^\s*- ", "", lines[i]); i += 1
                while i < len(lines) and lines[i].startswith("  ") and not re.match(r"^\s*- ", lines[i]):
                    item += " " + lines[i].strip(); i += 1
                buf.append(item)
            for b in buf: story.append(Paragraph(inline(b), S["bul"], bulletText="•"))
            story.append(Spacer(1, 3)); continue
        m = re.match(r"^(\d+)\. (.*)", ln)
        if m:
            n, item = m.group(1), m.group(2); i += 1
            while i < len(lines) and lines[i].startswith("   ") and not re.match(r"^\d+\. ", lines[i].strip()):
                item += " " + lines[i].strip(); i += 1
            story.append(Paragraph(f"<b>{n}.</b>&nbsp;&nbsp;" + inline(item), S["num"])); continue
        if ln.strip() == "": i += 1; continue
        # paragraph (merge soft-wrapped lines)
        buf = [ln.strip()]; i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||>|```|---|<!--|\s*- |\d+\. )", lines[i]):
            buf.append(lines[i].strip()); i += 1
        txt = " ".join(buf)
        st = "meta" if (txt.startswith("*") and txt.endswith("*") and txt.count("*") == 2) else "body"
        if st == "meta": txt = txt[1:-1]
        story.append(para(txt, st))

def on_page(c, doc):
    c.saveState(); c.setFont("Ar", 7.5); c.setFillColor(GRAY)
    c.drawString(0.75*inch, 0.5*inch, "LandTek · Mining Opportunity Package · INTERNAL-HELD / NEEDS-COUNSEL · Paracale-001")
    c.drawRightString(letter[0]-0.75*inch, 0.5*inch, f"Page {doc.page}")
    c.restoreState()

MEMO_MD = "MEMO_STEPHEN_JULIET_MINING_OPPORTUNITY_2026-09.md"
MEMO_OUT = os.path.join(HERE, "MEMO_STEPHEN_JULIET_MINING_OPPORTUNITY_2026-09.pdf")

def scale_styles(body_pt):
    """Re-size every text style so body text renders at body_pt (memo default 14 pt, Jonathan 2026-09-12).
    Code blocks stay small enough for the structure diagram to fit the page width."""
    f = body_pt / 9.6
    for k, st in S.items():
        if k == "code":
            st.fontSize, st.leading = 8.2, 10.2
        elif k in ("cell", "cellh"):
            st.fontSize, st.leading = round(body_pt * 0.86, 1), round(body_pt * 0.86 * 1.3, 1)
        else:
            st.fontSize = round(st.fontSize * f, 1); st.leading = round(st.leading * f, 1)
        if k in ("num",):
            st.leftIndent, st.firstLineIndent = 26, -26
        if k in ("bul",):
            st.leftIndent = 22

def build_memo(body_pt=14):
    """Partner memo (Allan + Stephen + Juliet): no cover, memo header comes from the markdown. 14 pt body."""
    scale_styles(body_pt)
    doc = BaseDocTemplate(MEMO_OUT, pagesize=letter, leftMargin=0.75*inch, rightMargin=0.75*inch,
                          topMargin=0.7*inch, bottomMargin=0.8*inch,
                          title="Memorandum — The Paracale gold opportunity", author="Jonathan Zschoche & Allan V. Inocalla")
    W = letter[0] - 1.5*inch
    def foot(c, d):
        c.saveState(); c.setFont("Ar", 7.5); c.setFillColor(GRAY)
        c.drawString(0.75*inch, 0.5*inch, "Memorandum · The Paracale gold opportunity · Confidential — partners' working document")
        c.drawRightString(letter[0]-0.75*inch, 0.5*inch, f"Page {d.page}"); c.restoreState()
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(doc.leftMargin, doc.bottomMargin, W,
                          letter[1]-1.5*inch, id="f")], onPage=foot)])
    st = []
    render_md(open(os.path.join(HERE, MEMO_MD), encoding="utf-8").read(), W, st)
    doc.build(st); print("wrote", MEMO_OUT)

def build():
    doc = BaseDocTemplate(OUT, pagesize=letter, leftMargin=0.75*inch, rightMargin=0.75*inch,
                          topMargin=0.7*inch, bottomMargin=0.8*inch,
                          title="Mining Opportunity Package — Allan Inocalla / LandTek", author="LandTek")
    W = letter[0] - 1.5*inch
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(doc.leftMargin, doc.bottomMargin, W,
                          letter[1]-1.5*inch, id="f")], onPage=on_page)])
    st = []
    # cover
    st += [Spacer(1, 1.6*inch), Paragraph("MINING OPPORTUNITY PACKAGE", S["cover_t"]), Spacer(1, 6),
           Paragraph("Allan Inocalla's mining company — processing, small-scale contracts, exploration, and the Canadian listing path",
                     S["cover_s"]), Spacer(1, 10), HRFlowable(width="100%", thickness=1.4, color=NAVY), Spacer(1, 14)]
    st += [Paragraph("<b>Part A — Immediate opportunities.</b> What starts now inside the SMBC Minahang Bayan at Casalugan around the ₱29M "
                "mercury-free plant, with the ₱5M already committed; then Wave 2 at Jose Panganiban (AVI Gold Processing and Allan's "
                "Minahang Bayan). None of it needs NIBDC.", S["body"]),
           Paragraph("<b>Part B — The investment vehicle.</b> The Philippine-law structure (Filipino extraction layer + foreign-eligible "
                "processing / finance / exploration layer), the NIBDC exploration chapter, and what a TSX Venture or CSE listing "
                "actually tests.", S["body"]),
           Spacer(1, 14),
           para("Prepared by LandTek, 12 September 2026, for Jonathan Zschoche and Allan V. Inocalla. Internal working papers. "
                "Not legal, tax or securities advice; every gate is for Philippine mining counsel, Philippine tax counsel and "
                "Canadian securities counsel to confirm before any incorporation, filing, wire or listing step. "
                "Fact tags: [V] cited to statute / policy / corpus document · [O] operator-stated · [E] estimate, unquoted · "
                "[PV] pending verification.", "meta"),
           para("Sequence: Wave 1 (SMBC, Casalugan) → Wave 2 (Jose Panganiban) → Wave 3 (NIBDC EP → listing). "
                "MGB Region V's letter of 29 July 2026 confirms an Exploration Permit applicant holds notice rights only, so Waves 1 and 2 "
                "need no NIBDC consent.", "body"),
           PageBreak()]
    for title, fn in PARTS:
        md = open(os.path.join(HERE, fn), encoding="utf-8").read()
        st += [Paragraph(title, S["part"]), HRFlowable(width="100%", thickness=1.2, color=ACCENT, spaceAfter=8)]
        render_md(md, W, st)
        st.append(PageBreak())
    st.pop()
    doc.build(st)
    print("wrote", OUT)

if __name__ == "__main__":
    import sys
    build_memo() if (len(sys.argv) > 1 and sys.argv[1] == "memo") else build()
