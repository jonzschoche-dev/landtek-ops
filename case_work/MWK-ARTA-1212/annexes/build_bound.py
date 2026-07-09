#!/usr/bin/env python3
"""
Bind the stamped annexes into ONE 8.5 x 13 PDF, in filing order A..I,
with a cover Index of Annexes. Annex G has no standalone document (its
acceptance is embodied in the Deed, Annex F) -> a cross-reference divider.
"""
import io, os
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import black, Color
from reportlab.lib.units import inch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "MWK-ARTA-1212_Annexes_A-I_bound_8.5x13.pdf")
TW, TH = 8.5 * 72, 13.0 * 72

# (letter, description, stamped file or None if divider)
ANNEXES = [
    ("A", "Resolution of the Anti-Red Tape Authority (CTN SL-2026-0128-1212), signed 01 June 2026", "stamped/Annex_A.pdf"),
    ("B", "Letter dated 22 May 2025 to Hon. Mayor Alexander L. Pajarillo", "stamped/Annex_B.pdf"),
    ("C", "Follow-up letter dated 03 October 2025 to Hon. VM Yapyuco and the Sangguniang Bayan", "stamped/Annex_C.pdf"),
    ("D", "Formal Motion dated 26 January 2026 (Submission of Position in Lieu of Attendance)", "stamped/Annex_D.pdf"),
    ("E", "Letter of Hon. Francisco Noel Y. Ong dated 26 January 2026 (SPA signed by all heirs)", "stamped/Annex_E.pdf"),
    ("F", "Deed of Absolute Donation (road lots; acceptance per Resolution No. 75, s. 1979)", "stamped/Annex_F.pdf"),
    ("G", "Sangguniang Bayan Resolution No. 75-79 (accepting the donation)", None),
    ("H", "Sangguniang Bayan Resolution No. 103-86 (amending Res. 75-79; Road Lot 6-A and Dona Moreno St.)", "stamped/Annex_H.pdf"),
    ("I", "Written request to the Secretary of the Sangguniang Bayan for the minutes (with the SB's refusal)", "stamped/Annex_I.pdf"),
]


def wrap(c, text, x, y, width, font="Helvetica", size=9.5, leading=13):
    words, line = text.split(), ""
    for w in words:
        t = (line + " " + w).strip()
        if c.stringWidth(t, font, size) <= width:
            line = t
        else:
            c.drawString(x, y, line); y -= leading; line = w
    if line:
        c.drawString(x, y, line); y -= leading
    return y


def page_counts():
    n = {}
    for letter, _, f in ANNEXES:
        n[letter] = len(PdfReader(os.path.join(HERE, f)).pages) if f else 1
    return n


def cover(start_pages):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(TW, TH))
    ml = 1.0 * inch
    y = TH - 1.0 * inch
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(TW / 2, y, "INDEX OF ANNEXES"); y -= 20
    c.setFont("Helvetica", 10.5)
    c.drawCentredString(TW / 2, y, "CTN No. SL-2026-0128-1212"); y -= 15
    c.drawCentredString(TW / 2, y, "Jonathan Paul Zschoche v. Hon. Jeana T. Yapyuco, et al."); y -= 10
    c.setLineWidth(0.8); c.line(ml, y, TW - ml, y); y -= 26
    for letter, desc, f in ANNEXES:
        c.setFont("Helvetica-Bold", 10.5)
        c.drawString(ml, y, f'Annex "{letter}"')
        c.setFont("Helvetica", 9)
        c.drawRightString(TW - ml, y, f"p. {start_pages[letter]}")
        y -= 13
        c.setFont("Helvetica", 9.5)
        note = desc if f else desc + "  (embodied in the Deed of Absolute Donation, Annex “F” — acceptance clause)"
        y = wrap(c, note, ml + 16, y, TW - 2 * ml - 16)
        y -= 12
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(ml, 0.7 * inch, "Each annex bears a boxed ANNEX label lower-right; all pages 8.5 x 13 in. (long bond).")
    c.showPage(); c.save(); buf.seek(0)
    return PdfReader(buf).pages[0]


def divider_G():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(TW, TH))
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(TW / 2, TH / 2 + 30, 'ANNEX "G"')
    c.setFont("Helvetica", 11)
    c.drawCentredString(TW / 2, TH / 2, "Sangguniang Bayan Resolution No. 75-79 (accepting the donation)")
    c.setFont("Helvetica-Oblique", 10)
    y = TH / 2 - 26
    for ln in ["The acceptance under Resolution No. 75, series of 1979 is embodied in the",
               "Deed of Absolute Donation (Annex “F”) and in the amending Resolution",
               "No. 103-86 (Annex “H”). No separate certified copy is in the record."]:
        c.drawCentredString(TW / 2, y, ln); y -= 15
    # corner label to match the others
    c.setFont("Helvetica-Bold", 17)
    c.setFillColor(Color(1, 1, 1, alpha=0.85)); c.setStrokeColor(black); c.setLineWidth(1.4)
    txt = 'ANNEX "G"'; tw = c.stringWidth(txt, "Helvetica-Bold", 17)
    c.roundRect(TW - tw - 2 * 9.35 - 22, 22, tw + 2 * 9.35, 17 + 2 * 9.35, 3, stroke=1, fill=1)
    c.setFillColor(black); c.drawString(TW - tw - 9.35 - 22, 22 + 9.35, txt)
    c.showPage(); c.save(); buf.seek(0)
    return PdfReader(buf).pages[0]


def main():
    counts = page_counts()
    start, p = {}, 2  # cover is p.1
    for letter, _, _ in ANNEXES:
        start[letter] = p; p += counts[letter]
    writer = PdfWriter()
    writer.add_page(cover(start))
    for letter, _, f in ANNEXES:
        if f:
            for pg in PdfReader(os.path.join(HERE, f)).pages:
                writer.add_page(pg)
        else:
            writer.add_page(divider_G())
    with open(OUT, "wb") as fh:
        writer.write(fh)
    print(f"Bound -> {os.path.basename(OUT)} ({len(writer.pages)} pp)")
    for letter, _, _ in ANNEXES:
        print(f'  Annex "{letter}": p.{start[letter]} ({counts[letter]}pp)')


if __name__ == "__main__":
    main()
