#!/usr/bin/env python3
"""Bind O-1..O-8 (already stamped, 8.5x13) into one PDF with a List-of-Annexes cover."""
import io, os
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "MWK-ARTA-1212_ThirdManifestation_Annexes_O1-O8_bound_8.5x13.pdf")
TW, TH = 8.5 * 72, 13.0 * 72

ANNEXES = [
    ("O-1", "Resolution of the Anti-Red Tape Authority dated 1 June 2026 in CTN SL-2026-0128-1212 — recommending closure and, in the same instrument, referring two officials to the Office of the Ombudsman", "stamped_O/Annex_O-1.pdf"),
    ("O-2", "1979 Deed of Absolute Donation conveying the public roadway lots to the Municipality of Mercedes, with the express road-naming condition", "stamped_O/Annex_O-2.pdf"),
    ("O-3", "Sangguniang Bayan Resolution No. 103-86 (16 July 1986) accepting/amending the 1979 donation acceptance (Res. No. 75-79) on its naming condition", "stamped_O/Annex_O-3.pdf"),
    ("O-4", "Letter of 22 May 2025 formally requesting implementation of the naming condition", "stamped_O/Annex_O-4.pdf"),
    ("O-5", "Formal request dated 3 October 2025 — transmission, encroachments, and inclusion in the Executive-Legislative Agenda", "stamped_O/Annex_O-5.pdf"),
    ("O-6", "Written admission of Respondents — letter dated 12 November 2025 signed by Vice Mayor Jeana T. Yapyuco (“NO” to transmittal/ELA priority) — that no final action was taken", "stamped_O/Annex_O-6.pdf"),
    ("O-7", "Written refusal of the Secretary of the Sangguniang Bayan (5 March 2026) to release the session minutes pending internal adoption", "stamped_O/Annex_O-7.pdf"),
    ("O-8", "Unsigned communication issued to Petitioner, with no responsible officer identified", "stamped_O/Annex_O-8.pdf"),
]


def wrap(c, text, x, y, width, font="Helvetica", size=9.5, leading=12.5):
    line = ""
    for w in text.split():
        t = (line + " " + w).strip()
        if c.stringWidth(t, font, size) <= width:
            line = t
        else:
            c.drawString(x, y, line); y -= leading; line = w
    if line:
        c.drawString(x, y, line); y -= leading
    return y


def counts():
    return {lab: len(PdfReader(os.path.join(HERE, f)).pages) for lab, _, f in ANNEXES}


def cover(start):
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=(TW, TH)); ml = 1.0 * inch
    y = TH - 0.9 * inch
    c.setFont("Helvetica-Bold", 13); c.drawCentredString(TW/2, y, "LIST OF ANNEXES"); y -= 18
    c.setFont("Helvetica", 9.5)
    for ln in ["Third Manifestation (with Motion to Consolidate; and in the Alternative, Notice of Appeal)",
               "Office of the President  —  O.P. Case No. ______  (Transmittal Ref.: 050526-MRO-234187)",
               "re: ARTA Case No. CTN SL-2026-0128-1212  —  Zschoche v. Vice Mayor Yapyuco, et al."]:
        c.drawCentredString(TW/2, y, ln); y -= 13
    y -= 6; c.setLineWidth(0.8); c.line(ml, y, TW-ml, y); y -= 22
    for lab, desc, _ in ANNEXES:
        c.setFont("Helvetica-Bold", 10.5); c.drawString(ml, y, f'Annex "{lab}"')
        c.setFont("Helvetica", 9); c.drawRightString(TW-ml, y, f"p. {start[lab]}")
        y -= 13; c.setFont("Helvetica", 9.5)
        y = wrap(c, desc, ml+16, y, TW-2*ml-16); y -= 11
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(ml, 0.7*inch, "Each annex bears a boxed ANNEX label lower-right; all pages 8.5 x 13 in. (long bond).")
    c.showPage(); c.save(); buf.seek(0); return PdfReader(buf).pages[0]


def main():
    n = counts(); start = {}; p = 2
    for lab, _, _ in ANNEXES:
        start[lab] = p; p += n[lab]
    w = PdfWriter(); w.add_page(cover(start))
    for lab, _, f in ANNEXES:
        for pg in PdfReader(os.path.join(HERE, f)).pages:
            w.add_page(pg)
    with open(OUT, "wb") as fh:
        w.write(fh)
    print(f"Bound -> {os.path.basename(OUT)} ({len(w.pages)} pp)")
    for lab, _, _ in ANNEXES:
        print(f'  Annex "{lab}": p.{start[lab]} ({n[lab]}pp)')


if __name__ == "__main__":
    main()
