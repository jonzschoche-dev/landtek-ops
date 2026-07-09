#!/usr/bin/env python3
"""
Stamp a boxed "ANNEX 'X'" label on the lower-right corner of every page of each
source PDF, filing-ready for CTN No. SL-2026-0128-1212.

Reads:  case_work/MWK-ARTA-1212/annexes/source/Annex_<L>_src.pdf
Writes: case_work/MWK-ARTA-1212/annexes/stamped/Annex_<L>.pdf

Handles per-page size + rotation. Idempotent (re-run overwrites stamped/).
"""
import io, os, sys, glob
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color, black

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "source")
OUT = os.path.join(HERE, "stamped")

# Annex letter -> short description (for the optional caption under the label)
LABELS = {
    "A": "ARTA Resolution",
    "B": "22 May 2025 Letter to Mayor Pajarillo",
    "C": "03 Oct 2025 Follow-up Letter",
    "D": "26 Jan 2026 Formal Motion to SB",
    "E": "26 Jan 2026 Ong Letter (SPA all-heirs)",
    "F": "Deed of Absolute Donation",
    "G": "SB Resolution Nos. 75-79",
    "H": "SB Resolution Nos. 103-86",
    "I": "Requests to SB Secretary for Minutes",
}


def make_overlay(w, h, letter):
    """Return a single-page PDF (bytes) sized w x h with a boxed ANNEX label
    in the lower-right corner."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    text = f'ANNEX "{letter}"'
    # Box geometry, scaled but clamped so it stays legible on small/large pages.
    fs = max(12, min(20, w * 0.028))
    pad = fs * 0.55
    c.setFont("Helvetica-Bold", fs)
    tw = c.stringWidth(text, "Helvetica-Bold", fs)
    box_w = tw + 2 * pad
    box_h = fs + 2 * pad
    margin = max(14, w * 0.03)
    x = w - box_w - margin
    y = margin
    # semi-opaque white fill so it stays readable over dark scans, black border
    c.setFillColor(Color(1, 1, 1, alpha=0.82))
    c.setStrokeColor(black)
    c.setLineWidth(1.4)
    c.roundRect(x, y, box_w, box_h, radius=3, stroke=1, fill=1)
    c.setFillColor(black)
    c.drawCentredString(x + box_w / 2, y + pad, text)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def stamp(src_path, letter, out_path):
    reader = PdfReader(src_path)
    writer = PdfWriter()
    for page in reader.pages:
        # Use the page's visible box; account for rotation so the label lands
        # in the lower-right of the *displayed* page.
        box = page.mediabox
        w = float(box.width)
        h = float(box.height)
        rot = (page.rotation or 0) % 360
        ow, oh = (h, w) if rot in (90, 270) else (w, h)
        overlay = PdfReader(make_overlay(ow, oh, letter)).pages[0]
        if rot:
            overlay.transfer_rotation_to_content()  # keep label upright
            overlay.rotate(rot)
        page.merge_page(overlay)
        writer.add_page(page)
    with open(out_path, "wb") as f:
        writer.write(f)
    return len(reader.pages)


def main():
    os.makedirs(OUT, exist_ok=True)
    srcs = sorted(glob.glob(os.path.join(SRC, "Annex_*_src.pdf")))
    if not srcs:
        print(f"No source PDFs in {SRC}", file=sys.stderr)
        sys.exit(1)
    for s in srcs:
        base = os.path.basename(s)
        letter = base.split("_")[1]  # Annex_<L>_src.pdf
        out = os.path.join(OUT, f"Annex_{letter}.pdf")
        try:
            n = stamp(s, letter, out)
            print(f"Annex {letter}: {n:>3} pg  ->  {os.path.relpath(out, HERE)}")
        except Exception as e:
            print(f"Annex {letter}: FAILED — {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
