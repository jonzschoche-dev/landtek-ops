#!/usr/bin/env python3
"""Build the concise memo+directive PDF for Atty. Botor (memo + 28-Aug Order scan)."""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, PageBreak, Paragraph, Image
from build_bound_pdf import md_to_flow, H1, ORDERS, HERE

OUT = os.path.join(HERE, "MEMO_CV26360_for_Atty_Botor.pdf")

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=1.9*cm, rightMargin=1.9*cm,
                        topMargin=1.7*cm, bottomMargin=1.7*cm,
                        title="Memo - CV 26-360 for Atty. Botor",
                        author="Jonathan Paul Zschoche")
with open(os.path.join(HERE, "06_MEMO_DIRECTIVE_BOTOR.md"), encoding="utf-8") as f:
    story = md_to_flow(f.read())
scan = os.path.join(ORDERS, "ORDER_2026-08-28_trial_setting_scan.jpg")
story.append(PageBreak())
story.append(Paragraph("Attachment — MTC Order of 28 August 2026", H1))
img = Image(scan)
maxw, maxh = A4[0] - 3.8*cm, A4[1] - 5*cm
r = min(maxw / img.imageWidth, maxh / img.imageHeight)
img.drawWidth, img.drawHeight = img.imageWidth * r, img.imageHeight * r
story.append(img)
doc.build(story)
print(OUT, os.path.getsize(OUT), "bytes")
