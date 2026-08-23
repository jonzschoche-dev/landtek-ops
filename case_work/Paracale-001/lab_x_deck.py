#!/usr/bin/env python3
"""LAB X — Gold Shaking Table Program. Design + specs + cost model deck (PDF).

Golden Inocalla Management Services · Stephen Lloyd (design lead, SMBC operating partner) · Allan Inocalla.
Site: SMBC Mercury-Free Processing System, Barangay Casalugan, Paracale — facts per case_work/NIBDC-001/DEAL_MEMO_PLANET_GOLD_PROCESSING_NIBDC.md.
Regenerate:  python3 case_work/Paracale-001/lab_x_deck.py
Source of record for the engineering content: SHAKER_TABLE_PROTOTYPE_DESIGN.md (same folder).
Every figure that is not a design choice is either a blank field or flagged TO CLARIFY;
all peso figures are ESTIMATE / UNQUOTED until a vendor quote replaces them.
"""
import os, math
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "LAB_X_SHAKER_TABLE_DESIGN.pdf")
DATE = "23 Aug 2026"
VERSION = "Draft v0.1"

# ---------- fonts ----------
FONTS = "/System/Library/Fonts"
pdfmetrics.registerFont(TTFont("FutXB", f"{FONTS}/Supplemental/Futura.ttc", subfontIndex=4))
pdfmetrics.registerFont(TTFont("FutM", f"{FONTS}/Supplemental/Futura.ttc", subfontIndex=0))
pdfmetrics.registerFont(TTFont("FutB", f"{FONTS}/Supplemental/Futura.ttc", subfontIndex=2))
pdfmetrics.registerFont(TTFont("Ch", f"{FONTS}/Supplemental/Charter.ttc", subfontIndex=0))
pdfmetrics.registerFont(TTFont("ChI", f"{FONTS}/Supplemental/Charter.ttc", subfontIndex=1))
pdfmetrics.registerFont(TTFont("ChB", f"{FONTS}/Supplemental/Charter.ttc", subfontIndex=3))
pdfmetrics.registerFont(TTFont("ChBI", f"{FONTS}/Supplemental/Charter.ttc", subfontIndex=2))
pdfmetrics.registerFont(TTFont("Mono", f"{FONTS}/Menlo.ttc", subfontIndex=0))
pdfmetrics.registerFont(TTFont("MonoB", f"{FONTS}/Menlo.ttc", subfontIndex=1))
pdfmetrics.registerFontFamily("Ch", normal="Ch", bold="ChB", italic="ChI", boldItalic="ChBI")
pdfmetrics.registerFontFamily("Mono", normal="Mono", bold="MonoB", italic="Mono", boldItalic="MonoB")

# ---------- palette ----------
GRAPHITE = HexColor("#22272B")
STONE = HexColor("#ECEDE9")
STONE2 = HexColor("#E1E3DE")
INK = HexColor("#1D2124")
GOLD = HexColor("#C29A32")
GOLD_D = HexColor("#9E7A1F")
OXIDE = HexColor("#9A3F2C")
SLATE = HexColor("#4F6D84")
MUTE = HexColor("#7C8287")
RULE = HexColor("#C9CCC6")
WHITE = HexColor("#F7F7F4")

W, H = 960, 540
RAIL = 46
LM = RAIL + 34          # left margin for content
RM = W - 40
CW = RM - LM            # content width

# ---------- styles ----------
def ps(name, font="Ch", size=10, lead=None, color=INK, **kw):
    return ParagraphStyle(name, fontName=font, fontSize=size, leading=lead or size * 1.3, textColor=color, alignment=TA_LEFT, **kw)

BODY = ps("body", size=10.5, lead=14)
BODY_S = ps("bodys", size=9.2, lead=12.2)
LEAD = ps("lead", size=13, lead=17.5)
LEAD_W = ps("leadw", size=13, lead=17.5, color=WHITE)
CAP = ps("cap", size=8, lead=10, color=MUTE)
CELL = ps("cell", size=8.6, lead=10.6)
CELL_B = ps("cellb", font="ChB", size=8.6, lead=10.6)
CELL_M = ps("cellm", font="Mono", size=7.8, lead=10)
CELL_W = ps("cellw", font="FutM", size=7.2, lead=9, color=WHITE)
NOTE = ps("note", font="ChI", size=8.6, lead=11, color=MUTE)

TOTAL_PAGES = [0]


def glyph(t):
    """Charter/Futura lack the arrow glyphs; set them in Menlo inside paragraphs."""
    for ch in ("→", "←", "↔"):
        t = t.replace(ch, f"<font name='Mono'>{ch}</font>")
    return t.replace("₱", "PHP ")  # Charter/Futura have no peso glyph


class Deck:
    def __init__(self, path):
        self.c = canvas.Canvas(path, pagesize=(W, H))
        self.c.setTitle("LAB X — Gold Shaking Table Program")
        self.c.setAuthor("Golden Inocalla Management Services")
        self.c.setSubject("Design, specifications and cost model — draft v0.1")
        self.n = 0

    # ----- chrome -----
    def _rail(self, dark=False):
        c = self.c
        c.setFillColor(GRAPHITE if not dark else HexColor("#1A1E21"))
        c.rect(0, 0, RAIL, H, stroke=0, fill=1)
        c.saveState()
        c.setFillColor(GOLD)
        c.setFont("FutXB", 15)
        c.translate(RAIL / 2 + 5, 26)
        c.rotate(90)
        c.drawString(0, 0, "LAB X")
        c.restoreState()
        c.setFillColor(WHITE)
        c.setFont("Mono", 7.5)
        c.drawCentredString(RAIL / 2, H - 24, f"{self.n:02d}")

    def _footer(self, dark=False):
        c = self.c
        c.setFont("Ch", 7.3)
        c.setFillColor(MUTE)
        c.drawString(LM, 20, f"Golden Inocalla Management Services · Gold Shaking Table Program · {VERSION} · {DATE}")
        c.drawRightString(RM, 20, "Confidential · all costs ESTIMATE / UNQUOTED · engineering content: SHAKER_TABLE_PROTOTYPE_DESIGN.md")

    def page(self, title, eyebrow=None, dark=False):
        if self.n:
            self.c.showPage()
        self.n += 1
        c = self.c
        c.setFillColor(GRAPHITE if dark else STONE)
        c.rect(0, 0, W, H, stroke=0, fill=1)
        self._rail(dark)
        if eyebrow:
            c.setFont("FutM", 7.6)
            c.setFillColor(GOLD)
            c.drawString(LM, H - 42, eyebrow.upper(), charSpace=1.6)
        c.setFont("FutXB", 25)
        c.setFillColor(WHITE if dark else INK)
        c.drawString(LM - 1, H - 70, title)
        c.setStrokeColor(GOLD)
        c.setLineWidth(1.2)
        c.line(LM, H - 82, LM + 54, H - 82)
        self._footer(dark)
        return H - 100  # content top y

    # ----- primitives -----
    def para(self, text, x, y_top, w, style=BODY):
        p = Paragraph(glyph(text), style)
        _, h = p.wrap(w, 1000)
        p.drawOn(self.c, x, y_top - h)
        return y_top - h

    def label(self, text, x, y, color=GOLD_D, size=7.4):
        self.c.setFont("FutM", size)
        self.c.setFillColor(color)
        self.c.drawString(x, y, text.upper(), charSpace=1.4)

    def flag(self, x, y, text="TO CLARIFY", w=None):
        c = self.c
        c.setFont("FutM", 6.6)
        tw = pdfmetrics.stringWidth(text.upper(), "FutM", 6.6) + 6.6 * 0.2 * len(text)
        w = w or tw + 12
        c.setStrokeColor(OXIDE)
        c.setLineWidth(0.8)
        c.setFillColor(Color(0.60, 0.25, 0.17, alpha=0.08))
        c.roundRect(x, y - 3.5, w, 12, 2.5, stroke=1, fill=1)
        c.setFillColor(OXIDE)
        c.drawString(x + 6, y, text.upper(), charSpace=1.1)
        return w

    def blank(self, x, y, w, label=None, value=""):
        """A fill-in field: light box, dotted baseline, optional label left."""
        c = self.c
        c.setFillColor(WHITE)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.6)
        c.rect(x, y - 4, w, 14, stroke=1, fill=1)
        c.setStrokeColor(MUTE)
        c.setDash(1, 2)
        c.line(x + 4, y - 1, x + w - 4, y - 1)
        c.setDash()
        if value:
            c.setFont("Mono", 8)
            c.setFillColor(INK)
            c.drawString(x + 5, y + 1, value)
        if label:
            c.setFont("FutM", 6.4)
            c.setFillColor(MUTE)
            c.drawString(x, y + 12.5, label.upper(), charSpace=1)

    def table(self, data, x, y_top, col_w, header=True, font_size=8.6, zebra=True, mono_cols=(), bold_col0=False, pad=4):
        rows = []
        for ri, row in enumerate(data):
            out = []
            for ci, cell in enumerate(row):
                cell = glyph(str(cell))
                if header and ri == 0:
                    out.append(Paragraph(cell.upper(), CELL_W))
                elif ci in mono_cols:
                    out.append(Paragraph(str(cell), CELL_M))
                elif ci == 0 and bold_col0:
                    out.append(Paragraph(str(cell), CELL_B))
                else:
                    out.append(Paragraph(str(cell), CELL))
            rows.append(out)
        t = Table(rows, colWidths=col_w)
        st = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), pad + 1),
            ("RIGHTPADDING", (0, 0), (-1, -1), pad),
            ("TOPPADDING", (0, 0), (-1, -1), pad),
            ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ]
        if header:
            st += [("BACKGROUND", (0, 0), (-1, 0), GRAPHITE), ("LINEBELOW", (0, 0), (-1, 0), 0.8, GOLD)]
        if zebra:
            for r in range(1 if header else 0, len(rows)):
                if (r - (1 if header else 0)) % 2 == 1:
                    st.append(("BACKGROUND", (0, r), (-1, r), STONE2))
        t.setStyle(TableStyle(st))
        _, h = t.wrap(sum(col_w), 1000)
        t.drawOn(self.c, x, y_top - h)
        return y_top - h

    def bullets(self, items, x, y_top, w, style=BODY, gap=3, marker="—"):
        y = y_top
        for it in items:
            self.c.setFont("FutB", style.fontSize * 0.9)
            self.c.setFillColor(GOLD)
            self.c.drawString(x, y - style.fontSize, marker)
            y = self.para(it, x + 14, y, w - 14, style) - gap
        return y

    def card(self, x, y_top, w, h, title=None, fill=WHITE):
        c = self.c
        c.setFillColor(fill)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.6)
        c.rect(x, y_top - h, w, h, stroke=1, fill=1)
        if title:
            self.label(title, x + 10, y_top - 14)
        return y_top - 24

    def save(self):
        self.c.save()


# ====================================================================
def build():
    d = Deck(OUT)
    c = d.c

    # ---------------- 01 cover ----------------
    d.n += 1
    c.setFillColor(GRAPHITE); c.rect(0, 0, W, H, stroke=0, fill=1)
    d._rail(dark=True)
    # gold ruled field suggesting riffles
    c.setStrokeColor(GOLD_D); c.setLineWidth(0.5)
    for i in range(22):
        yy = 92 + i * 9
        ln = 250 - i * 9.5
        c.setLineWidth(1.6 - i * 0.06)
        c.line(W - 80 - ln, yy, W - 80, yy)
    c.setFont("FutM", 9); c.setFillColor(GOLD)
    c.drawString(LM, H - 78, "GOLDEN INOCALLA MANAGEMENT SERVICES", charSpace=2.4)
    c.setFont("FutXB", 96); c.setFillColor(WHITE)
    c.drawString(LM - 3, H - 185, "LAB X")
    c.setFont("FutXB", 26); c.setFillColor(GOLD)
    c.drawString(LM, H - 222, "Gold Shaking Table Program")
    d.para("Design, specifications and cost model for locally built, commercial-grade gravity concentrating tables "
           "at the SMBC Mercury-Free Processing System, Barangay Casalugan, Paracale — part of the UN-backed planetGOLD sustainable Minahang Bayan agenda. One prototype first, two tables if the ore and the numbers allow.",
           LM, H - 248, 500, LEAD_W)
    c.setFont("FutM", 7.6); c.setFillColor(GOLD)
    c.drawString(LM, 132, "DESIGN LEAD", charSpace=1.6)
    c.setFont("FutXB", 20); c.setFillColor(WHITE)
    c.drawString(LM, 108, "Stephen Lloyd")
    c.setFont("Ch", 9.5); c.setFillColor(MUTE)
    c.drawString(LM, 94, "Head Mechanical Engineer & Designer · Investor and Operational Partner, SMBC processing plant (Board Res. 2026-009)")
    c.setFont("FutM", 7.6); c.setFillColor(GOLD)
    c.drawString(LM, 72, "PROGRAM OWNER", charSpace=1.6)
    c.setFont("FutB", 11); c.setFillColor(WHITE)
    c.drawString(LM, 58, "Golden Inocalla Management Services  ·  Allan Inocalla, Principal")
    c.setFont("Mono", 7.5); c.setFillColor(MUTE)
    c.drawString(LM, 36, f"{VERSION} · {DATE} · Confidential · all costs ESTIMATE / UNQUOTED · blanks and flags mark items still to be clarified")

    # ---------------- 02 program at a glance ----------------
    y = d.page("Program at a glance", "Overview")
    colw = (CW - 24) / 2
    d.card(LM, y, colw, 252, "What we are building")
    d.bullets([
        "A full-size Wilfley / 6-S-class <b>gold shaking table</b> — about 4.5 m long, 1.8 m wide — that separates free gold from sand by density using a short asymmetric shake, a thin film of water and tapered riffles.",
        "<b>Mercury-free.</b> Gravity only; the concentrate is cleaned, not amalgamated.",
        "<b>Built in the Philippines</b> with Camarines Norte / Metro Manila fabricators and installed inside an operating mercury-free plant that Stephen already runs.",
        "<b>Prototype first, then table 2.</b> The first unit is tuned and measured before the second identical unit is ordered.",
    ], LM + 10, y - 30, colw - 20, BODY_S, gap=4)
    d.card(LM + colw + 24, y, colw, 252, "Targets and status")
    x2 = LM + colw + 34
    d.table([
        ["Item", "Value"],
        ["Throughput goal", "10 tonnes per day of gravity feed"],
        ["Number of tables", "2 if possible (1 prototype now; 2nd gated — p.10)"],
        ["Site", "SMBC Mercury-Free Processing System (MFPS), Brgy. Casalugan, Paracale — p.04"],
        ["Design authority", "Stephen Lloyd — also the plant's operating partner"],
        ["Manpower", "Allan Inocalla supplies the site and operating crew"],
        ["Positioning", "Part of the UN-backed (planetGOLD) sustainable Minahang Bayan; a platform for further funding and partners — p.05"],
        ["Program documentation", "LandTek (engineering record, project control)"],
        ["Status", "Design draft v0.1 — no steel cut, no quotes in hand"],
        ["Next hard gate", "Ore gravity test (p.22) + plant equipment inventory (p.17)"],
    ], x2, y - 28, [118, colw - 20 - 118], font_size=8.4)
    y2 = y - 252 - 16
    d.label("Reading this document", LM, y2)
    d.para("Figures that are design choices are stated plainly. Figures that depend on the ore, the site, or a vendor are either "
           "left as a <font face='Mono' size='8'>blank field</font> to be filled in, or carry a flag. "
           "All flags are collected in the clarification register on the last pages, each with an owner.",
           LM, y2 - 8, CW - 200, BODY_S)
    d.flag(RM - 150, y2 - 22, "TO CLARIFY  = open question")
    d.flag(RM - 150, y2 - 40, "ESTIMATE / UNQUOTED", w=150)

    # ---------------- 03 principals (Stephen spotlight) ----------------
    y = d.page("Stephen Lloyd — design lead and plant operator", "Overview · who")
    wl = 560
    d.card(LM, y, wl, 318, "Stephen Lloyd — Head Mechanical Engineer & Designer")
    d.para("<b>Holds design authority for LAB X.</b> Every decision marked D-n in this document is his to make or overrule. "
           "He also operates the site: under <b>SMBC Board Resolution No. 2026-009</b> he is SMBC's <b>Investor and Operational Partner</b> for the rehabilitation, "
           "improvement, management and operation of SMBC's mineral processing plant — the Mercury-Free Processing System at Barangay Casalugan where the tables will be built and run.",
           LM + 10, y - 32, wl - 20, BODY_S)
    d.label("What that puts in his hands", LM + 10, y - 112)
    d.bullets([
        "The <b>reference machinery</b>: an operating gravity circuit on local ore, measurable in-house instead of by visit.",
        "The <b>site services</b>: power, water, milling and classification the plant already runs — the tables plug in, they do not start from bare ground.",
        "The <b>operating team</b> that will commission and run the tables, and the setup-sheet discipline to carry table 1's settings to table 2.",
        "A clear line: SMBC owns the plant; Stephen holds no equity in it; net profits after agreed operating expenses are shared 50/50 between SMBC and Stephen.",
    ], LM + 10, y - 124, wl - 20, BODY_S, gap=4)
    d.blank(LM + 10, y - 262, 255, "Formal title to print")
    d.blank(LM + 285, y - 262, 255, "Credentials approved for print")
    d.flag(LM + 10, y - 300, "TO CLARIFY — C-3 credentials · C-16 executed agreement copy", w=wl - 20)
    xr = LM + wl + 20; wr = RM - xr
    d.card(xr, y, wr, 150, "Golden Inocalla Management Services")
    d.para("Program owner and operating company for LAB X. Allan Inocalla, Principal.", xr + 10, y - 32, wr - 20, BODY_S)
    d.blank(xr + 10, y - 84, wr - 20, "Registered name / form · reg. no.")
    d.blank(xr + 10, y - 122, wr - 20, "Address · TIN · signatories")
    d.flag(xr + 10, y - 146, "C-1 particulars", w=wr - 20)
    d.card(xr, y - 168, wr, 150, "Allan Inocalla — Principal")
    d.para("Principal of the program owner; landholder and Minahang Bayan proponent in Paracale. <b>Supplies the manpower</b>: the site crew and the table operators.",
           xr + 10, y - 200, wr - 20, BODY_S)
    d.blank(xr + 10, y - 264, wr - 20, "Crew: headcount · skills · cost basis")
    d.flag(xr + 10, y - 300, "C-2 role · C-20 manpower terms", w=wr - 20)
    d.para("<i>Nothing about either person is stated beyond their role in this program and what the SMBC resolution records; add only what each has approved for print.</i>",
           LM, y - 336, CW, NOTE)

    # ---------------- 04 the site ----------------
    y = d.page("The site — SMBC Mercury-Free Processing System", "Overview · where")
    colw = (CW - 24) / 2
    d.card(LM, y, colw, 236, "What is on record")
    d.bullets([
        "<b>SMBC</b> — Samahan ng mga Minero sa Barangay Casalugan — is the legally recognised small-scale mining association operating in the declared <b>Minahang Bayan</b> of Paracale, Camarines Norte.",
        "The plant is the <b>Mercury-Free Processing System (MFPS)</b>: a ₱29-million centralised facility established under the <b>planetGOLD Philippines</b> project to eliminate mercury from small-scale gold mining. Managed by SMBC; monitored by the <b>PMRB</b> and <b>MGB Region V</b>.",
        "<b>Board Resolution No. 2026-009</b>: SMBC authorises an Operational Partnership Agreement with Stephen Lloyd as Investor and Operational Partner. SMBC owns the plant; he holds no equity; net profits shared 50/50.",
        "A related draft deal memorandum contemplates a <b>secondary processing station for smaller ore batches on a toll basis</b> once the main plant is upgraded — a natural slot for LAB X.",
    ], LM + 10, y - 30, colw - 20, BODY_S, gap=4)
    xr = LM + colw + 24
    d.card(xr, y, colw, 236, "What it means for the build")
    d.bullets([
        "<b>No greenfield site.</b> The tables stand inside or beside an operating plant with power, water, milling and a tailings system already in place — each to be confirmed, not built.",
        "<b>Reference machinery in-house.</b> If the MFPS gravity circuit carries a shaking table (reported as centrifuge + helix + table), its riffle layout and head motion are measured at home.",
        "<b>Ore from the Minahang Bayan.</b> The ore test is run on what the plant actually receives from SMBC's miners.",
        "<b>Consents.</b> Adding equipment to a PMRB / MGB-V-monitored facility needs SMBC's written consent and a check that the addition sits inside the plant's existing permits and ECC.",
    ], xr + 10, y - 30, colw - 20, BODY_S, gap=4)
    yy = y - 256
    d.label("Open before any steel is ordered", LM, yy)
    d.table([
        ["#", "Item", "Owner"],
        ["C-16", "Copy of the <b>executed</b> Operational Partnership Agreement; SMBC written consent to install and operate LAB X tables at the MFPS", "Stephen"],
        ["C-17", "MFPS equipment inventory: gravity circuit (centrifuge / helix / table?), mill, classifier, power supply, water and tailings system", "Stephen"],
        ["C-18", "Role of the tables: main-circuit cleaning capacity, or the toll-basis secondary station — and who holds title to them (GIMS / SMBC / investor group)", "Allan / Stephen"],
        ["C-19", "Marlon Malaluan's role in operations (named as operator in the draft memo; not in Resolution 2026-009)", "Stephen"],
    ], LM, yy - 10, [40, CW - 40 - 110, 110], mono_cols=(0,), pad=3)

    # ---------------- 05 programme positioning ----------------
    y = d.page("Part of the UN-backed sustainable Minahang Bayan", "Overview · why it matters beyond the plant")
    d.para("<b>LAB X adds locally made, mercury-free gravity capacity inside a facility that exists because of the UN-led planetGOLD programme — "
           "and it is the showcase the partnership uses to bring more money and more participants into a sustainable Minahang Bayan.</b>",
           LM, y, CW, LEAD)
    y -= 40
    colw = (CW - 24) / 2
    d.card(LM, y, colw, 158, "What is on record")
    d.bullets([
        "The MFPS was established under <b>planetGOLD Philippines</b> — the UN Environment Programme-led, GEF-funded programme to eliminate mercury from small-scale gold mining — managed by SMBC under PMRB / MGB-V oversight.",
        "The partnership's own alignment note names the MFPS as <b>the model to replicate across the region</b>, with expansion through Allan's investor network and a public-listing path via a TSX Venture vehicle.",
        "LAB X is the first replicable, locally fabricated piece of that model: mercury-free, repairable on site, crewed locally.",
    ], LM + 10, y - 30, colw - 20, BODY_S, gap=4)
    xr = LM + colw + 24
    d.card(xr, y, colw, 158, "The story, honestly staged")
    d.table([
        ["Stage", "What can be said"],
        ["Today", "Design complete; site and operating partner in place; local build; crew committed"],
        ["After table 1", "Measured recovery on Minahang Bayan ore; mercury-free tonnes processed; local fabrication cost vs import; jobs"],
        ["After table 2", "A replicable unit cost and a commissioning sheet any Minahang Bayan can follow"],
    ], xr + 10, y - 28, [70, colw - 40 - 70], pad=3)
    y -= 174
    d.label("Credentials to deploy — documents only", LM, y)
    d.para("Stephen's and the project's accolades spearhead the funding ask, so they must be its best-documented part: "
           "nothing enters a partner deck without a certificate, letter, published report or dated photograph behind it.",
           LM, y - 10, colw, BODY_S)
    yy = y - 60
    for lab in ["Stephen Lloyd — qualifications, roles, recognitions (documented)", "MFPS / SMBC — planetGOLD milestones, visits, awards, media", "Partnership — investor, LGU, agency endorsements in hand"]:
        d.blank(LM, yy - 14, colw, lab); yy -= 34
    d.flag(LM, yy - 4, "TO CLARIFY — C-21 accolade file, verified documents only", w=colw)
    d.label("Money and involvement — who to approach", xr, y)
    d.table([
        ["Line", "Lead", "Status"],
        ["planetGOLD / UN-GEF follow-on support", "________", "________"],
        ["DENR-MGB · PMRB · LGU programmes", "________", "________"],
        ["Private investors — Allan's network", "Allan", "________"],
        ["Public-market path (TSX-V vehicle, per alignment note)", "________", "________"],
        ["Development partners / NGOs in ASGM", "________", "________"],
    ], xr, y - 10, [colw - 160, 70, 90], mono_cols=(1, 2), pad=2.6)
    d.flag(xr, y - 140, "TO CLARIFY — C-22 funding lines · programme / phase · lead per line", w=colw)

    # ---------------- 04 objective ----------------
    y = d.page("Objective and what success looks like", "Overview")
    d.para("<b>Process 10 tonnes of classified feed per day through a gravity circuit built on locally fabricated shaking tables, "
           "recovering the free gold without mercury, at a build cost far below an imported unit — installed in the SMBC plant Stephen operates, with machines its own shop can repair.</b>",
           LM, y, CW, LEAD)
    y -= 70
    d.table([
        ["Success criterion", "Target", "How it is measured", "Status"],
        ["Throughput", "10 t/day total; 0.5–1.2 t/h per table", "Feed-rate log at the band-smear limit (p.15)", "Design target"],
        ["Gold recovery (free gold)", "________ % of gravity-recoverable gold", "Feed vs tails assay around the table", "TO CLARIFY C-5 — set after ore test"],
        ["Mercury", "Zero", "No amalgamation step anywhere in the circuit", "Design rule"],
        ["Local content", "Frame, deck, head-motion housing, launders, shaft all local; only motor, VFD, bearings, rubber bought in", "BOM source column (p.20)", "Design rule"],
        ["Cost", "Well under an imported 6-S landed cost", "Quoted BOM vs import quote", "Unquoted both sides"],
        ["Repairability", "Every wear part replaceable by the plant's own shop", "Spares list at commissioning", "To be written"],
        ["Table 2", "Ordered only after table 1 is measured", "Decision D-1 with data (p.10)", "Gated"],
        ["Programme visibility", "LAB X presented inside the planetGOLD / sustainable Minahang Bayan frame to draw funding and partners", "Partner engagements and commitments logged (p.05)", "TO CLARIFY C-21 / C-22"],
    ], LM, y, [150, 250, 260, CW - 660], bold_col0=True)

    # ---------------- 05 how it works (diagram) ----------------
    y = d.page("How a shaking table separates gold", "Principle")
    # plan-view deck
    dx, dy, dw, dh = LM + 10, 120, 500, 250
    c.setFillColor(WHITE); c.setStrokeColor(INK); c.setLineWidth(1)
    # slightly narrower at concentrate end
    c.setFillColor(WHITE)
    p = c.beginPath(); p.moveTo(dx, dy); p.lineTo(dx + dw, dy + 18); p.lineTo(dx + dw, dy + dh - 18); p.lineTo(dx, dy + dh); p.close()
    c.drawPath(p, stroke=1, fill=1)
    # riffles: bottom (tailings) edge longest, top shortest; tapered wedges
    N = 26
    for i in range(N):
        t = i / (N - 1)
        yy = dy + 16 + t * (dh - 50)
        L = (dw - 30) * (1 - 0.74 * t)
        w0 = 2.4 * (1 - 0.25 * t)
        c.setFillColor(GOLD)
        pp = c.beginPath(); pp.moveTo(dx + 14, yy - w0 / 2); pp.lineTo(dx + 14 + L, yy - 0.2); pp.lineTo(dx + 14 + L, yy + 0.2); pp.lineTo(dx + 14, yy + w0 / 2); pp.close()
        c.drawPath(pp, stroke=0, fill=1)
    # cleaning plane label
    c.setFont("ChI", 8.5); c.setFillColor(MUTE)
    c.drawString(dx + dw - 175, dy + dh - 60, "cleaning plane (no riffles)")
    c.drawString(dx + dw - 175, dy + dh - 71, "fine heavies get their final wash here")
    # wash water along top edge
    c.setStrokeColor(SLATE); c.setLineWidth(1.4)
    for k in range(9):
        xx = dx + 60 + k * 58
        ytop = dy + dh - 2 + (18 * (xx - dx) / dw) * -1 + 2
        c.line(xx, dy + dh + 14 - 18 * (xx - dx) / dw, xx, dy + dh - 10 - 18 * (xx - dx) / dw)
    c.setFont("FutM", 7); c.setFillColor(SLATE)
    c.drawString(dx + 60, dy + dh + 22, "WASH WATER — ACROSS THE RIFFLES", charSpace=1.2)
    # feed box
    c.setFillColor(STONE2); c.setStrokeColor(INK); c.setLineWidth(0.8)
    c.rect(dx - 2, dy + dh - 40, 44, 52, stroke=1, fill=1)
    c.setFont("FutM", 6.5); c.setFillColor(INK); c.drawString(dx + 4, dy + dh - 18, "FEED"); c.drawString(dx + 4, dy + dh - 28, "BOX")
    # head motion
    c.setFillColor(GRAPHITE); c.rect(dx - 40, dy + 70, 36, 90, stroke=0, fill=1)
    c.setFillColor(WHITE); c.setFont("FutM", 6.2)
    c.saveState(); c.translate(dx - 26, dy + 78); c.rotate(90); c.drawString(0, 0, "HEAD MOTION", charSpace=1); c.restoreState()
    # stroke arrow
    c.setStrokeColor(INK); c.setLineWidth(1.2)
    c.line(dx + 40, dy - 16, dx + 120, dy - 16); c.line(dx + 120, dy - 16, dx + 113, dy - 12); c.line(dx + 120, dy - 16, dx + 113, dy - 20)
    c.line(dx + 40, dy - 16, dx + 47, dy - 12); c.line(dx + 40, dy - 16, dx + 47, dy - 20)
    c.setFont("Ch", 8); c.setFillColor(INK); c.drawString(dx + 128, dy - 19, "shake: slow forward, fast return — 12–16 mm, ~300/min")
    # products
    c.setFillColor(GOLD_D); c.setFont("FutB", 8)
    c.drawString(dx + dw + 8, dy + dh - 40, "CONCENTRATE")
    c.setFillColor(SLATE); c.drawString(dx + dw + 8, dy + dh / 2 - 4, "MIDDLINGS")
    c.setFillColor(MUTE); c.drawString(dx + dw + 8, dy + 30, "TAILINGS")
    c.setFont("Ch", 8); c.setFillColor(MUTE); c.drawString(dx + 150, dy - 34, "lights wash off the long lower edge as tailings")
    # right column text
    xr = LM + 610
    d.label("The mechanism", xr, y - 4)
    d.bullets([
        "Feed slurry enters at the upper corner; wash water sheets across the deck at right angles to the riffles.",
        "The deck moves slowly forward and snaps back. On the snap the bed slides relative to the deck, and the <b>densest grains crawl along the riffles</b> toward the far end.",
        "Riffles <b>taper lower</b> toward that end: lights get washed over each successively lower barrier and off the side; heavies keep going.",
        "Heavies leave the riffle ends onto the unriffled <b>cleaning plane</b>, are rinsed once more, and discharge as concentrate; middlings below them are re-fed.",
        "Everything depends on the stroke shape being true in the ground frame — which is why the machine must stand on a rigid foundation (p.13).",
    ], xr, y - 20, RM - xr, BODY_S, gap=5)

    # ---------------- 06 section: design ----------------
    y = d.page("Design", "Section 1", dark=True)
    c.setFont("FutXB", 60); c.setFillColor(GOLD); c.drawString(LM - 2, H - 230, "The machine")
    d.para("Design basis · circuit · deck and riffles · head motion and eccentric shaft · frame and foundation · water, feed and power · operating settings.",
           LM, H - 262, 600, LEAD_W)

    # ---------------- 07 design basis ----------------
    y = d.page("Design basis — one prototype table", "Design")
    d.table([
        ["Parameter", "Specification", "Note"],
        ["Deck", "≈ 4.5 m long × 1.8 m wide at the head end, concentrate end slightly narrower", "Standard full-size 6-S class"],
        ["Deck construction", "Welded steel skeleton, 3–4 mm plate or 6 mm marine-ply skin, 8–12 mm abrasion-grade rubber/EPDM lining, tapered riffles", "FRP deck deferred to table 2 (D-6)"],
        ["Capacity", "0.5–1.2 t/h of ≤ 2 mm feed at 15–30 % solids", "Strongly dependent on feed size — ore test"],
        ["Stroke", "Adjustable 8–22 mm; commission at 12–16 mm", "Hand-wheel / threaded stop"],
        ["Frequency", "240–360 strokes/min; commission at 280–320", "VFD-controlled"],
        ["Cross (side) slope", "Adjustable 0–8°; commission at ≈ 3°", "Screw jacks"],
        ["End slope", "Level to concentrate end raised ≤ 1°", "Tuning parameter"],
        ["Drive", "1.1–1.5 kW electric motor, V-belt to eccentric shaft, toggle/pitman head motion, heavy driven pulley as flywheel", "Motor type per power supply (p.14)"],
        ["Empty weight", "≈ 600–900 kg", "Weigh the finished unit"],
        ["Footprint", "≈ 6 m × 3 m incl. launders + working space both long sides", ""],
        ["Water", "≈ 1–3 m³/h wash + feed water, recycled", "Settling pond / tank — site item"],
        ["Power", "220 V; 3-phase preferred, single-phase workable via 1-ph-in / 3-ph-out VFD", "Plant supply phase and spare kW — C-8"],
        ["Operator", "1 person once tuned", ""],
    ], LM, y, [130, 470, CW - 600], bold_col0=True)

    # ---------------- 08 circuit A vs B ----------------
    y = d.page("One table or two — it depends on the circuit", "Design · decision D-1")
    d.para("A full-size table is normally a <b>cleaner</b>, not a rougher. Whether the program needs two tables for 10 t/day is a question about what sits upstream of the table, not about the table.",
           LM, y, CW, LEAD)
    y -= 58
    colw = (CW - 24) / 2
    d.card(LM, y, colw, 230, "Circuit A — the table roughs the whole feed")
    d.bullets([
        "Mill → classify (≤ 2 mm) → <b>shaking table</b> → concentrate.",
        "Each table sees the full 10 t/day: ≈ 0.5–0.6 t/h over 18–20 h.",
        "<b>Two tables required</b> — one is marginal with zero redundancy and no room for finer feed.",
        "Simplest circuit; most deck area per tonne; highest table count.",
    ], LM + 10, y - 30, colw - 20, BODY_S, gap=5)
    d.card(LM + colw + 24, y, colw, 230, "Circuit B — a rougher ahead of the table")
    d.bullets([
        "Mill → classify → <b>centrifugal bowl or spiral/helix</b> → shaking table cleans the concentrate.",
        "The table sees a few percent of plant tonnage. <b>One table has capacity to spare.</b>",
        "Extra machine upstream (bought or built) — but better fine-gold recovery and a cleaner concentrate.",
        "Reportedly how the MFPS itself is arranged (centrifuge + helix + table, ≈ 3.5 t/day) — to be confirmed from the plant inventory (C-17). If so, LAB X adds table capacity to a circuit that already roughs.",
    ], LM + colw + 34, y - 30, colw - 20, BODY_S, gap=5)
    y -= 248
    d.label("Decision path", LM, y)
    d.para("The prototype is the same machine under either circuit, so fabrication is not blocked. The ore gravity test (p.22) tells us how fine the gold is; fine gold favours B. "
           "At the MFPS a third use exists: the tables as the <b>toll-basis secondary station</b> for smaller ore batches (C-18). Decision D-1 is taken by Stephen and Allan with the test result and the plant inventory in hand, before table 2 is ordered.",
           LM, y - 10, CW - 260, BODY_S)
    d.flag(RM - 230, y - 8, "TO CLARIFY — C-4 circuit A or B", w=230)
    d.blank(RM - 230, y - 40, 230, "Decision D-1 and date")

    # ---------------- 09 deck & riffles ----------------
    y = d.page("Deck and riffles", "Design · D-6, D-7")
    d.table([
        ["Riffle parameter", "Specification"],
        ["Direction", "Parallel to the long axis — the direction of shake"],
        ["Pitch", "30–35 mm centre-to-centre (use 32 mm)"],
        ["Section", "8–10 mm wide; 8–10 mm high at the head end tapering to 1–2 mm (feather) at the riffle's own end"],
        ["Count", "Riffled band ≈ 1.5 m wide ÷ 32 mm ≈ 45–48 riffles"],
        ["Lengths", "Longest on the lower (tailings) edge ≈ 4.0 m; shortest near the wash-water edge ≈ 1.0 m; ends on a straight diagonal"],
        ["Cleaning plane", "The unriffled triangle this leaves at the upper concentrate corner — a quarter to a third of the deck. Never riffled."],
        ["Fixing", "Removable: polyurethane adhesive bead + stainless countersunk screws every 250–300 mm through riffle and rubber into the skeleton"],
        ["Material (prototype)", "Dense water-stable hardwood (yakal / molave) or strips ripped from 12 mm marine ply; sealed with epoxy or marine varnish"],
        ["Material (table 2)", "Rubber strip (stepped or sanded taper) or riffles moulded into an FRP deck once the layout is proven"],
    ], LM, y, [130, 460], bold_col0=True)
    # taper diagram
    xr = LM + 612; ytop = y - 6
    d.label("Riffle profile — side view", xr, ytop)
    c.setFillColor(GOLD); pth = c.beginPath()
    pth.moveTo(xr, ytop - 60); pth.lineTo(xr + 200, ytop - 60); pth.lineTo(xr + 200, ytop - 57); pth.lineTo(xr, ytop - 34); pth.close()
    c.drawPath(pth, stroke=0, fill=1)
    c.setFillColor(STONE2); c.rect(xr - 6, ytop - 70, 214, 10, stroke=0, fill=1)
    c.setFont("Mono", 7); c.setFillColor(INK)
    c.drawString(xr - 4, ytop - 28, "10 mm"); c.drawString(xr + 176, ytop - 50, "1.5 mm")
    c.drawString(xr + 70, ytop - 80, "head end ← riffle length → tail")
    c.setFont("Ch", 8); c.setFillColor(MUTE); c.drawString(xr - 6, ytop - 92, "rubber lining under; screws below the riffle top")
    d.label("Lining", xr, ytop - 118)
    d.para("8–12 mm abrasion-grade rubber / EPDM, bonded and bolted to the skeleton. Local conveyor-grade rubber for the prototype; "
           "imported Linatex-class only if wear rate proves it necessary.", xr, ytop - 128, RM - xr, BODY_S)
    d.flag(xr, ytop - 200, "TO CLARIFY — C-6 copy a reference deck", w=RM - xr)
    d.para("<i>Before any riffle is cut: photograph and measure an operating 6-S deck on local ore (see p.17) and copy it. "
           "The numbers at left are textbook-class; the reference deck is proven.</i>", xr, ytop - 214, RM - xr, NOTE)

    # ---------------- 10 head motion ----------------
    y = d.page("Head motion and eccentric shaft", "Design · the critical part · D-4")
    d.para("The eccentric shaft converts motor rotation into the slow-forward / fast-return stroke. It is the one precision part in the machine and the longest lead item — it goes to a lathe shop with the specification below.",
           LM, y, CW, BODY)
    y -= 40
    d.table([
        ["Feature", "Dimension", "Tolerance / finish"],
        ["Material", "AISI 1045 / S45C medium-carbon bar; optional Q&T 28–35 HRC", "As-machined acceptable with sealed bearings"],
        ["Overall length", "300–450 mm, fixed after housing design", "Stock left for centres"],
        ["Main journals ×2", "Ø50 mm (Ø45–55), 40–60 mm long", "h6/g6 to bearing; Ra ≤ 0.8 µm; concentric ≤ 0.03 mm TIR"],
        ["Eccentric lobe", "Ø60–80 mm × 40–60 mm; throw 8 mm initial (4–12.5 range)", "Throw ±0.05 mm; parallel to main axis"],
        ["Drive end", "Keyed for pulley (12×8 key or to suit); shoulder / lock-nut", ""],
        ["Counterweight", "Bolt pattern opposite the lobe for bolt-on plates", "Field-adjustable static balance"],
        ["Bearings", "UCP pillow blocks on journals; big-end bearing or bronze bush on the lobe", "Grease nipples"],
    ], LM, y, [120, 300, CW - 420 - 250], bold_col0=True)
    # schematic
    xs = RM - 240; ys = y - 6
    d.label("Schematic — side view", xs, ys)
    c.setStrokeColor(INK); c.setLineWidth(1); c.setFillColor(STONE2)
    c.circle(xs + 30, ys - 70, 22, stroke=1, fill=1)   # motor
    c.setFont("FutM", 6); c.setFillColor(INK); c.drawCentredString(xs + 30, ys - 73, "MOTOR")
    c.setFillColor(STONE2); c.circle(xs + 120, ys - 60, 30, stroke=1, fill=1)  # flywheel
    c.setFillColor(GOLD); c.circle(xs + 128, ys - 60, 5, stroke=0, fill=1)   # eccentric
    c.setFillColor(INK); c.drawCentredString(xs + 120, ys - 98, "FLYWHEEL + ECCENTRIC")
    c.setStrokeColor(MUTE); c.setDash(2, 2); c.line(xs + 30, ys - 48, xs + 120, ys - 30); c.line(xs + 30, ys - 92, xs + 120, ys - 90); c.setDash()
    c.setStrokeColor(INK); c.line(xs + 128, ys - 60, xs + 190, ys - 40)  # pitman
    c.setFillColor(INK); c.setFont("FutM", 6); c.drawString(xs + 150, ys - 38, "PITMAN")
    c.line(xs + 190, ys - 40, xs + 190, ys - 10); c.line(xs + 190, ys - 10, xs + 235, ys - 10)  # toggle to deck
    c.setFillColor(GOLD); c.rect(xs + 200, ys - 14, 40, 8, stroke=0, fill=1)
    c.setFillColor(INK); c.drawString(xs + 200, ys - 26, "DECK")
    # spring
    c.setStrokeColor(SLATE); c.setLineWidth(1.2)
    zx = xs + 190; zy = ys - 40
    for k in range(6):
        c.line(zx + k * 6, zy - 8 if k % 2 else zy + 0, zx + (k + 1) * 6, zy + 0 if k % 2 else zy - 8)
    c.setFillColor(SLATE); c.drawString(xs + 190, ys - 56, "RETURN SPRING")
    d.para("The toggle and return spring make the return faster than the forward stroke. A stroke-adjusting stop on the toggle, or an adjustable eccentric sleeve, sets the stroke without re-machining.",
           xs, ys - 118, 240, BODY_S)
    d.flag(xs, ys - 180, "TO CLARIFY — C-7 measure a 6-S head motion", w=240)

    # ---------------- 11 frame & foundation ----------------
    y = d.page("Frame, supports and foundation", "Design · D-5, D-8")
    colw = (CW - 24) / 2
    d.card(LM, y, colw, 300, "Frame and deck supports")
    d.bullets([
        "<b>Base frame</b>: 150×75 or 200×75 mild-steel channel with 50–65 mm angle bracing; four or six feet drilled for M16–M20 anchors. Stiff and square — no flex when a corner is loaded.",
        "<b>Deck skeleton</b>: flat bar and angle, skinned, flat to within ≈ 2 mm over its length.",
        "<b>Supports</b>: four to six flexure legs (spring-steel strip or stacked leaf) that let the deck move only lengthwise — fewer wear parts than rocker stands (D-5 default).",
        "<b>Slope adjustment</b>: M16–M20 screw jacks for side and end tilt, adjustable while running.",
        "<b>Motor mount</b> on slotted rails for belt tension; guard over belt and pulley.",
        "<b>Finish</b>: primer + industrial topcoat — everything sits wet.",
    ], LM + 10, y - 30, colw - 20, BODY_S, gap=5)
    d.card(LM + colw + 24, y, colw, 300, "Foundation — rigid, not isolated")
    xr = LM + colw + 34
    d.bullets([
        "<b>Concrete pad</b> ≈ 5.5 m × 2.5 m × 0.3 m (≈ 4 m³, ≈ 10 t) — an order of magnitude heavier than the machine — inside or beside the MFPS, where the plant's existing floor slab may already serve if thick enough. Single reinforcing mat; cast-in anchors; top level to ±3 mm.",
        "<b>Why rigid</b>: the gold crawls because the stroke shape is true in the ground frame. On soft mounts a ~600 kg base moves in antiphase with a 200–300 kg moving deck and the stroke degrades. <b>No coil springs.</b>",
        "Thin (10–15 mm) rubber under the feet <i>only</i> if structure-borne noise becomes a problem.",
        "<b>Drainage</b>: surrounding slab falls to a sump; the tailings launder must run away freely.",
        "<b>Trial alternative</b>: a ≥ 1.5 t steel skid pinned to the ground — acceptable for trials, not for production.",
    ], xr, y - 30, colw - 20, BODY_S, gap=5)
    d.flag(xr, y - 284, "TO CLARIFY — C-9 location in the plant, existing slab, concrete quote", w=colw - 20)

    # ---------------- 12 water, feed, power ----------------
    y = d.page("Water, feed preparation and power", "Design · site interfaces")
    colw3 = (CW - 40) / 3
    d.card(LM, y, colw3, 280, "Water")
    d.bullets([
        "≈ 1–3 m³/h wash water plus feed dilution water, recycled through the plant's existing water and tailings system if it has the capacity.",
        "Wash bar: PVC or stainless pipe with holes / nozzles along the feed side, ball-valve controlled; must give an even sheet with no dry strips.",
        "Three launders — concentrate, middlings, tailings — in plate, PVC or stainless.",
    ], LM + 10, y - 30, colw3 - 20, BODY_S, gap=5)
    d.blank(LM + 10, y - 190, colw3 - 20, "Plant water supply and spare capacity")
    d.blank(LM + 10, y - 228, colw3 - 20, "Plant tailings / settling arrangement")
    d.flag(LM + 10, y - 262, "TO CLARIFY — C-10", w=colw3 - 20)
    xb = LM + colw3 + 20
    d.card(xb, y, colw3, 280, "Feed preparation")
    d.bullets([
        "The table wants ≤ 2 mm, preferably deslimed, 15–30 % solids. Coarser material must be screened; ultrafines hurt performance.",
        "The MFPS already mills and classifies — the tables take their feed from that circuit or from the secondary-station batch mill. Its capacity, not the tables, sets the real tonnage.",
    ], xb + 10, y - 30, colw3 - 20, BODY_S, gap=5)
    d.blank(xb + 10, y - 160, colw3 - 20, "MFPS mill / crusher and capacity")
    d.blank(xb + 10, y - 198, colw3 - 20, "MFPS classification (screen / cyclone)")
    d.blank(xb + 10, y - 236, colw3 - 20, "Feed size distribution (from ore test)")
    d.flag(xb + 10, y - 262, "TO CLARIFY — C-11", w=colw3 - 20)
    xc = LM + 2 * (colw3 + 20)
    d.card(xc, y, colw3, 280, "Power")
    d.bullets([
        "Motor 1.1–1.5 kW. Default (D-3): 3-phase motor + a single-phase-input / three-phase-output VFD, so stroke frequency is dialled from a panel.",
        "The MFPS already has a power supply. Its phase and spare capacity for two more 1.5 kW drives decide the motor, VFD and starter.",
        "Emergency stop at the operator position; motor starter / contactor; cable and conduit rated for a wet site.",
    ], xc + 10, y - 30, colw3 - 20, BODY_S, gap=5)
    d.blank(xc + 10, y - 198, colw3 - 20, "Plant supply: phase · voltage · spare kW")
    d.blank(xc + 10, y - 236, colw3 - 20, "Plant generator backup (kVA)")
    d.flag(xc + 10, y - 262, "TO CLARIFY — C-8", w=colw3 - 20)

    # ---------------- 13 operating settings ----------------
    y = d.page("Operating settings and field tuning", "Design · commissioning")
    d.table([
        ["Feed class", "Cross slope", "Stroke", "Strokes / min", "Wash water", "Feed solids"],
        ["Coarse sand 0.5–2 mm", "4–6°", "16–22 mm", "240–280", "higher ≈ 2–3 m³/h", "20–30 %"],
        ["Fine sand 0.1–0.5 mm", "2.5–4°", "11–16 mm", "280–320", "medium ≈ 1.5–2 m³/h", "20–25 %"],
        ["Slimes < 0.1 mm", "1–2.5°", "8–12 mm", "320–360", "low ≈ 1–1.5 m³/h", "15–20 %"],
    ], LM, y, [150, 90, 90, 100, 140, 90], bold_col0=True, mono_cols=(1, 2, 3, 5))
    d.para("<i>Published 6-S / Wilfley-class starting ranges. End slope: start level, raise the concentrate end in small steps (≤ 1°) only if lights reach the concentrate end. "
           "Use slope first, water second — too much water washes fine gold away.</i>", LM, y - 96, 660, NOTE)
    yy = y - 142
    d.label("Field tuning — the commissioning routine", LM, yy)
    steps = [
        ("Level", "spirit level on the riffle tops, both ways; record jack positions."),
        ("Dry run", "lowest speed; trace the stroke with pencil and card; listen for knock; tune the counterweight until the frame is quiet."),
        ("Water only", "cross slope ≈ 3°; the sheet must cross every riffle evenly — fix the spray bar before feeding anything."),
        ("Feed low", "a third of target, classified material; within minutes a diagonal band forms."),
        ("Read the band", "heavies at the tailings edge → less slope / water · sand at the concentrate end → more slope / water / raise the end · smeared band → shorter-faster (fines) or longer-slower (coarse) stroke · riffles packing → stroke too short or feed too thick."),
        ("Raise feed", "stepwise until the band smears, then back off ≈ 20 % — that is the table's real capacity on that ore."),
        ("Log", "jack turns, VFD Hz, stroke, water valve, feed rate + a photo of the band → the setup sheet for table 2."),
    ]
    rows = [["#", "Step", "What to do"]] + [[str(i + 1), a, b] for i, (a, b) in enumerate(steps)]
    d.table(rows, LM, yy - 10, [24, 80, CW - 104], bold_col0=False, mono_cols=(0,), pad=3)

    # ---------------- 14 section: build ----------------
    y = d.page("Build", "Section 2", dark=True)
    c.setFont("FutXB", 60); c.setFillColor(GOLD); c.drawString(LM - 2, H - 230, "Local fabrication")
    d.para("Who makes what · build sequence and gates · schedule.", LM, H - 262, 600, LEAD_W)

    # ---------------- 15 fabrication plan ----------------
    y = d.page("Local fabrication — who makes what", "Build")
    d.table([
        ["Scope", "Made by", "Where (candidates)", "Quote"],
        ["Base frame, legs, deck skeleton, supports, jacks, motor mount, launders, assembly, paint", "General fabrication / welding shop (one primary shop)", "Daet / Paracale area shops; Double R Steel (Daet) for sections; Metro Manila shops if local capacity is short", "________"],
        ["Eccentric shaft; pulley machining; bushes", "Lathe / machine shop", "Daet, Paracale, Naga or Quezon City precision shops", "________"],
        ["Rubber lining supply", "Industrial rubber supplier", "Matlex, Dela Torre & Co., conveyor-rubber dealers (Manila)", "________"],
        ["Motor, VFD, bearings, belts, fasteners", "Bought in", "Industrial motor houses and hardware, QC / Manila / online industrial sellers", "________"],
        ["Riffles (cut, taper, seal, fit)", "Allan's crew with the plant shop", "At the MFPS", "________"],
        ["Concrete pad, anchors, drainage", "Allan's crew under a local contractor / mason", "Casalugan, inside / beside the MFPS", "________"],
        ["Site labour — installation, plumbing, commissioning help, table operators", "<b>Allan Inocalla — supplied manpower</b>", "At the MFPS", "C-20"],
        ["Design drawings, shop sketches, QA", "Stephen Lloyd", "—", "—"],
    ], LM, y, [250, 150, 330, CW - 730], bold_col0=True, mono_cols=(3,))
    yy = y - 232
    d.label("Reference unit", LM, yy)
    d.para("The fastest route to proven geometry is to measure an operating table on local ore — riffle layout, deck supports, toggle geometry, eccentric throw. "
           "Stephen operates the MFPS; if its gravity circuit carries a shaking table, that measurement happens in-house, by him, at no cost. If it does not, a visit to another planetGOLD-class unit is arranged.",
           LM, yy - 10, CW - 280, BODY_S)
    d.flag(RM - 250, yy - 8, "TO CLARIFY — C-6 / C-7 / C-17 table at the MFPS?", w=250)
    d.blank(RM - 250, yy - 40, 250, "Unit measured · by · date")

    # ---------------- 16 sequence & schedule ----------------
    y = d.page("Build sequence, gates and schedule", "Build")
    seq = [
        ("Ore gravity test", "Allan / Stephen", "GATE — sets stroke, slope, riffle height; decides D-1", "____ wks"),
        ("MFPS equipment inventory; measure the plant's own table / head motion", "Stephen", "GATE for riffle layout and head-motion geometry; in-house", "____ wks"),
        ("Freeze dimensions; shop sketches; three fabrication quotes", "Stephen", "Replaces every estimate on p.20 with a quote", "____ wks"),
        ("Eccentric shaft machined", "Lathe shop", "Critical path — longest lead", "____ wks"),
        ("Frame → skeleton → supports → head-motion housing → launders", "Fabricator", "", "____ wks"),
        ("Rubber bonded; riffles cut, sealed, fitted", "Fabricator / plant shop", "After the ore test and the reference measurement", "____ wks"),
        ("Dry run and balance on the shop floor", "Stephen + fabricator", "", "____ days"),
        ("SMBC consent in writing; pad cast at the MFPS (cure ≥ 7 days)", "Stephen / local contractor", "Consent first (C-16); pad in parallel with fabrication", "____ wks"),
        ("Set, anchor, plumb water, wire motor + VFD + E-stop", "Allan's crew + fabricator / electrician", "", "____ days"),
        ("Wet commissioning and setup sheet", "Stephen + Allan's operators", "Measured capacity and band quality", "____ days"),
        ("Decision: table 2", "Allan / Stephen", "D-1 with data; order an identical unit", "—"),
    ]
    rows = [["#", "Step", "Owner", "Gate / note", "Duration"]] + [[str(i + 1), a, b, cnote, dur] for i, (a, b, cnote, dur) in enumerate(seq)]
    yb = d.table(rows, LM, y, [22, 300, 130, 290, CW - 742], mono_cols=(0, 4), pad=3)
    d.flag(LM, yb - 28, "TO CLARIFY — C-12 durations and target commissioning date", w=330)
    d.blank(LM + 350, yb - 30, 220, "Target commissioning date")

    # ---------------- 17 section: cost ----------------
    y = d.page("Cost model", "Section 3", dark=True)
    c.setFont("FutXB", 60); c.setFillColor(GOLD); c.drawString(LM - 2, H - 230, "What it costs")
    d.para("Bill of materials per table · program model for one and two tables · what the estimates rest on. "
           "Every peso figure is an ESTIMATE from desk research, not a vendor quote; the quote column is blank on purpose.",
           LM, H - 262, 640, LEAD_W)

    # ---------------- 18 BOM ----------------
    y = d.page("Bill of materials and cost — one table", "Cost model · ESTIMATE / UNQUOTED")
    bom = [
        ("Structural steel (channel, SHS, angle, plate, flat bar; deck skin)", "450–550 kg", "Daet yards / Manila service centres", 35000, 48000),
        ("Deck lining — abrasion-grade rubber / EPDM 8–12 mm", "12–15 m²", "Matlex, Dela Torre, conveyor-rubber dealers", 18000, 35000),
        ("Riffles — hardwood strips, adhesive, SS screws", "45–50 pcs", "Local lumber / hardware", 3000, 8000),
        ("Motor 1.1 kW 3-ph TEFC (or 1.5 HP 1-ph)", "1", "Industrial motor houses", 6000, 15000),
        ("VFD 1.5 kW, 1-ph in / 3-ph out", "1", "Industrial / online sellers", 5000, 10000),
        ("Pulleys + V-belt (heavy driven pulley as flywheel)", "1 set", "Local casting / machining or stock", 3000, 8000),
        ("Eccentric shaft — AISI 1045 bar, machined to spec", "1", "Lathe shop", 8000, 18000),
        ("Bearings — UCP pillow blocks; big-end bearing / bush", "4–6", "Industrial hardware", 2000, 6000),
        ("Head-motion parts — rod, toggle, spring, adjuster, housing", "1 set", "Fabricator + lathe shop", 6000, 12000),
        ("Deck supports — flexures / rockers; screw jacks", "1 set", "Fabricator", 4000, 8000),
        ("Feed box, spray bar, launders, hose, drains", "1 set", "Fabricator + plumbing supply", 5000, 10000),
        ("Anchor bolts, fasteners, grease nipples", "lot", "Hardware", 3000, 6000),
        ("Primer, topcoat, sealant, epoxy", "lot", "Hardware", 3000, 5000),
        ("Fabrication labour — cutting, welding, assembly, fitting", "", "One primary shop", 45000, 75000),
    ]
    lo = sum(b[3] for b in bom); hi = sum(b[4] for b in bom)
    rows = [["Item", "Qty", "Likely source", "Est. low ₱", "Est. high ₱", "Quote ₱"]]
    for a, q, s, l, h in bom:
        rows.append([a, q, s, f"{l:,}", f"{h:,}", "________"])
    rows.append(["<b>Total — one table (materials + local fabrication)</b>", "", "", f"<b>{lo:,}</b>", f"<b>{hi:,}</b>", "________"])
    d.table(rows, LM, y, [300, 52, 230, 80, 80, CW - 742], mono_cols=(3, 4, 5), pad=2.6, font_size=8)
    d.para(f"<i>Excludes: concrete pad, water tank / pump, feed preparation, site electrical run, transport. Planning mid-point carried from the design chat: ₱160,000–190,000 per table. "
           f"Basis: mid-2026 desk research on Philippine steel, motor, rubber and shop-labour prices — not quotes.</i>", LM, y - 372, CW - 220, NOTE)
    d.flag(RM - 200, y - 372, "C-13 replace with quotes", w=200)

    # ---------------- 19 program cost model ----------------
    y = d.page("Program cost model — one table vs two", "Cost model · ESTIMATE / UNQUOTED")
    cont = 0.15
    def rng(a, b): return f"{a:,} – {b:,}"
    rows = [
        ["Line", "1 table (prototype)", "2 tables", "Basis / status"],
        ["Tables — materials + fabrication (p.20)", rng(lo, hi), rng(2 * lo, 2 * hi), "Sum of the BOM; table 2 identical, no design time"],
        ["Design, drawings, QA (Stephen)", "________", "________", "TO CLARIFY C-14 — internal or billed?"],
        ["Pad inside / beside the MFPS, anchors, drainage", "________", "________", "Local contractor quote — C-9"],
        ["Water tie-in to the plant system (or tank / pump if short)", "________", "________", "Plant capacity — C-10"],
        ["Feed tie-in (screen / classifier; batch mill for the secondary station)", "________", "________", "Plant inventory — C-11 / C-17"],
        ["Electrical tie-in (panel, cable, VFDs, E-stop; supply upgrade if short)", "________", "________", "Plant supply — C-8"],
        ["Transport Manila ↔ Paracale; crane / handling", "________", "________", "If Manila fabrication is used"],
        ["Ore test (sampling, assay, lab table)", "________", "—", "C-5 — first spend in the program"],
        ["Reference measurement (in-house if the MFPS has a table; else travel)", "________", "—", "C-6 / C-7 / C-17"],
        ["Site labour and operators — crew supplied by Allan", "________", "________", "In-kind or costed — C-20"],
        ["Spares kit (bearings, belt, rubber offcuts, riffle stock)", "________", "________", "Write at commissioning"],
        [f"Contingency on table cost ({int(cont*100)} %)", rng(int(lo * cont), int(hi * cont)), rng(int(2 * lo * cont), int(2 * hi * cont)), "Design-stage allowance"],
        ["<b>Subtotal — tables + contingency only</b>", f"<b>{rng(int(lo*(1+cont)), int(hi*(1+cont)))}</b>", f"<b>{rng(int(2*lo*(1+cont)), int(2*hi*(1+cont)))}</b>", "All other lines blank until quoted"],
        ["<b>Program total</b>", "<b>________</b>", "<b>________</b>", "Fill when the blanks above are quoted"],
    ]
    d.table(rows, LM, y, [290, 150, 150, CW - 590], mono_cols=(1, 2), pad=3)
    d.para("<i>Two tables cost roughly twice the table line and share the pad, water, feed preparation and electrical lines (size those once, for two). "
           "The comparison that matters for decision D-1 is: second table vs more rougher capacity upstream — and whether the tables are main-circuit cleaners or the toll-basis secondary station (C-18). Title to the tables (C-18) decides whose balance sheet carries them.</i>", LM, y - 356, CW, NOTE)

    # ---------------- 20 ore & performance assumptions ----------------
    y = d.page("Ore test and performance assumptions", "Cost model · the numbers the model rests on")
    d.para("Every capacity and recovery figure in this document assumes free-milling gold liberated below ≈ 2 mm. Paracale ores are frequently sulfide-associated; "
           "if much of the gold is locked in pyrite or arsenopyrite, gravity alone recovers a fraction of it no matter how well the table is built. "
           "The ore test is therefore the first spend in the program and a hard gate before riffles are cut.", LM, y, CW, BODY)
    y -= 64
    colw = (CW - 24) / 2
    d.card(LM, y, colw, 250, "Gravity-recoverable-gold test — to run")
    d.bullets([
        "Representative 20–50 kg sample of what the MFPS actually receives from SMBC's Minahang Bayan miners (not a grab from the richest spot).",
        "Stage-grind; at each stage, pan or lab-table the product and assay concentrate and tails.",
        "Outputs: size distribution of the gold, gravity-recoverable fraction, liberation size, slime content.",
        "Lab: ________ (MGB regional lab, a university mineral-processing lab, or the planetGOLD facility).",
    ], LM + 10, y - 30, colw - 20, BODY_S, gap=5)
    d.flag(LM + 10, y - 232, "TO CLARIFY — C-5 ore test: lab, cost, date", w=colw - 20)
    xr = LM + colw + 24
    d.card(xr, y, colw, 250, "Fill in when the result is back")
    yy = y - 44
    for lab in ["Gravity-recoverable gold (% of head grade)", "Head grade (g/t) and sample source", "P80 / liberation size (µm)", "Slime (< 20 µm) fraction (%)", "Recovery target adopted for the program (%)"]:
        d.blank(xr + 10, yy - 14, colw - 20, lab); yy -= 40

    # ---------------- 21 risks & gates ----------------
    y = d.page("Risks and gates", "Program")
    d.table([
        ["Risk", "Effect", "Mitigation / gate", "Owner"],
        ["Gold is sulfide-locked, not free", "Gravity recovery far below expectation; tables under-used", "Ore test before riffles are cut; consider flotation / leach downstream as a separate study", "Allan / Stephen"],
        ["Head motion built from guesswork", "Wrong stroke shape → poor separation, bearing wear", "Measure a reference 6-S head motion; keep stroke adjustable; dial-indicate the shaft", "Stephen"],
        ["Soft or light foundation", "Stroke degrades; machine walks", "≈ 10 t concrete pad, cast-in anchors; no springs", "Stephen / contractor"],
        ["Wrong power assumption", "Motor or VFD unusable on site", "Confirm the plant supply phase and spare capacity before buying the motor", "Stephen"],
        ["Rubber lining wears fast", "Downtime, recovery loss", "Local conveyor-grade first; log wear; upgrade to Linatex-class if needed", "Stephen"],
        ["Costs drift above estimate", "Program over budget", "Three quotes per scope; contingency 15 %; no order before the BOM is quoted", "Stephen"],
        ["Feed preparation missing", "Table starved or over-sized feed", "Define the upstream circuit and its capacity (C-11)", "Allan / Stephen"],
        ["Water supply / tailings handling", "Cannot run continuously", "Site water and settling plan before commissioning (C-10)", "Allan"],
        ["SMBC / PMRB / MGB-V consent for added equipment", "Installation challenged; plant compliance exposed", "SMBC written consent; confirm the addition sits inside the MFPS permits and ECC (C-15, C-16)", "Stephen / Jonathan"],
        ["Operating agreement not in hand", "Program rests on terms we have only by reference", "Obtain the executed Operational Partnership Agreement before spending (C-16)", "Stephen"],
    ], LM, y, [170, 200, 340, CW - 710], bold_col0=True, pad=3)

    # ---------------- 22 clarification register ----------------
    y = d.page("Clarification register", "Program · every open item, one owner each")
    reg = [
        ("C-1", "Corporate particulars of Golden Inocalla Management Services (form, registration, address, TIN, signatories)", "Allan"),
        ("C-2", "Allan Inocalla — formal title and program role", "Allan"),
        ("C-3", "Stephen Lloyd — formal title and credentials approved for print", "Stephen"),
        ("C-4", "Decision D-1: circuit A (table roughs, 2 tables) or circuit B (rougher upstream, 1 table)", "Allan / Stephen"),
        ("C-5", "Ore gravity test: lab, cost, date; adopt a recovery target", "Allan / Stephen"),
        ("C-6", "Reference deck: does the MFPS carry a shaking table? Measure it in-house; else arrange a visit elsewhere", "Stephen"),
        ("C-7", "Reference head motion measured (throw, toggle geometry, spring)", "Stephen"),
        ("C-8", "MFPS power supply: phase, voltage, spare capacity for two 1.5 kW drives; generator backup", "Stephen"),
        ("C-9", "Table location inside / beside the MFPS; existing slab thickness; concrete quote", "Stephen / contractor"),
        ("C-10", "MFPS water supply and tailings / settling capacity for the added tables", "Stephen"),
        ("C-11", "MFPS mill / crusher and classification capacity; batch mill for the secondary station", "Stephen"),
        ("C-12", "Step durations and target commissioning date", "Stephen"),
        ("C-13", "Vendor quotes replacing every BOM estimate (steel, rubber, shaft, motor/VFD, labour)", "Stephen"),
        ("C-14", "Design / drawing / QA cost — internal or billed", "Allan / Stephen"),
        ("C-15", "Added tables inside the MFPS permits and ECC (PMRB / MGB-V); Minahang Bayan status", "Jonathan / Stephen"),
        ("C-16", "Executed Operational Partnership Agreement (Board Res. 2026-009) copy; SMBC written consent to install and operate LAB X", "Stephen"),
        ("C-17", "MFPS equipment inventory (gravity circuit, mill, classifier, power, water, tailings)", "Stephen"),
        ("C-18", "Role of the tables (main-circuit cleaner vs toll secondary station) and title to them (GIMS / SMBC / investor group)", "Allan / Stephen"),
        ("C-19", "Marlon Malaluan's operating role", "Stephen"),
        ("C-20", "Allan-supplied manpower: headcount, skills (welder / fitter / mason / operators), cost basis (in-kind vs paid), availability date", "Allan"),
        ("C-21", "Accolade file: Stephen's and the project's credentials and recognitions — verified documents only, nothing asserted without one", "Stephen / Allan"),
        ("C-22", "Funding and involvement lines (planetGOLD / UN-GEF follow-on, DENR-MGB / PMRB / LGU, investors, TSX-V path, NGOs): exact programme name and phase, who leads each approach", "Allan / Stephen / Jonathan"),
    ]
    rows = [["#", "Item to clarify", "Owner", "Answer / date"]] + [[a, b, cc, "________________"] for a, b, cc in reg]
    d.table(rows, LM, y, [40, 470, 110, CW - 620], mono_cols=(0, 3), pad=1.6)

    # ---------------- 23 next steps ----------------
    y = d.page("Next steps", "Program")
    d.para("<b>Five things move the program off paper. None of them is steel.</b>", LM, y, CW, LEAD)
    y -= 44
    steps = [
        ("Inventory the MFPS and measure its own gravity equipment", "Stephen", "Power, water, mill, classifier, and — if there is one — the plant's shaking table. The cheapest engineering in the program, and it is in-house."),
        ("Sample the Minahang Bayan ore, book the gravity test, name the crew", "Allan / Stephen", "Sets every operating number and decides one table or two; Allan confirms the crew he supplies (C-20)."),
        ("Executed agreement copy and SMBC's written consent", "Stephen", "The program stands on Board Resolution 2026-009; hold the signed agreement and the consent to add equipment before any spend."),
        ("Freeze dimensions and collect three quotes", "Stephen", "Shop sketches for frame, skeleton, housing and the shaft; quotes replace every estimate on p.20–21."),
        ("Assemble the accolade file and the partner list", "Stephen / Allan / Jonathan", "Documents only; then the planetGOLD / agency / investor approaches with LAB X as the showcase (p.05)."),
    ]
    for i, (a, b, cc) in enumerate(steps):
        yy = y - i * 58
        c.setFillColor(GOLD); c.setFont("FutXB", 26); c.drawString(LM, yy - 22, str(i + 1))
        c.setFillColor(INK); c.setFont("FutB", 12.5); c.drawString(LM + 40, yy - 14, a)
        c.setFillColor(MUTE); c.setFont("FutM", 7.2); c.drawString(LM + 40, yy - 27, b.upper(), charSpace=1.2)
        d.para(cc, LM + 40, yy - 34, CW - 60, BODY_S)
    c.setFont("FutM", 7.4); c.setFillColor(GOLD)
    c.drawString(LM, 66, "THEN: ORDER THE SHAFT · CUT THE FRAME · CAST THE PAD AT THE MFPS · COMMISSION · DECIDE TABLE 2", charSpace=1.4)

    d.save()
    return OUT, d.n


if __name__ == "__main__":
    path, n = build()
    print(f"wrote {path} ({n} pages)")
