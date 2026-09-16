#!/usr/bin/env python3
"""Render the LandTek Control & Unwind Playbook to PDF. Internal; nothing filed."""
import os
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.lib import colors

OUT = os.path.join(os.path.dirname(__file__), "LANDTEK_CONTROL_AND_UNWIND_PLAYBOOK.pdf")
FOLIO = (8.5 * inch, 13 * inch)
s = getSampleStyleSheet()
body = ParagraphStyle('b', parent=s['Normal'], fontName='Helvetica', fontSize=10.5, leading=14, alignment=TA_JUSTIFY, spaceAfter=5)
h1 = ParagraphStyle('h1', parent=body, fontName='Helvetica-Bold', fontSize=15, alignment=TA_CENTER, spaceAfter=4)
sub = ParagraphStyle('sub', parent=body, fontSize=9, alignment=TA_CENTER, textColor='#666', spaceAfter=10)
sec = ParagraphStyle('sec', parent=body, fontName='Helvetica-Bold', fontSize=12, spaceBefore=11, spaceAfter=4, textColor='#0a5')
li = ParagraphStyle('li', parent=body, leftIndent=16, firstLineIndent=-10, fontSize=10, leading=13, spaceAfter=3)
box = ParagraphStyle('box', parent=body, fontSize=9.5, leading=13, leftIndent=8, textColor='#333')
cell = ParagraphStyle('cell', parent=body, fontSize=9, leading=12, spaceAfter=0)
cellb = ParagraphStyle('cellb', parent=cell, fontName='Helvetica-Bold')
callout = ParagraphStyle('co', parent=body, fontName='Helvetica-Bold', fontSize=11.5, leading=15, spaceAfter=4, textColor='#b00')

def P(t, st=body): return Paragraph(t, st)

def mktable(rows, widths):
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#0a5')),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('FONTSIZE',(0,0),(-1,0),9),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#cccccc')),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f2faf5')]),
        ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),
        ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
    ]))
    return t

story = [
    P("LANDTEK - CONTROL & UNWIND PLAYBOOK", h1),
    P("How you keep control of a Filipino-owned operating company you do not own on paper - and how to "
      "rearrange, replace, or exit if it goes sour. Path C (you own + license the IP; a Filipino principal "
      "owns the lean opco). Internal; nothing filed.", sub),

    P("1. Where your control actually lives", sec),
    P("Not in the opco's shares - those must be genuinely the Filipino principal's (Anti-Dummy). Your control "
      "sits OUTSIDE the equity, in three levers you legitimately hold:", body),
    mktable([
        [P("Lever", cellb), P("What it is", cellb), P("Why it controls", cellb)],
        [P("IP License", cellb),
         P("You / your holdco own the platform, engines, playbooks, name; the opco only <b>licenses</b> it, revocably.", cell),
         P("Revoke it and the opco is an empty shell that can deliver nothing. Held openly, owner-to-vendor - not a hidden leash on their shares.", cell)],
        [P("Estate mandate", cellb),
         P("Patricia engaged the opco to run MWK; terminable on 30 days' notice.", cell),
         P("The opco's only revenue exists because Patricia lets it. Pull it and re-engage a new vehicle.", cell)],
        [P("Trust + first charge", cellb),
         P("Collections are the co-ownership's, held in trust; your + Patricia's advances are a first charge, with a duty to account.", cell),
         P("A rogue principal cannot lawfully pocket estate funds - the money isn't the opco's.", cell)],
    ], [1.1*inch, 2.7*inch, 2.9*inch]),

    P("2. The golden rule", sec),
    P("NEVER seize or claw back their shares. A right to grab their equity on demand PROVES they never really "
      "owned it - that is the Anti-Dummy violation that voids the whole structure. Control by starving the "
      "shell, not by leashing the equity.", callout),

    P("3. If it goes sour - scenario and your counter", sec),
    mktable([
        [P("Situation", cellb), P("Your counter", cellb)],
        [P("Principal refuses to act, or acts against you", cell),
         P("Patricia terminates the estate agreement + you revoke the IP license -> opco goes inert; stand up a new opco and re-point.", cell)],
        [P("Principal tries to claim the business / the IP", cell),
         P("They can't: the IP was never theirs (licensed, revocable) and the estate mandate is Patricia's. They're left with an empty shell + any liabilities.", cell)],
        [P("Principal tries to keep collected estate funds", cell),
         P("Trust + first-charge + accounting duty make it recoverable; it's the co-ownership's money, not the opco's.", cell)],
        [P("Principal just goes quiet / unreachable", cell),
         P("Same play - starve (pull IP + mandate) and re-point to a new vehicle; the dead shell can't operate without the license.", cell)],
    ], [2.5*inch, 4.2*inch]),

    P("4. Ways to rearrange - lightest to heaviest", sec),
    mktable([
        [P("Goal", cellb), P("The move", cellb)],
        [P("Swap the person, keep the company", cell),
         P("The single stockholder transfers 100% of the OPC shares to a NEW Filipino principal - one clean share transfer (trivial with one owner).", cell)],
        [P("Add owners / bring in partners", cell),
         P("Convert the OPC into an ordinary stock corporation (the law allows the conversion).", cell)],
        [P("Total reset", cell),
         P("Dissolve the shell; a fresh opco takes the IP license + Patricia's re-engagement. Cheap, because value never lived in the shell.", cell)],
        [P("You / Patricia become citizens", cell),
         P("Acquire opco equity then via a legitimate purchase or new issuance AT FAIR VALUE - as qualified investors, not by exercising a pre-baked option.", cell)],
    ], [2.5*inch, 4.2*inch]),

    P("5. Pre-install now so unwind stays clean", sec),
    P("- <b>Keep the opco a lean shell:</b> no owned IP, no owned assets, minimal capital - nothing to fight over.", li),
    P("- <b>IP license terms:</b> revocable at will / on breach, short cure period, non-transferable, survives a change of the opco.", li),
    P("- <b>Estate agreement:</b> terminable on short notice (30 days), full accounting on termination.", li),
    P("- <b>Buy-out-on-cause (optional):</b> if you want a forced-exit mechanic for the principal, it must run to a "
      "<b>REPLACEMENT Filipino you designate</b>, at fair value - NEVER back to you. \"Transfer to me on demand\" is the nominee red flag.", li),
    P("- <b>Separate the crown jewel:</b> the platform/IP stays with you/holdco throughout - it is licensed in, never contributed to the opco.", li),

    P("6. The citizenship endgame", sec),
    P("Because the value is always in your IP, you lose nothing by waiting. On naturalization (yours or "
      "Patricia's), you acquire opco equity through a normal arms-length transaction at fair value - the same "
      "way any eligible investor would - and consolidate ownership cleanly. No hold-for-me option is ever "
      "papered, so nothing about the structure reads as a foreigner's dummy arrangement.", body),

    P("Guardrails", sec),
    P("- <b>Anti-Dummy:</b> the Filipino owner genuinely owns + controls the opco; you're the licensor/owner of the IP, never the hidden owner.<br/>"
      "- <b>No practice of law:</b> the opco manages / demands / collects; a lawyer files actual court suits.<br/>"
      "- <b>Real party in interest:</b> Patricia is the named plaintiff in any recovery suit.", box),

    Spacer(1, 0.12*inch),
    P("<font size=8 color='#888'>Internal control & unwind playbook - not legal/corporate advice. You execute "
      "the structure yourself; a lawyer is optional and only files actual court suits. Generated 2026-09-16.</font>", body),
]
doc = SimpleDocTemplate(OUT, pagesize=FOLIO, topMargin=0.8*inch, bottomMargin=0.7*inch,
                        leftMargin=0.85*inch, rightMargin=0.85*inch, title="LandTek Control & Unwind Playbook")
doc.build(story)
print("wrote", OUT)
