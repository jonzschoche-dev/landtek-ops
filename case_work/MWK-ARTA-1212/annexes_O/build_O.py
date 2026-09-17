#!/usr/bin/env python3
"""
Build the O-series annexes for the Third Manifestation (O.P.):
  1. Generate Annex O-8 (compilation of the SB's unsigned email acknowledgments).
  2. Normalize every Annex_O-*_src.pdf to 8.5 x 13 in (long bond), centered,
     aspect-preserved, and stamp ANNEX "O-N" lower-right.
Reads/writes under this folder: source/ -> stamped_O/
"""
import io, os, glob
from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.pdfgen import canvas
from reportlab.lib.colors import black, Color
from reportlab.lib.units import inch

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "source")
OUT = os.path.join(HERE, "stamped_O")
TW, TH = 8.5 * 72, 13.0 * 72

# ---- O-8: the SB's unsigned acknowledgment communications (authentic headers) ----
UNSIGNED = [
    ("12 January 2026, 8:27 AM", "Re: Road Donation Implementation and Inquiry, Mercedes",
     "Dear Mr. Zschoche:\n\nThis is to acknowledge receipt of your email."),
    ("22 January 2026, 2:49 PM", "Re: Road Donation Implementation and Inquiry, Mercedes",
     "Dear Mr. Zschoche:\n\nThis is to acknowledge receipt of your email."),
    ("30 January 2026, 9:41 AM", "Re: Road Donation Implementation and Inquiry, Mercedes",
     "This is to acknowledge receipt of your email."),
    ("19 February 2026, 8:50 AM", "Re: URGENT Bukas na Liham at Manifestasyon – Request for Immediate Forwarding",
     "This is to acknowledge receipt of your email."),
    ("19 February 2026, 8:51 AM", "Re: URGENT Bukas na Liham at Manifestasyon – Request for Immediate Forwarding",
     "This is to acknowledge receipt of your email."),
    ("12 March 2026, 5:33 PM", "Re: URGENT Bukas na Liham at Manifestasyon – Request for Immediate Forwarding",
     "This is to acknowledge receipt of your email."),
]


def gen_o8(path):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(TW, TH))
    ml = 1.0 * inch
    y = TH - 1.0 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(TW / 2, y, "UNSIGNED COMMUNICATIONS ISSUED TO PETITIONER"); y -= 16
    c.setFont("Helvetica", 9.5)
    c.drawCentredString(TW / 2, y, "Email communications from the Sangguniang Bayan of Mercedes — no signatory, no responsible officer identified"); y -= 12
    c.setLineWidth(0.8); c.line(ml, y, TW - ml, y); y -= 24
    for i, (date, subj, body) in enumerate(UNSIGNED, 1):
        if y < 2.0 * inch:
            c.showPage(); y = TH - 1.0 * inch
        c.setFont("Helvetica-Bold", 10); c.drawString(ml, y, f"{i}.  From:  Sangguniang Bayan <sangguniangbayan@mercedes.gov.ph>"); y -= 13
        c.setFont("Helvetica", 9.5)
        c.drawString(ml + 16, y, "To:      Jonathan Zschoche <jonzschoche@gmail.com>"); y -= 12
        c.drawString(ml + 16, y, f"Date:    {date}"); y -= 12
        c.drawString(ml + 16, y, f"Subject: {subj[:88]}"); y -= 15
        c.setFont("Helvetica-Oblique", 10)
        for line in body.split("\n"):
            c.drawString(ml + 30, y, line); y -= 13
        c.setFont("Helvetica", 8.5); c.setFillColor(Color(0.35,0.35,0.35))
        c.drawString(ml + 30, y, "[no signature block · no named officer or position]"); c.setFillColor(black); y -= 22
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(ml, 0.7 * inch, "Reproduced from the petitioner's Gmail (jonzschoche@gmail.com); sender/date/subject as received.")
    c.showPage(); c.save(); buf.seek(0)
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def overlay(label):
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=(TW, TH))
    text = f'ANNEX "{label}"'; fs = 16; pad = fs * 0.55
    c.setFont("Helvetica-Bold", fs); tw = c.stringWidth(text, "Helvetica-Bold", fs)
    bw, bh = tw + 2 * pad, fs + 2 * pad; margin = 22
    x, y = TW - bw - margin, margin
    c.setFillColor(Color(1,1,1,alpha=0.85)); c.setStrokeColor(black); c.setLineWidth(1.4)
    c.roundRect(x, y, bw, bh, 3, stroke=1, fill=1)
    c.setFillColor(black); c.drawCentredString(x + bw/2, y + pad, text)
    c.showPage(); c.save(); buf.seek(0); return PdfReader(buf).pages[0]


def normstamp(src, label, out):
    r = PdfReader(src); w = PdfWriter()
    for pg in r.pages:
        pg.transfer_rotation_to_content()
        b = pg.mediabox; llx, lly = float(b.left), float(b.bottom); sw, sh = float(b.width), float(b.height)
        s = min(TW/sw, TH/sh); tx = (TW - sw*s)/2 - llx*s; ty = (TH - sh*s)/2 - lly*s
        np = w.add_blank_page(width=TW, height=TH)
        np.merge_transformed_page(pg, Transformation().scale(s).translate(tx, ty))
        np.merge_page(overlay(label))
    with open(out, "wb") as f: w.write(f)
    return len(r.pages)


def main():
    os.makedirs(OUT, exist_ok=True)
    o8 = os.path.join(SRC, "Annex_O-8_src.pdf")
    if not os.path.exists(o8):
        gen_o8(o8); print("generated Annex_O-8_src.pdf (unsigned communications)")
    for s in sorted(glob.glob(os.path.join(SRC, "Annex_O-*_src.pdf"))):
        label = os.path.basename(s).split("_")[1]           # 'O-1'
        out = os.path.join(OUT, f"Annex_{label}.pdf")
        n = normstamp(s, label, out)
        print(f'Annex "{label}": {n:>2}pg -> {os.path.relpath(out, HERE)} @ 8.5x13')


if __name__ == "__main__":
    main()
