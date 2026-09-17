#!/usr/bin/env python3
"""Render STRATEGY_MANDATE_ALLAN_2026-08-24.md as a clean professional PDF."""
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, KeepTogether)

OUT = "/Users/jonathanzschoche/landtek/case_work/Paracale-001/STRATEGY_MANDATE_ALLAN_2026-08-24.pdf"

NAVY = colors.HexColor("#1a2e4a")
ACCENT = colors.HexColor("#8a6d1f")
GRAY = colors.HexColor("#555555")
LIGHT = colors.HexColor("#f2f0ea")

styles = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=17,
                            leading=21, textColor=NAVY, alignment=TA_LEFT),
    "subtitle": ParagraphStyle("subtitle", fontName="Helvetica-Bold", fontSize=11.5,
                               leading=15, textColor=ACCENT),
    "meta": ParagraphStyle("meta", fontName="Helvetica-Oblique", fontSize=8,
                           leading=10.5, textColor=GRAY),
    "objective": ParagraphStyle("objective", fontName="Helvetica-Bold", fontSize=10.5,
                                leading=14, textColor=NAVY),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12, leading=15,
                         textColor=NAVY, spaceBefore=14, spaceAfter=4),
    "h2sub": ParagraphStyle("h2sub", fontName="Helvetica-Oblique", fontSize=9,
                            leading=12, textColor=GRAY, spaceAfter=6),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.8, leading=13.6,
                           spaceAfter=5),
    "num": ParagraphStyle("num", fontName="Helvetica", fontSize=9.8, leading=13.6,
                          leftIndent=22, firstLineIndent=-22, spaceAfter=5),
    "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=9.6, leading=13.2,
                          leftIndent=36, firstLineIndent=-10, spaceAfter=3),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=9.3, leading=12,
                           alignment=TA_CENTER),
    "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=9.3,
                            leading=12, alignment=TA_CENTER),
}

def num(n, text):
    return Paragraph(f"<b>{n}.</b>&nbsp;&nbsp;{text}", styles["num"])

story = []
story.append(Paragraph("STRATEGY MANDATE — ALLAN V. INOCALLA", styles["title"]))
story.append(Spacer(1, 3))
story.append(Paragraph("Manila Building (TCT 44055) &amp; Estate of Vicente Inocalla Sr.",
                       styles["subtitle"]))
story.append(Spacer(1, 6))
story.append(HRFlowable(width="100%", thickness=1.4, color=NAVY))
story.append(Spacer(1, 5))
story.append(Paragraph(
    "Prepared by LandTek Assisted, 24 August 2026. Operator-grade directive for Allan and his legal "
    "counsel. Not legal advice; legal steps to be confirmed by engaged counsel. Fact basis: 1992 judicial "
    "partition (doc 671), CC 13-131220 / CA SP 161072 / SC G.R. 256997 judgments, alias writ 25 Nov 2025.",
    styles["meta"]))
story.append(Spacer(1, 10))
story.append(Paragraph(
    "OBJECTIVE: Full control of the building, rents flowing to the family, Ace ejected and made to pay. "
    "Three tracks, run in parallel, never mixed.", styles["objective"]))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "<b>WHY THIS MATTERS:</b> The family cannot outsource its security to public systems that are "
    "themselves in decline — the environment, the drinking water, the hospitals, the schools, the grip of "
    "poverty all tell the same story across the country. Whatever the family will have, the family must "
    "build and hold itself. A recovered, well-run estate is that foundation: housing, steady rental income, "
    "funds for health and education, and land restored instead of stripped. That is what this fight is for "
    "— not just beating Ace, but ending the years in which the family's own inheritance was another "
    "degraded asset. <i>(This context is for the family and counsel's understanding of the mandate; it "
    "does not go into court filings, which stay strictly on the legal elements.)</i>", styles["body"]))

# Track 1
story.append(Paragraph("TRACK 1 — POSSESSION", styles["h2"]))
story.append(Paragraph("File within weeks, not months. Direct counsel to:", styles["h2sub"]))
story.append(num(1, "<b>Obtain RD Manila certified copy of reinstated TCT 44055</b> plus the entry of "
                   "judgment on Ace's motion for reconsideration. This is the anchor exhibit for everything "
                   "that follows."))
story.append(num(2, "<b>File unlawful detainer, MeTC Manila</b>, vs. Ace (Vicente de Leon Inocalla III), "
                   "Elena de Leon Inocalla, and all occupants, the moment the 15-day demand period lapses. "
                   "Deadline discipline: must be filed <b>within 1 year of the last written demand</b>."))
story.append(num(3, "<b>Name Jesus as lead plaintiff</b> (non-Manila resident — exempt from barangay "
                   "conciliation under RA 7160 §408; bypasses the obstructed barangay). Allan joins as "
                   "attorney-in-fact. Do NOT make Allan lead plaintiff — his address of record is the "
                   "building itself."))
story.append(num(4, "<b>Pre-empt Ace's one defense:</b> the 1992 court-approved partition gave his late "
                   "father <b>one ground-floor door only</b> (ground floor, left, facing east). Plead that "
                   "the award passed to Vicente Jr.'s five heirs collectively, Ace's filiation is contested, "
                   "and it confers no right to the other nine units or to collect any rent."))
story.append(num(5, "<b>Claim in the ejectment:</b> possession + <b>fair rental value</b> + attorney's "
                   "fees. Nothing more — the bigger money goes in Track 2."))

# Track 2
story.append(Paragraph("TRACK 2 — MONEY", styles["h2"]))
story.append(Paragraph("Build now; file after the administrator is appointed.", styles["h2sub"]))
story.append(num(6, "<b>Evidence capture starts today, no exceptions:</b>"))
for s in [
    "Same-day police blotter for every incident.",
    "Timestamped photos and video.",
    "Damaged-equipment inventory: item, owner, purchase receipt, written repair/replacement quote. "
    "Courts award actual damages on receipts and competent proof, not estimates.",
    "Sworn worker affidavits while memories are fresh.",
    "Tenant list per door: what each paid Ace, and when.",
]:
    story.append(Paragraph(f"–&nbsp;&nbsp;{s}", styles["sub"]))
story.append(Spacer(1, 2))
story.append(num(7, "<b>File criminal complaints</b> with the prosecutor: malicious mischief (equipment "
                   "destruction), grave threats / grave coercion (intimidation). These anchor the civil "
                   "damages."))
story.append(num(8, "<b>RTC damages suit later:</b> rents Ace actually collected (Art. 549, bad-faith "
                   "possessor), equipment losses, moral + exemplary damages. <b>Never claim the same rents "
                   "in both cases</b> — claim-splitting kills both. Recovery backstop: set off everything "
                   "Ace owes against his branch's share in settlement."))

# Track 3
story.append(Paragraph("TRACK 3 — ESTATE", styles["h2"]))
story.append(Paragraph("The blocker — engage counsel this month.", styles["h2sub"]))
story.append(num(9, "<b>Engage estate counsel on a narrow scope:</b> intestate settlement petition + Allan "
                   "as <b>Special Administrator (Rule 80)</b>. Petition discloses the 1998 case (98-88750) "
                   "up front, paired with Allan's record of recovering the building for the family, heir "
                   "consents, and a surety bond."))
story.append(num(10, "<b>No new EJS is needed for the building</b> — the 1992 judicial partition (CC "
                    "B-5625, RTC Br. 41 Daet; finality certified 2014) already allocated the land equally "
                    "and the 10 doors by name. Counsel's jobs: estate-tax amnesty check (RA 11213 as "
                    "amended), register the partition, sweep in the un-partitioned ~74.6 ha still titled "
                    "to Vicente Sr."))
story.append(num(11, "<b>Income now:</b> willing tenants sign new written leases and pay into <b>one "
                    "dedicated account with clean books</b>. Tenants who keep paying Ace get no credit for "
                    "it. Those books are also Allan's fitness evidence for the appointment."))

# Rules
rules = [
    Paragraph("RULES", styles["h2"]),
    Paragraph("–&nbsp;&nbsp;<b>No self-help retaking of units.</b> No confrontation with Ace's group — "
              "everything through blotter, counsel, courts.", styles["sub"]),
    Paragraph("–&nbsp;&nbsp;<b>Allan signs nothing</b> selling or encumbering estate property before "
              "appointment.", styles["sub"]),
    Paragraph("–&nbsp;&nbsp;Keep Inocalla matters strictly separate from all other client matters.",
              styles["sub"]),
]
story.append(KeepTogether(rules))

# Allocation table
def cell(t, bold=False):
    return Paragraph(t, styles["cellb" if bold else "cell"])

hdr_style = ParagraphStyle("hdr", fontName="Helvetica-Bold", fontSize=9.3, leading=12,
                           alignment=TA_CENTER, textColor=colors.white)
table_data = [
    [Paragraph(h, hdr_style) for h in ["Floor", "Left", "Center", "Right"]],
    [cell("4th"), cell("Allan (whole floor)"), cell("—"), cell("—")],
    [cell("3rd"), cell("Heirs of Melvyn"), cell("Herbert"), cell("Marilou")],
    [cell("2nd"), cell("Francisco"), cell("Cipriana"), cell("Senen")],
    [cell("Ground"), cell("Vicente Jr. (= Ace's branch)", True), cell("Casper"), cell("Jesus")],
]
tbl = Table(table_data, colWidths=[0.9 * inch, 2.1 * inch, 1.7 * inch, 1.7 * inch])
tbl.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
]))
alloc = [
    Paragraph("THE 10-DOOR ALLOCATION", styles["h2"]),
    Paragraph("Per the 1992 judicial partition (doc 671) — left to right facing east. "
              "Land under TCT 44055: all ten siblings equally.", styles["h2sub"]),
    tbl,
]
story.append(KeepTogether(alloc))
story.append(Spacer(1, 12))
story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#bbbbbb")))
story.append(Spacer(1, 4))
story.append(Paragraph(
    "Companions: ALLAN_ADMIN_DIRECTIVE.md · MANILA_EJECTMENT_BRIEF_OF_FACTS.md · "
    "ACE_DAMAGES_FRAMEWORK.md · DEMAND_TO_VACATE_VITO_CRUZ_ALL_OCCUPANTS.md", styles["meta"]))


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GRAY)
    canvas.drawString(0.85 * inch, 0.55 * inch,
                      "LandTek Assisted · Strategy Mandate · 2026-08-24 · Paracale-001")
    canvas.drawRightString(letter[0] - 0.85 * inch, 0.55 * inch, f"Page {doc.page}")
    canvas.restoreState()


doc = SimpleDocTemplate(OUT, pagesize=letter,
                        leftMargin=0.85 * inch, rightMargin=0.85 * inch,
                        topMargin=0.8 * inch, bottomMargin=0.85 * inch,
                        title="Strategy Mandate — Allan V. Inocalla",
                        author="LandTek Assisted")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print("wrote", OUT)
