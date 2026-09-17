#!/usr/bin/env python3
"""Normalize O-1..O-12 to 8.5x13, stamp ANNEX "O-n", and bind with a List-of-Annexes cover."""
import io, os
from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color, black
from reportlab.lib.units import inch

HERE = os.path.dirname(os.path.abspath(__file__))
SRC, OUT = os.path.join(HERE, "source"), os.path.join(HERE, "stamped_O")
BOUND = os.path.join(HERE, "OP_ThirdManifestation_Annexes_O1-O12_bound_8.5x13.pdf")
TW, TH = 8.5 * 72, 13.0 * 72

ANNEXES = [
 ("O-1","ARTA Resolution dated 1 June 2026 in CTN SL-2026-0128-1212, recommending closure and, in the same instrument, referring Hon. Princess B. Torralba (R.A. 6713) and Mr. Tony Teope (R.A. 3019) to the Ombudsman"),
 ("O-2","Deed of Absolute Donation dated 19 April 1979 (road lots, TCT No. 4497), embodying acceptance under Sangguniang Bayan Resolution No. 75, s. 1979"),
 ("O-3","Sangguniang Bayan Resolution No. 103-86, amending Resolution No. 75-79 to add Road Lot 6-A and Dona Moreno Street"),
 ("O-4","Demand letter dated 22 May 2025 to Hon. Mayor Alexander L. Pajarillo for implementation of the naming condition"),
 ("O-5","Follow-up letter dated 3 October 2025 to Hon. Vice Mayor Jeana T. Yapyuco and the Sangguniang Bayan"),
 ("O-6","Formal Motion dated 26 January 2026, and letter of Hon. Francisco Noel Y. Ong of 26 January 2026 demanding an all-heirs SPA and the body's own Resolutions"),
 ("O-7","Written requests of 11 February and 5 March 2026 for the minutes and vote tallies of the 22 January, 4 February and 11 February 2026 sessions, and the SB Secretary's refusal of 5 March 2026 pending adoption"),
 ("O-8","Response of the Sangguniang Bayan of Mercedes dated 20 February 2026 - bearing no signature and identifying no responsible officer - expressly admitting that there was no final action"),
 ("O-9","Manifestation with Respectful Request for Written Clarification filed with ARTA on 9 July 2026"),
 ("O-10","Initial Petition to the Office of the President under Transmittal Ref. No. 050526-MRO-234187"),
 ("O-11","Proof that the ARTA Resolution was received on 8 July 2026"),
 ("O-12","Notarized and apostilled Special Power of Attorney of Patricia Keesey Zschoche"),
]


def overlay(label):
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=(TW, TH))
    RED = Color(0.78, 0.05, 0.07)
    txt = f'ANNEX "{label}"'; fs = 21; pad = fs * 0.6
    c.setFont("Helvetica-Bold", fs); tw = c.stringWidth(txt, "Helvetica-Bold", fs)
    bw, bh = tw + 2 * pad, fs + 2 * pad; m = 24
    x, y = TW - bw - m, m
    c.setFillColor(Color(1, 1, 1, alpha=0.9)); c.setStrokeColor(RED); c.setLineWidth(2.2)
    c.roundRect(x, y, bw, bh, 4, stroke=1, fill=1)
    c.setFillColor(RED); c.drawCentredString(x + bw / 2, y + pad, txt)
    c.showPage(); c.save(); buf.seek(0); return PdfReader(buf).pages[0]


def normalize_stamp(src, label, out):
    r = PdfReader(src); w = PdfWriter()
    for p in r.pages:
        p.transfer_rotation_to_content()
        b = p.mediabox; llx, lly = float(b.left), float(b.bottom)
        sw, sh = float(b.width), float(b.height)
        s = min(TW / sw, TH / sh)
        tx = (TW - sw * s) / 2 - llx * s; ty = (TH - sh * s) / 2 - lly * s
        pg = w.add_blank_page(width=TW, height=TH)
        pg.merge_transformed_page(p, Transformation().scale(s).translate(tx, ty))
        pg.merge_page(overlay(label))
    with open(out, "wb") as f: w.write(f)
    return len(r.pages)


def wrap(c, t, x, y, width, font="Helvetica", size=8.8, lead=11.5):
    line = ""
    for word in t.split():
        cand = (line + " " + word).strip()
        if c.stringWidth(cand, font, size) <= width: line = cand
        else: c.drawString(x, y, line); y -= lead; line = word
    if line: c.drawString(x, y, line); y -= lead
    return y


def cover(start):
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=(TW, TH)); ml = 0.85 * inch
    y = TH - 0.8 * inch
    c.setFont("Helvetica-Bold", 12.5); c.drawCentredString(TW / 2, y, "LIST OF ANNEXES"); y -= 17
    c.setFont("Helvetica", 9)
    for ln in ["Third Manifestation (with Motion to Consolidate; in the Alternative, Appeal Memorandum and Notice of Appeal;",
               "with Motion under Section 3, Administrative Order No. 22)",
               "Office of the President  -  O.P. Case No. ______  (Transmittal Ref.: 050526-MRO-234187)",
               "ARTA Case No. CTN SL-2026-0128-1212  -  Zschoche v. Hon. Jeana T. Yapyuco, et al."]:
        c.drawCentredString(TW / 2, y, ln); y -= 12
    y -= 5; c.setLineWidth(0.8); c.line(ml, y, TW - ml, y); y -= 19
    for lab, desc in ANNEXES:
        c.setFont("Helvetica-Bold", 10); c.drawString(ml, y, f'Annex "{lab}"')
        c.setFont("Helvetica", 8.6); c.drawRightString(TW - ml, y, f"p. {start[lab]}")
        y -= 12; c.setFont("Helvetica", 8.8)
        y = wrap(c, desc, ml + 15, y, TW - 2 * ml - 15); y -= 8
    c.setFont("Helvetica-Oblique", 7.6)
    c.drawString(ml, 0.62 * inch, "Each annex bears a boxed ANNEX label lower-right; all pages 8.5 x 13 in. (long bond).")
    c.showPage(); c.save(); buf.seek(0); return PdfReader(buf).pages[0]


def main():
    os.makedirs(OUT, exist_ok=True)
    n = {}
    for lab, _ in ANNEXES:
        src = os.path.join(SRC, f"Annex_{lab}_src.pdf")
        dst = os.path.join(OUT, f"Annex_{lab}.pdf")
        n[lab] = normalize_stamp(src, lab, dst)
        print(f'Annex "{lab}": {n[lab]:>2}pp -> stamped_O/Annex_{lab}.pdf @ 8.5x13')
    start, p = {}, 2
    for lab, _ in ANNEXES: start[lab] = p; p += n[lab]
    w = PdfWriter(); w.add_page(cover(start))
    for lab, _ in ANNEXES:
        for pg in PdfReader(os.path.join(OUT, f"Annex_{lab}.pdf")).pages: w.add_page(pg)
    with open(BOUND, "wb") as f: w.write(f)
    print(f"\nBound -> {os.path.basename(BOUND)} ({len(w.pages)} pp)")
    for lab, _ in ANNEXES: print(f'  Annex "{lab}": p.{start[lab]} ({n[lab]}pp)')


if __name__ == "__main__":
    main()
