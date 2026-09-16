#!/usr/bin/env python3
"""Render the LandTek company-formation step-by-step (Philippines) to PDF. Internal; nothing filed."""
import os
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER

OUT = os.path.join(os.path.dirname(__file__), "LANDTEK_COMPANY_FORMATION_STEPS.pdf")
FOLIO = (8.5 * inch, 13 * inch)
s = getSampleStyleSheet()
body = ParagraphStyle('b', parent=s['Normal'], fontName='Helvetica', fontSize=10.5, leading=14, alignment=TA_JUSTIFY, spaceAfter=5)
h1 = ParagraphStyle('h1', parent=body, fontName='Helvetica-Bold', fontSize=15, alignment=TA_CENTER, spaceAfter=4)
sub = ParagraphStyle('sub', parent=body, fontSize=9, alignment=TA_CENTER, textColor='#666', spaceAfter=10)
stp = ParagraphStyle('stp', parent=body, fontName='Helvetica-Bold', fontSize=11.5, spaceBefore=9, spaceAfter=3, textColor='#0a5')
li = ParagraphStyle('li', parent=body, leftIndent=16, firstLineIndent=-10, fontSize=10, leading=13, spaceAfter=3)
box = ParagraphStyle('box', parent=body, fontSize=9.5, leading=13, leftIndent=8, textColor='#333')

def P(t, st=body): return Paragraph(t, st)

story = [
    P("LANDTEK - HOW TO FORM THE COMPANY, STEP BY STEP", h1),
    P("Philippines - Path C (Filipino-owned operating company; Jonathan owns + licenses the IP). "
      "You (and the Filipino principal) do every step yourself: the OPC registers online via SEC OneSEC, "
      "and BIR / LGU / bank are direct filings. A lawyer is optional, on your call - not a gate to finishing "
      "anything here. SEC/BIR/LGU fees and forms change - verify on the portals.", sub),

    P("STEP 0 - Lock your five decisions (you decide - do this first)", stp),
    P("- <b>(1)</b> the genuine Filipino principal (the single OPC owner) + the authorized signatory, "
      "<b>(2)</b> entity form (Step 1), <b>(3)</b> company name, <b>(4)</b> capital, <b>(5)</b> the purpose clause.", li),
    P("- Structure it right so it holds up under <b>Anti-Dummy</b>: the value stays in your IP (you license it "
      "in), the Filipino principal genuinely owns and runs the lean opco shell, and any future path to your "
      "ownership is a real transaction on naturalization - never a hold-for-me option. (If you ever want extra "
      "certainty, a foreign-ownership ruling is available - that's your option, not a prerequisite.)", li),

    P("STEP 1 - Choose the entity", stp),
    P("- <b>OPC (One Person Corporation)</b> - ONE Filipino natural-person stockholder; simplest; limited "
      "liability. Requires a <b>nominee + alternate nominee</b> (take over on death/incapacity), a "
      "<b>Corporate Secretary</b> (a different Filipino resident), and a <b>Treasurer</b> (if the stockholder "
      "is treasurer, post a surety bond). Name ends in \"OPC\".", li),
    P("- <b>Small stock corporation</b> - 2-15 Filipino incorporators; needs Articles + By-laws. Use if there "
      "are several principals.", li),
    P("- <b>Recommendation:</b> OPC if one trusted Filipino principal owns it; small corp if a few do.", li),

    P("STEP 2 - Reserve the company name", stp),
    P("- Via SEC's online portal (eSPARC / OneSEC). Verify the name is distinguishable and reserve it. It must "
      "end with the correct suffix (OPC / Corp. / Inc.).", li),

    P("STEP 3 - Prepare the incorporation documents", stp),
    P("- <b>Articles of Incorporation</b> - primary purpose = <b>property/land services + legal-operations "
      "support (records intelligence, property recovery, management, development coordination) - NOT the "
      "practice of law</b>; principal office [Daet / Camarines Norte]; capital + shares.", li),
    P("- <b>OPC extras:</b> nominee + alternate-nominee designation with their written consent; Treasurer's "
      "affidavit; surety bond if the stockholder is also treasurer.", li),
    P("- <b>Corporate Secretary</b> appointment (Filipino resident; for an OPC, a different person from the "
      "stockholder). Corporation: add By-laws.", li),

    P("STEP 4 - File with the SEC and pay fees", stp),
    P("- Submit the application + documents via eSPARC/OneSEC; pay the filing/registration fee, name-reservation "
      "fee, and documentary stamp tax on the shares.", li),
    P("- SEC issues the <b>Certificate of Incorporation</b> - the company now legally exists.", li),

    P("STEP 5 - Register with the BIR", stp),
    P("- Register the company (BIR Form 1903), obtain its <b>TIN</b>; pay the registration fee (Form 0605) and "
      "DST on the original issuance of shares.", li),
    P("- Register the <b>books of accounts</b>; apply for <b>Authority to Print</b> + official "
      "receipts/invoices; obtain the <b>Certificate of Registration (BIR 2303)</b>.", li),

    P("STEP 6 - LGU business permits", stp),
    P("- <b>Barangay business clearance</b> (where the office is), then the <b>Mayor's / Business Permit</b> "
      "from the city/municipality [Daet / Mercedes].", li),

    P("STEP 7 - Employer registrations (only if hiring)", stp),
    P("- Register as employer with <b>SSS, PhilHealth, and Pag-IBIG</b>.", li),

    P("STEP 8 - Open the corporate bank account", stp),
    P("- With the SEC Certificate, BIR 2303, a board/stockholder resolution authorizing the account + "
      "signatory, and IDs. This is the account that holds estate collections <b>in trust</b>.", li),

    P("STEP 9 - Finalize + sign the LandTek instruments (yours to complete)", stp),
    P("- <b>IP Ownership & License</b> (Jonathan/holdco -> opco) - fill the blanks (royalty, term), sign. This "
      "is your kill-switch: revocable, so the opco only operates while you license it. (Drafted.)", li),
    P("- <b>Estate Management & Agency Agreement</b> (Patricia -> opco) - fill the blanks, Patricia signs and "
      "<b>APOSTILLES</b> it (she's in the US). Confidential; not filed. Terminable on 30 days. (Drafted.)", li),
    P("- Record the opco's <b>authorized signatory</b> for all demands (not Jonathan/Patricia).", li),

    P("STEP 10 - Go live", stp),
    P("- The opco signs the pay-to-stay/pay-or-quit demands and collects -> every peso through the reimbursement "
      "ledger. The only piece that needs a lawyer is actually filing a lawsuit in court (that's the UPL line - "
      "a lawyer files suits); everything up to that you run yourself.", li),

    P("Rough timeline & cost (verify - both vary)", stp),
    P("- SEC (OneSEC) can be days for a simple OPC; BIR + LGU typically add 1-3 weeks; whole thing often "
      "~3-6 weeks. Costs: SEC fees (modest) + DST + LGU fees + the lawyer/incorporation-service fee + notarial/"
      "apostille. Get a fixed quote from the corporate lawyer.", box),

    P("Guardrails (carry through every step)", stp),
    P("- <b>Anti-Dummy:</b> the Filipino owner must genuinely own and control the opco - you are the IP "
      "owner/licensor, never the hidden owner. Your control is the IP license + Patricia's mandate, not a "
      "leash on their shares.<br/>"
      "- <b>No practice of law:</b> the opco manages/demands/collects; a lawyer files actual court suits.<br/>"
      "- <b>Citizenship bridge:</b> value stays in your IP; equity comes to you on naturalization via a "
      "legitimate future transaction - never a pre-baked hold-for-me option.", box),

    P("If it goes sour / you want to rearrange", stp),
    P("- <b>Don't seize their shares</b> (that would prove they never really owned it - the Anti-Dummy trap). "
      "Instead <b>starve the shell and re-point:</b> revoke the IP license -> Patricia terminates the estate "
      "agreement -> stand up a fresh opco with a new Filipino principal -> re-license the IP + Patricia "
      "re-engages it. The dead shell is worthless because value never lived there.", li),
    P("- <b>Swap the person:</b> the single stockholder transfers 100% of the OPC shares to a new Filipino "
      "principal (one clean transfer). <b>Add partners:</b> convert the OPC to an ordinary stock corporation. "
      "<b>Total reset:</b> dissolve + re-form. <b>On naturalization:</b> you/Patricia buy in at fair value.", li),
    P("- Keep the opco a <b>lean shell</b> - no owned IP, no owned assets, minimal capital - so there's never "
      "anything to fight over; make the IP license and estate agreement short-cure / terminable in writing.", li),

    Spacer(1, 0.12*inch),
    P("<font size=8 color='#888'>Internal step-by-step - not legal/corporate advice. You form the OPC and do "
      "BIR/LGU/bank yourself; a lawyer is optional and only files actual court suits. Verify current portals, "
      "forms, and fees. Nothing filed or incorporated by this document. Generated 2026-09-16.</font>", body),
]
doc = SimpleDocTemplate(OUT, pagesize=FOLIO, topMargin=0.8*inch, bottomMargin=0.7*inch,
                        leftMargin=0.9*inch, rightMargin=0.9*inch, title="LandTek Company Formation - Step by Step")
doc.build(story)
print("wrote", OUT)
