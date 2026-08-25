#!/usr/bin/env python3
"""Bind the COMPLETE Relucio transmittal packet, 8.5x13 throughout:
  letter (4pp) + ATTACHMENT 1 (Guerrero letter, received-stamped) +
  ATTACHMENT 2 divider + the bound Enclosures 1-9 (49pp, already stamped/indexed).
"""
import io, os
from pypdf import PdfReader, PdfWriter, Transformation, PageObject
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color, black
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
MWK = os.path.dirname(HERE)
FOLIO = (8.5 * 72, 13.0 * 72)

F = "/System/Library/Fonts/Supplemental"
pdfmetrics.registerFont(TTFont("TNR", f"{F}/Times New Roman.ttf"))
pdfmetrics.registerFont(TTFont("TNR-Bold", f"{F}/Times New Roman Bold.ttf"))
pdfmetrics.registerFont(TTFont("TNR-Italic", f"{F}/Times New Roman Italic.ttf"))


def normalize(pg, rot=0):
    pw, ph = float(pg.mediabox.width), float(pg.mediabox.height)
    if rot == 0 and pw > ph:
        rot = 90
    tgt = PageObject.create_blank_page(width=FOLIO[0], height=FOLIO[1])
    t = Transformation()
    if rot == 90:
        t = t.rotate(90).translate(ph, 0)
        pw, ph = ph, pw
    s = min(FOLIO[0] / pw, FOLIO[1] / ph)
    t = t.scale(s).translate((FOLIO[0] - pw * s) / 2, (FOLIO[1] - ph * s) / 2)
    tgt.merge_transformed_page(pg, t)
    return tgt


def stamp(pg, text):
    pw, ph = float(pg.mediabox.width), float(pg.mediabox.height)
    ov = io.BytesIO()
    c = canvas.Canvas(ov, pagesize=(pw, ph))
    fs = 13
    pad = fs * 0.5
    c.setFont("Helvetica-Bold", fs)
    tw = c.stringWidth(text, "Helvetica-Bold", fs)
    bw, bh = tw + 2 * pad, fs + 2 * pad
    m = 18
    x, y = pw - bw - m, m
    c.setFillColor(Color(1, 1, 1, alpha=0.85))
    c.setStrokeColor(black)
    c.setLineWidth(1.3)
    c.roundRect(x, y, bw, bh, radius=3, stroke=1, fill=1)
    c.setFillColor(black)
    c.drawCentredString(x + bw / 2, y + pad, text)
    c.showPage()
    c.save()
    ov.seek(0)
    pg.merge_page(PdfReader(ov).pages[0])
    return pg


def divider(title, lines):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=FOLIO)
    W, H = FOLIO
    c.setFont("TNR-Bold", 22)
    c.drawCentredString(W / 2, H * 0.60, title)
    c.setFont("TNR", 12)
    y = H * 0.54
    for ln in lines:
        c.drawCentredString(W / 2, y, ln)
        y -= 17
    c.showPage()
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


out = PdfWriter()

# 1) The letter
for pg in PdfReader(os.path.join(MWK, "DILG_PD_RELUCIO_FOLLOWUP_2026-08-26.pdf")).pages:
    out.add_page(normalize(pg))

# 2) Attachment 1 — Guerrero letter as received
for pg in PdfReader(os.path.join(MWK, "DILG_MLGOO_RESPONSE_Guerrero_2026-08-18.pdf")).pages:
    out.add_page(stamp(normalize(pg), 'ATTACHMENT "1"'))

# 3) Attachment 2 — divider + the bound Enclosures 1-9 (keep their own stamps/index)
out.add_page(divider('ATTACHMENT "2"', [
    'Enclosures "1" through "9" to the Letter of 18 August 2026 (Attachment "1"),',
    "bound with Index of Enclosures — 49 pages.",
    "Each enclosure page carries its own boxed ENCLOSURE label at the lower right.",
]))
for pg in PdfReader(os.path.join(HERE, "DILG_Enclosures_1-9_bound_8.5x13.pdf")).pages:
    out.add_page(normalize(pg))

# 4) Attachment 3 -- divider for the physical DILG instruments (paper originals inserted at filing)
out.add_page(divider('ATTACHMENT "3"', [
    "MLGOO Acknowledgment and Action Taken letter, 24 August 2026, and",
    "2nd Indorsements of 25 August 2026 (to the Municipal Mayor and to the",
    "Sangguniang Bayan thru the Secretary to the Sanggunian), as received-stamped.",
    "Paper originals inserted at filing by the affiant.",
]))

OUT = os.path.join(MWK, "DILG_PD_RELUCIO_PACKET_2026-08-26_8.5x13.pdf")
with open(OUT, "wb") as f:
    out.write(f)
r = PdfReader(OUT)
sizes = {(round(float(p.mediabox.width)), round(float(p.mediabox.height))) for p in r.pages}
print("BOUND:", OUT, len(r.pages), "pp, sizes:", sizes)
