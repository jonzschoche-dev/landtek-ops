#!/usr/bin/env python3
"""Bundle the three LandTek formation PDFs into one packet with a cover page.
Re-renders the three source PDFs first, then concatenates: cover -> steps -> control/unwind -> A-Z.
Internal; nothing filed."""
import os, subprocess, io
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from pypdf import PdfReader, PdfWriter

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "LANDTEK_FORMATION_PACKET.pdf")
FOLIO = (8.5 * inch, 13 * inch)

# 1. Re-render the three sources so the packet is always current.
for script in ("build_steps.py", "build_control_unwind.py", "build.py"):
    subprocess.run(["python3", os.path.join(HERE, script)], check=True)

PARTS = [
    ("LANDTEK_COMPANY_FORMATION_STEPS.pdf", "Part 1 - How to Form the Company, Step by Step",
     "Steps 0-10: your five decisions, the OPC via SEC OneSEC, BIR / LGU / bank, signing the instruments, going live. Plus headcount, timeline, cost."),
    ("LANDTEK_CONTROL_AND_UNWIND_PLAYBOOK.pdf", "Part 2 - Control & Unwind Playbook",
     "Where your control lives (IP license, estate mandate, trust), the golden rule (never seize their shares), sour scenarios + counters, the rearrange menu, and what to pre-install now."),
    ("LANDTEK_OPERATIONALIZE_A_Z.pdf", "Part 3 - A-Z Operational Playbook",
     "From today to a company earning on the MWK estate (proof client): stand up the vehicle, wire the authority, turn on the money, run it as a business."),
]

# 2. Cover page.
s = getSampleStyleSheet()
body = ParagraphStyle('b', parent=s['Normal'], fontName='Helvetica', fontSize=11, leading=15, alignment=TA_JUSTIFY, spaceAfter=6)
title = ParagraphStyle('t', parent=body, fontName='Helvetica-Bold', fontSize=22, alignment=TA_CENTER, spaceAfter=6, leading=26)
sub = ParagraphStyle('sub', parent=body, fontSize=11, alignment=TA_CENTER, textColor='#555', spaceAfter=22)
toc = ParagraphStyle('toc', parent=body, fontName='Helvetica-Bold', fontSize=13, spaceBefore=10, spaceAfter=2, textColor='#0a5')
tocd = ParagraphStyle('tocd', parent=body, fontSize=10, leading=13, leftIndent=8, textColor='#333', spaceAfter=4)
box = ParagraphStyle('box', parent=body, fontSize=9.5, leading=13, leftIndent=8, textColor='#333')

cover_buf = io.BytesIO()
doc = SimpleDocTemplate(cover_buf, pagesize=FOLIO, topMargin=1.1*inch, bottomMargin=0.9*inch,
                        leftMargin=0.9*inch, rightMargin=0.9*inch, title="LandTek Formation Packet")
story = [
    Paragraph("LANDTEK", title),
    Paragraph("FORMATION PACKET", title),
    Paragraph("Everything to stand up the company, keep control, and run it - Path C "
              "(you own + license the IP; a Filipino principal owns the lean operating company).", sub),
    Paragraph("Contents", toc),
]
for _, t, d in PARTS:
    story += [Paragraph(t, toc), Paragraph(d, tocd)]
story += [
    Spacer(1, 0.3*inch),
    Paragraph("The core design in one line", toc),
    Paragraph("The crown jewel - the platform and IP - never enters the company; it stays yours and is "
              "licensed in. That single fact makes the Filipino ownership genuinely real (Anti-Dummy safe), "
              "makes your control durable (revoke the license, pull the mandate), and makes any future "
              "consolidation on naturalization a clean, arms-length transaction.", body),
    Spacer(1, 0.2*inch),
    Paragraph("Minimum headcount", toc),
    Paragraph("One genuine Filipino owner (the OPC's single stockholder) + one Filipino corporate secretary "
              "(an officer, no equity). That's the floor.", body),
    Spacer(1, 0.3*inch),
    Paragraph("<font size=8 color='#888'>Internal formation packet - not legal/corporate advice. You execute "
              "the structure yourself; a lawyer is optional and only files actual court suits. Nothing filed or "
              "incorporated by this document. Generated 2026-09-16.</font>", body),
]
doc.build(story)
cover_buf.seek(0)

# 3. Concatenate cover + the three parts.
writer = PdfWriter()
for page in PdfReader(cover_buf).pages:
    writer.add_page(page)
for fname, _, _ in PARTS:
    for page in PdfReader(os.path.join(HERE, fname)).pages:
        writer.add_page(page)
with open(OUT, "wb") as f:
    writer.write(f)
print("wrote", OUT, "-", len(writer.pages), "pages")
