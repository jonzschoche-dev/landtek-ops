# Render BIR_1901_FILL_KEY.md → PDF. Run: python3 render.py
import re
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY

src = open('BIR_1901_FILL_KEY.md').read()
ss = getSampleStyleSheet()
H1 = ParagraphStyle('H1', parent=ss['Normal'], fontName='Helvetica-Bold', fontSize=15, leading=18, spaceAfter=8)
H2 = ParagraphStyle('H2', parent=ss['Normal'], fontName='Helvetica-Bold', fontSize=11.5, leading=14, spaceBefore=12, spaceAfter=5)
P  = ParagraphStyle('P', parent=ss['Normal'], fontName='Helvetica', fontSize=9.2, leading=12.4, alignment=TA_JUSTIFY, spaceAfter=5)
C  = ParagraphStyle('C', parent=P, fontSize=8.3, leading=10.6, spaceAfter=0, alignment=0)
CH = ParagraphStyle('CH', parent=C, fontName='Helvetica-Bold')

def inline(t):
    t = t.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    t = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', t)
    t = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', t)
    t = re.sub(r'`([^`]+)`', r'<font face="Courier">\1</font>', t)
    t = re.sub(r'\[(.+?)\]\((.+?)\)', r'\1', t)
    return t

story, rows = [], []
def flush():
    global rows
    if not rows: return
    hdr, body = rows[0], rows[1:]
    ncol = len(hdr)
    widths = {3:[1.3*cm, 3.6*cm, 8.3*cm, 4.0*cm], 2:[3.2*cm, 14.0*cm]}.get(ncol) or [17.2*cm/ncol]*ncol
    if ncol == 4: widths = [1.3*cm, 3.4*cm, 8.2*cm, 4.3*cm]
    data = [[Paragraph(inline(c), CH) for c in hdr]] + [[Paragraph(inline(c), C) for c in r] for r in body]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.4,colors.HexColor('#999999')),
                           ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8e8e8')),
                           ('VALIGN',(0,0),(-1,-1),'TOP'),
                           ('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),
                           ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
    story.append(t); story.append(Spacer(1, 8)); rows = []

for line in src.split('\n'):
    l = line.rstrip()
    if l.startswith('|'):
        cells = [c.strip() for c in l.strip('|').split('|')]
        if all(set(c) <= set('-: ') for c in cells): continue
        rows.append(cells); continue
    flush()
    if not l.strip(): continue
    if l.startswith('# '):   story.append(Paragraph(inline(l[2:]), H1))
    elif l.startswith('## '): story.append(Paragraph(inline(l[3:]), H2))
    elif l.startswith('---'): story.append(Spacer(1, 6))
    elif l.startswith('- [ ] '): story.append(Paragraph('&#9744;  ' + inline(l[6:]), P))
    else: story.append(Paragraph(inline(l), P))
flush()
SimpleDocTemplate('BIR_1901_FILL_KEY.pdf', pagesize=A4, leftMargin=2*cm, rightMargin=1.8*cm,
                  topMargin=1.6*cm, bottomMargin=1.5*cm,
                  title='BIR 1901 fill key - AVI Gold Processing Plant').build(story)
print('rendered')
