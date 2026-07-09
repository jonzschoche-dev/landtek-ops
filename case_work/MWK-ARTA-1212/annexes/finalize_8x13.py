#!/usr/bin/env python3
"""
Normalize every annex source to 8.5 x 13 in (Philippine legal / long bond),
centered + aspect-preserved, then stamp ANNEX "X" lower-right.

Reads:  source/Annex_<L>_src.pdf
Writes: stamped/Annex_<L>.pdf   (all pages exactly 612 x 936 pt)
"""
import io, os, glob
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import RectangleObject
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color, black

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "source")
OUT = os.path.join(HERE, "stamped")

TW, TH = 8.5 * 72, 13.0 * 72          # 612 x 936 pt  (8.5 x 13 in)


def annex_overlay(letter):
    """Full-page 8.5x13 overlay with a boxed ANNEX label lower-right."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(TW, TH))
    text = f'ANNEX "{letter}"'
    fs = 17
    pad = fs * 0.55
    c.setFont("Helvetica-Bold", fs)
    tw = c.stringWidth(text, "Helvetica-Bold", fs)
    box_w, box_h = tw + 2 * pad, fs + 2 * pad
    margin = 22
    x, y = TW - box_w - margin, margin
    c.setFillColor(Color(1, 1, 1, alpha=0.85))
    c.setStrokeColor(black)
    c.setLineWidth(1.4)
    c.roundRect(x, y, box_w, box_h, radius=3, stroke=1, fill=1)
    c.setFillColor(black)
    c.drawCentredString(x + box_w / 2, y + pad, text)
    c.showPage()
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def normalize_page(writer, src_page, letter):
    src_page.transfer_rotation_to_content()      # bake any /Rotate into content
    box = src_page.mediabox
    llx, lly = float(box.left), float(box.bottom)
    sw, sh = float(box.width), float(box.height)
    scale = min(TW / sw, TH / sh)
    tx = (TW - sw * scale) / 2 - llx * scale
    ty = (TH - sh * scale) / 2 - lly * scale
    page = writer.add_blank_page(width=TW, height=TH)
    op = Transformation().scale(scale).translate(tx, ty)
    page.merge_transformed_page(src_page, op)
    page.merge_page(annex_overlay(letter))       # stamp on the normalized canvas
    return page


def main():
    os.makedirs(OUT, exist_ok=True)
    for s in sorted(glob.glob(os.path.join(SRC, "Annex_*_src.pdf"))):
        letter = os.path.basename(s).split("_")[1]
        reader = PdfReader(s)
        writer = PdfWriter()
        for p in reader.pages:
            normalize_page(writer, p, letter)
        out = os.path.join(OUT, f"Annex_{letter}.pdf")
        with open(out, "wb") as f:
            writer.write(f)
        print(f"Annex {letter}: {len(reader.pages):>2}pg -> {os.path.relpath(out, HERE)} @ 8.5x13")


if __name__ == "__main__":
    main()
