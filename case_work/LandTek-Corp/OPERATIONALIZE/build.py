#!/usr/bin/env python3
"""Render the LandTek A-Z operational playbook to PDF. Internal; nothing filed/incorporated."""
import os
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT

OUT = os.path.join(os.path.dirname(__file__), "LANDTEK_OPERATIONALIZE_A_Z.pdf")
FOLIO = (8.5 * inch, 13 * inch)
s = getSampleStyleSheet()
body = ParagraphStyle('b', parent=s['Normal'], fontName='Helvetica', fontSize=10.5, leading=14, alignment=TA_JUSTIFY, spaceAfter=6)
step = ParagraphStyle('st', parent=body, leftIndent=16, firstLineIndent=-16, spaceAfter=5)
h1 = ParagraphStyle('h1', parent=body, fontName='Helvetica-Bold', fontSize=15, alignment=TA_CENTER, spaceAfter=4, textColor='#1a1a1a')
h2 = ParagraphStyle('h2', parent=body, fontName='Helvetica-Bold', fontSize=12, spaceBefore=10, spaceAfter=5, textColor='#0b5')
sub = ParagraphStyle('sub', parent=body, fontSize=9, alignment=TA_CENTER, textColor='#666', spaceAfter=10)
box = ParagraphStyle('box', parent=body, fontSize=9.5, leading=13, leftIndent=8, textColor='#333')
callout = ParagraphStyle('co', parent=body, fontName='Helvetica-Bold', fontSize=11, leading=15, spaceAfter=4)

def P(t, st=body): return Paragraph(t, st)

story = [
    P("LANDTEK - A-Z OPERATIONAL PLAYBOOK", h1),
    P("From today to a functioning company earning on the MWK estate (proof client). "
      "Owner tags: [YOU]=Jonathan's decision - [COUNSEL]=PH lawyer - [OPCO]=the company - "
      "[FIELD]=on the ground - [DONE]=already built/drafted.", sub),

    P("START HERE - the three moves that unblock everything", h2),
    P("<b>1.</b> Name the genuine Filipino principal(s) and the authorized signatory for the operating company. <i>[YOU]</i>", callout),
    P("<b>2.</b> Engage a PH corporate/IP lawyer and hand them the Formation Package. <i>[YOU]</i>", callout),
    P("<b>3.</b> Put the CV6839 substitute-administrator question to Atty. Botor (the biggest money). <i>[YOU -> BOTOR]</i>", callout),

    P("PHASE 1 - STAND UP THE COMPANY (the vehicle)", h2),
    P("<b>A.</b> Decide the principals + the registered company name. <i>[YOU]</i>", step),
    P("<b>B.</b> Engage PH corporate/IP counsel; get the foreign-ownership + Anti-Dummy ruling and the "
      "citizenship-bridge language (Formation Package has it). <i>[YOU + COUNSEL]</i>", step),
    P("<b>C.</b> SEC: name reservation -> Articles / OPC -> certificate of registration. <i>[COUNSEL]</i>", step),
    P("<b>D.</b> BIR (TIN, books, official receipts) + LGU business permit + barangay clearance. <i>[OPCO]</i>", step),
    P("<b>E.</b> Open the corporate bank account (for collections held in trust). <i>[OPCO]</i>", step),
    P("<b>F.</b> Execute the IP Ownership & License, Jonathan/holdco -> opco (term sheet DONE; sets your royalty). <i>[YOU + COUNSEL]</i>", step),

    P("PHASE 2 - WIRE THE AUTHORITY OVER THE ESTATE", h2),
    P("<b>G.</b> Execute the Estate Management & Agency Agreement, Patricia -> opco; <b>APOSTILLE</b> it "
      "(Patricia is in the US). Draft DONE, marked confidential. <i>[PATRICIA + OPCO]</i>", step),
    P("<b>H.</b> Confirm Patricia's broad apostilled SPA reaches the needed acts; add a supplemental "
      "apostilled SPA if there's a gap. <i>[PATRICIA + COUNSEL]</i>", step),
    P("<b>I.</b> Designate the opco's authorized signatory for all demands - not you, not Patricia. <i>[OPCO]</i>", step),

    P("PHASE 3 - TURN ON THE MONEY (MWK proof client)", h2),
    P("<b>J.</b> CV6839 (biggest, ~tens of millions): Botor files the no-signature substitute-administrator / "
      "execution vehicle in parallel with the guardianship. Query DONE. <i>[BOTOR]</i>", step),
    P("<b>K.</b> Guardianship: keep the weight behind the grant - it unlocks full CV6839 + estate sale/lease. <i>[BOTOR]</i>", step),
    P("<b>L.</b> Census the 7-ha T-32917 occupants (barangay canvass + assessor/RD). Worklist DONE. <i>[FIELD]</i>", step),
    P("<b>M.</b> Serve the pay-to-stay / pay-or-quit demands on informal occupants (English + Tagalog DONE); "
      "titled adverse holders go on the nullity track, not pay-to-stay. <i>[OPCO + COUNSEL]</i>", step),
    P("<b>N.</b> Collect compensation -> run every peso through the reimbursement ledger -> allocate the "
      "co-owners' shares against their Art. 488 debts. <i>[OPCO]</i>", step),
    P("<b>O.</b> Sue the refusers (Art. 487 recovery + back-rent) - the stick that keeps the rest paying. <i>[COUNSEL]</i>", step),

    P("PHASE 4 - RUN IT AS A BUSINESS", h2),
    P("<b>P.</b> Keep the expense/reimbursement engine live (PHP 2,005,405.92 logged; RPT paid under protest; "
      "daily harvester running). <i>[DONE / ongoing]</i>", step),
    P("<b>Q.</b> Set the retainer/fee model (opco service fee + your IP royalty). <i>[YOU]</i>", step),
    P("<b>R.</b> Accounting: Rule 96 for the guardianship; trust accounting for all collections. <i>[OPCO + COUNSEL]</i>", step),
    P("<b>S.</b> Prove the arc on MWK, then onboard the next client (Paracale). <i>[YOU]</i>", step),

    P("GUARDRAILS - do not cross", h2),
    P("- <b>No practice of law:</b> the opco manages, demands, collects; <b>counsel files every suit.</b><br/>"
      "- <b>Anti-Dummy:</b> the Filipino owners must genuinely own and control the opco; you are the "
      "licensor/owner of the IP, never the hidden owner of the company.<br/>"
      "- <b>Real party in interest:</b> Patricia is the named plaintiff in any recovery suit.<br/>"
      "- <b>No external exposure until ready</b>; provenance/no-hallucination; client separation (MWK vs Paracale).", box),

    P("ALREADY DONE (the desk is ahead of the field)", h2),
    P("Formation package - IP license & Articles term sheets - estate management agreement (confidential) - "
      "pay-to-stay demands (EN + Tagalog) - T-32917 census worklist - CV6839 Botor query - reimbursement "
      "engine (live, self-updating) - boundary intelligence (estate 97% closed) - recovery execution register - "
      "Plan-B authority fallback. The gating items now are the two real-world moves at the top: name the "
      "principals, engage counsel.", box),

    Spacer(1, 0.15*inch),
    P("<font size=8 color='#888'>Internal operational playbook - not legal/corporate advice. A PH corporate/IP "
      "lawyer + SEC/BIR formalize the company; counsel of record files all suits. Nothing filed, served, or "
      "incorporated by this document. Generated 2026-09-16.</font>", body),
]

doc = SimpleDocTemplate(OUT, pagesize=FOLIO, topMargin=0.8*inch, bottomMargin=0.7*inch,
                        leftMargin=0.9*inch, rightMargin=0.9*inch, title="LandTek A-Z Operational Playbook")
doc.build(story)
print("wrote", OUT)
