#!/usr/bin/env python3
"""sign_pdf.py — overlay Jonathan's wet-ink signature onto a rendered PDF.

ONE signature asset, ONE code path, so every renderer signs identically:
    assets/signature/jpz_signature.png   (transparent PNG, extracted deploy_1010)

  python3 scripts/sign_pdf.py in.pdf                      # → in_signed.pdf, last page, above the name line
  python3 scripts/sign_pdf.py in.pdf -o out.pdf --page 2 --x 1.2 --y 2.4 --width 2.4
  python3 scripts/sign_pdf.py in.pdf --force              # sign even a DRAFT-marked document

DRAFT GUARD (the one rule that is not mine to relax silently): this refuses to sign a page carrying
DRAFT / NOT FOR SERVICE / DO-NOT-SERVE / HELD markers unless --force. A signed draft looks EXECUTED —
and the whole service/ingestion discipline (draft ≠ executed; a clock starts only on a served,
stamped instrument) depends on those two being distinguishable in the corpus. --force is one word
away when a "draft"-labelled instrument is genuinely being executed.

For reportlab renderers, skip the merge and draw directly:  draw_signature(canvas, x_in, y_in, width_in)
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys

from pypdf import PdfReader, PdfWriter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.lib.utils import ImageReader

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGNATURE_PATH = os.path.join(ROOT, "assets", "signature", "jpz_signature.png")
DEFAULT_WIDTH_IN = 2.3          # natural signing size on letter/folio
DRAFT_RE = re.compile(r"\bDRAFT\b|NOT FOR SERVICE|DO-?NOT-?SERVE|\bHELD\b|STAGED NOT SENT", re.I)


def signature_reader():
    if not os.path.exists(SIGNATURE_PATH):
        sys.exit(f"signature asset missing: {SIGNATURE_PATH}\n"
                 "It is gitignored on purpose (forgeable material) — copy it to this machine.")
    return ImageReader(SIGNATURE_PATH)


def signature_size(width_in=DEFAULT_WIDTH_IN):
    """(w,h) in points, preserving the asset's aspect ratio."""
    iw, ih = signature_reader().getSize()
    w = width_in * inch
    return w, w * (ih / iw)


def draw_signature(canv, x_in, y_in, width_in=DEFAULT_WIDTH_IN):
    """Draw onto an open reportlab canvas (x_in,y_in = lower-left of the signature, inches)."""
    w, h = signature_size(width_in)
    canv.drawImage(signature_reader(), x_in * inch, y_in * inch, width=w, height=h, mask="auto")
    return w, h


def page_is_draft(page):
    try:
        return bool(DRAFT_RE.search(page.extract_text() or ""))
    except Exception:
        return False


# Anchors that mark a real signature block, best first. "Last page" is the WRONG default on any
# instrument with enclosures (the Teope demand's last page is its Schedule) — so find the block.
_ANCHORS = (
    (r"^_{6,}", "above_line"),                              # a typed signature rule
    (r"JONATHAN\s+PAUL\s+ZSCHOCHE", "above_name"),          # the typed name block
    (r"Respectfully|Very truly yours|Sincerely", "below_closing"),
)


MARGIN_IN = 0.5          # signature must sit fully inside this edge margin
MIN_WIDTH_IN = 1.45      # shrink this far to fit a tight block before giving up


def find_signature_spot(path, width_in=DEFAULT_WIDTH_IN):
    """Locate the signature block → (page_index, x_in, y_in, width_in), or None.

    FIT-AWARE: a real instrument's block is often split across a page break (the Teope demand closes
    'Respectfully,' at the foot of p2 and carries the typed name to the top of p3) — so a naive anchor
    puts the signature off the page. Each candidate is validated against the page margins and the
    signature is shrunk (to MIN_WIDTH_IN) to fit. If nothing fits, return None and let the caller say
    so rather than stamping the signature somewhere wrong.
    """
    try:
        import fitz
    except ImportError:
        return None
    try:
        doc = fitz.open(path)
    except Exception:
        return None
    iw, ih = signature_reader().getSize()
    aspect = ih / iw
    try:
        for pno in range(len(doc) - 1, -1, -1):          # last page first
            page = doc[pno]
            ph, pw = page.rect.height / 72.0, page.rect.width / 72.0
            lines = page.get_text("text").splitlines()
            if not lines:
                continue
            for pat, mode in _ANCHORS:
                rx = re.compile(pat, re.I | re.M)
                hit = None
                for ln in lines:
                    if rx.search(ln.strip()):
                        rects = page.search_for(ln.strip()[:40]) if ln.strip() else []
                        if rects:
                            hit = rects[0]
                            break
                if not hit:
                    continue
                x_in = max(MARGIN_IN + 0.35, hit.x0 / 72.0)
                anchor_top_in = ph - hit.y0 / 72.0       # anchor's top edge, from page bottom
                anchor_bot_in = ph - hit.y1 / 72.0
                w = width_in
                while w >= MIN_WIDTH_IN - 1e-6:
                    h = w * aspect
                    y_in = (anchor_bot_in - 0.12 - h) if mode == "below_closing" else (anchor_top_in + 0.05)
                    if y_in >= MARGIN_IN and (y_in + h) <= (ph - MARGIN_IN) and (x_in + w) <= (pw - MARGIN_IN):
                        return pno, x_in, y_in, round(w, 2)
                    w -= 0.15
    finally:
        doc.close()
    return None


def sign(in_pdf, out_pdf=None, page_no=None, x_in=None, y_in=None,
         width_in=DEFAULT_WIDTH_IN, force=False):
    reader = PdfReader(in_pdf)
    auto = None
    if page_no is None and x_in is None and y_in is None:
        auto = find_signature_spot(in_pdf, width_in)      # anchor on the real signature block
        if auto:
            page_no, x_in, y_in, width_in = auto
        else:
            sys.exit("REFUSED: no signature block with room was found (checked signature rule, typed "
                     "name, and closing on every page, shrinking to fit).\n"
                     "This usually means the block is split across a page break — fix the layout, or "
                     "place it explicitly:  --page N --x <in> --y <in> [--width <in>]")
    if page_no is None:
        page_no = -1
    idx = (len(reader.pages) + page_no) if page_no < 0 else page_no
    if not 0 <= idx < len(reader.pages):
        sys.exit(f"page {page_no} out of range (doc has {len(reader.pages)})")
    target = reader.pages[idx]

    if page_is_draft(target) and not force:
        sys.exit(f"REFUSED: page {idx + 1} carries a DRAFT / NOT-FOR-SERVICE / HELD marker.\n"
                 "A signed draft reads as EXECUTED, and the corpus must keep prepared and executed "
                 "distinguishable (service starts clocks; drafts never do).\n"
                 "If this instrument is genuinely being executed, re-run with --force.")

    pw, ph = float(target.mediabox.width), float(target.mediabox.height)
    w, h = signature_size(width_in)
    # default placement: left margin, low on the page — above a typed name/signature line
    x = (x_in * inch) if x_in is not None else 1.0 * inch
    y = (y_in * inch) if y_in is not None else 1.55 * inch
    x = max(0, min(x, pw - w))
    y = max(0, min(y, ph - h))

    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=(pw, ph))
    c.drawImage(signature_reader(), x, y, width=w, height=h, mask="auto")
    c.save()
    buf.seek(0)
    target.merge_page(PdfReader(buf).pages[0])

    writer = PdfWriter()
    for p in reader.pages:
        writer.add_page(p)
    out_pdf = out_pdf or re.sub(r"\.pdf$", "", in_pdf, flags=re.I) + "_signed.pdf"
    with open(out_pdf, "wb") as fh:
        writer.write(fh)
    return out_pdf, idx + 1, (x / inch, y / inch, width_in)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out")
    ap.add_argument("--page", type=int, help="1-based; negative counts from the end. "
                    "Omit for AUTO: find the signature block (line / typed name / closing).")
    ap.add_argument("--x", type=float, help="inches from left (default 1.0)")
    ap.add_argument("--y", type=float, help="inches from bottom (default 1.55)")
    ap.add_argument("--width", type=float, default=DEFAULT_WIDTH_IN)
    ap.add_argument("--force", action="store_true", help="sign even a DRAFT-marked page")
    a = ap.parse_args()
    page = None if a.page is None else (a.page - 1 if a.page > 0 else a.page)
    out, pg, (x, y, w) = sign(a.pdf, a.out, page, a.x, a.y, a.width, a.force)
    print(f"{out}\n  signed page {pg} at {x:.2f}in,{y:.2f}in width {w}in"
          f"{'  [FORCED over draft marker]' if a.force else ''}")


if __name__ == "__main__":
    main()
