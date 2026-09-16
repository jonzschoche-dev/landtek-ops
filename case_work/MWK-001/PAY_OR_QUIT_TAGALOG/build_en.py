#!/usr/bin/env python3
"""Render the ENGLISH pay-or-quit (pay-to-stay) demand to PDF. Pilot: T-52537 / Sps. Gaulit.
Compensation-for-occupation, NOT a lease (runs on Patricia's 1/3, Art. 487). Draft for counsel;
nothing served. PH folio (8.5x13)."""
import os
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER

OUT = os.path.join(os.path.dirname(__file__), "PAY_OR_QUIT_ENGLISH_T52537.pdf")
FOLIO = (8.5 * inch, 13 * inch)

s = getSampleStyleSheet()
body = ParagraphStyle('b', parent=s['Normal'], fontName='Helvetica', fontSize=11, leading=15,
                      alignment=TA_JUSTIFY, spaceAfter=9)
ctr = ParagraphStyle('c', parent=body, fontName='Helvetica-Bold', fontSize=12, alignment=TA_CENTER, spaceAfter=4)
small = ParagraphStyle('sm', parent=body, fontSize=8, textColor='#666666', alignment=TA_CENTER, spaceAfter=12)
lead = ParagraphStyle('l', parent=body, fontName='Helvetica-Bold', spaceAfter=6)

P = [
    (small, "[DRAFT — for counsel review before service. Not served. Compensation-for-occupation, NOT a lease.]"),
    (ctr, "NOTICE TO PAY OR VACATE"),
    (ctr, "(Demand for Reasonable Compensation for Occupation, or to Vacate)"),
    (small, "[Counsel letterhead / Barandon or Adan Botor Law Office] &nbsp;&nbsp; Date: ____________"),
    (body, "<b>To:</b> Sps. DELFIN and LUISA GAULIT [or actual occupant]<br/>"
           "[premises / address], Barangay 3, Mercedes, Camarines Norte"),
    (body, "<b>Re:</b> Your occupation of Lot 2-X-4-E, covered by TCT No. T-52537, registered to the "
           "Heirs of Mary Worrick Keesey."),
    (body, "Dear Sps. Gaulit,"),
    (body, "We write on behalf of <b>Patricia Keesey Zschoche</b>, co-owner of the above property (Heirs of "
           "Mary Worrick Keesey), through <b>LandTek</b>, her duly authorized property manager and agent for "
           "the estate."),
    (body, "<b>1. Ownership.</b> The Heirs are the registered owners under <b>TCT No. T-52537</b> and the "
           "declared, tax-paying owners under <b>ARP GR-2014-HH-07-003-00169</b>. You occupy the property "
           "<b>without title or right</b>, heretofore by the mere tolerance of the owners, which is "
           "<b>hereby withdrawn</b>."),
    (body, "<b>2. You may remain only by paying for your use.</b> As a co-owner, our principal is entitled "
           "to reasonable compensation for your occupation. You are given the option to remain, "
           "<b>month to month</b>, upon payment of reasonable compensation of <b>PHP ______ per month</b>, "
           "beginning ____________, payable to the undersigned for the account of the co-ownership."),
    (body, "<b>3. This is NOT a lease.</b> This arrangement is a month-to-month permission "
           "<b>terminable at any time</b> on fifteen (15) days' notice, extended <b>without prejudice to and "
           "with express reservation of all the owners' rights</b>, <b>creating no lease and no tenancy</b>, "
           "and <b>not a recognition of any right in you</b>. It does not waive the owners' claim to "
           "compensation for your <b>prior</b> occupation, which remains reserved."),
    (body, "<b>4. If you do not pay or vacate.</b> Should you neither pay the monthly compensation nor "
           "peacefully vacate within fifteen (15) days, the owners will sue to recover possession and for "
           "the accrued reasonable compensation and damages. Any structure you built was made <b>without "
           "the owners' consent and without a building permit</b> - under <b>Articles 449-451 of the Civil "
           "Code</b> you are a <b>builder in bad faith</b>, with <b>no right to reimbursement and no right of "
           "retention</b>; on your default the owners may keep the improvement without paying you, or have it "
           "demolished <b>at your expense</b>."),
    (body, "<b>5. Choose within fifteen (15) days:</b> (a) pay PHP ______ per month and remain "
           "month-to-month; or (b) vacate peacefully. Silence or refusal will be treated as election to be sued."),
    (body, "Very truly yours,"),
    (Spacer, None),
    (lead, "____________________________<br/><b>LANDTEK [entity/OPC]</b> - by [Authorized Representative]<br/>"
           "Authorized Property Manager and Agent for Patricia Keesey Zschoche, co-owner<br/>"
           "<font size=9>(Any court action will be filed by counsel of record.)</font>"),
]

doc = SimpleDocTemplate(OUT, pagesize=FOLIO, topMargin=1*inch, bottomMargin=1*inch,
                        leftMargin=1*inch, rightMargin=1*inch,
                        title="Notice to Pay or Vacate - T-52537")
story = []
for style, text in P:
    story.append(Spacer(1, 0.25*inch) if style is Spacer else Paragraph(text, style))
doc.build(story)
print("wrote", OUT)
