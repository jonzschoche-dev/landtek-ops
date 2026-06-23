#!/usr/bin/env python3
"""pdf_compress.py — shrink a PDF for delivery, $0 and local (PyMuPDF). Ghostscript-free.

Scanned corpus PDFs are huge (the 51-page doc-700 bundle is 16.6 MB ≈ 325 KB/page of raw scan). This
downsamples + JPEG-recompresses the IMAGE pages to a target DPI/quality, while leaving real text pages
untouched — it never rasterizes selectable text. Pairs with pdf_pages: carve the pages you need, then
compress the exhibit before sending.

  python3 scripts/pdf_compress.py in.pdf [out.pdf] [--dpi 150] [--quality 55]
  from pdf_compress import compress; compress(inp, outp, dpi=150, quality=55)
"""
import os
import sys

import fitz  # PyMuPDF


def compress(inp, outp=None, dpi=150, quality=55):
    outp = outp or (inp[:-4] if inp.lower().endswith(".pdf") else inp) + "_small.pdf"
    src = fitz.open(inp)
    out = fitz.open()
    rasterized = 0
    for i in range(src.page_count):
        page = src[i]
        if (page.get_text() or "").strip():
            out.insert_pdf(src, from_page=i, to_page=i)          # real text page — keep vector/text intact
        else:
            pix = page.get_pixmap(dpi=dpi)                        # scanned page — downsample + JPEG
            if pix.alpha:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            img = pix.tobytes("jpeg", jpg_quality=quality)
            np = out.new_page(width=page.rect.width, height=page.rect.height)
            np.insert_image(np.rect, stream=img)
            rasterized += 1
    out.save(outp, garbage=4, deflate=True)
    out.close(); src.close()
    return outp, rasterized


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        sys.exit("usage: pdf_compress.py in.pdf [out.pdf] [--dpi 150] [--quality 55]")
    inp = args[0]
    outp = args[1] if len(args) > 1 and not args[1].startswith("-") else None
    dpi = int(args[args.index("--dpi") + 1]) if "--dpi" in args else 150
    q = int(args[args.index("--quality") + 1]) if "--quality" in args else 55
    if not os.path.exists(inp):
        sys.exit(f"[pdf_compress] no such file: {inp}")
    before = os.path.getsize(inp)
    outp, ras = compress(inp, outp, dpi, q)
    after = os.path.getsize(outp)
    pct = (1 - after / before) * 100 if before else 0
    print(f"[pdf_compress] {before//1024} KB → {after//1024} KB ({pct:.0f}% smaller, {ras} page(s) re-imaged @ {dpi}dpi/q{q}) → {outp}")


if __name__ == "__main__":
    main()
