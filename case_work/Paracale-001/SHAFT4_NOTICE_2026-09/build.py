# Builds the Shaft No. 4 letter (signed by Allan) as PDF from letter_draft.md. Run: python3 build.py
import re
from reportlab.lib.units import inch
PAGE = (8.5*inch, 13*inch)  # PH long bond
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.fonts import addMapping
addMapping("Times-Roman",1,0,"Times-Bold")

src = open("letter_draft.md").read().split("\n")[1:]  # drop the DRAFT header line
src = [l.replace("[Date]", "21 September 2026")
        .replace("[Sitio / Barangay]", "__________________")
        .replace("[phone / email]", "0917 155 4782 or shiraction2@gmail.com") for l in src]

body = ParagraphStyle("b", fontName="Times-Roman", fontSize=14, leading=18.5, alignment=TA_JUSTIFY, spaceAfter=10)
tight = ParagraphStyle("t", parent=body, spaceAfter=0, alignment=0)

def md(s):
    s = s.replace("&nbsp;", "").replace("&", "&amp;")
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)

story, block = [], []
def flush():
    if not block: return
    if len(block) > 1:
        for l in block: story.append(Paragraph(md(l), tight))
        story.append(Spacer(1, 10))
    else:
        story.append(Paragraph(md(block[0]), body))
    block.clear()

for l in src:
    if l.strip() == "":
        flush()
    elif l.startswith("______________________________"):
        flush(); story.append(Spacer(1, 26)); block.append(l)
    else:
        block.append(l.strip())
flush()

SimpleDocTemplate("Shaft4_letter_Allan_Inocalla.pdf", pagesize=PAGE,
                  leftMargin=1*inch, rightMargin=1*inch, topMargin=2.2*cm, bottomMargin=2*cm).build(story, onLaterPages=lambda c,d:(c.setFont("Times-Roman",10),c.drawCentredString(PAGE[0]/2,1.2*cm,"Page %d" % d.page)), onFirstPage=lambda c,d:(c.setFont("Times-Roman",10),c.drawCentredString(PAGE[0]/2,1.2*cm,"Page %d" % d.page)))
print("ok")
