#!/usr/bin/env python3
"""Lot 2-X subdivision-plan requests, Oct 2026, 8.5x13 throughout.
  01  DENR R5 (ARD Astor): 10 Region V plans       -> EMAIL (staged as Mail.app draft)
  02  LRA Administrator: (LRC)/(LRA) plans          -> COURIER
  03  Registrar of Deeds, Camarines Norte           -> COURIER
Each letter is e-signed (assets/signature/jpz_signature.png) and carries Annex "A",
the apostilled SPA of 18 May 2026 (Patricia Keesey Zschoche -> Jonathan Paul Zschoche)."""
import os, sys
from pypdf import PdfReader, PdfWriter

HERE = os.path.dirname(os.path.abspath(__file__))
MWK = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(MWK, "DENR_ASSESSOR_PACKET_2026-10"))
sys.path.insert(0, os.path.join(MWK, "OP_1321_packet"))
from build_op_packet import render_md, normalize, stamp  # noqa: E402
from build_packet import esign, table_page  # noqa: E402
from reportlab.lib.units import inch  # noqa: E402

SPA = os.path.join(HERE, "source", "SPA_Patricia_to_Jonathan_2026-05-18_apostilled.pdf")
ANNEX_DESC = "Special Power of Attorney, Patricia Keesey Zschoche to Jonathan Paul Zschoche, 18 May 2026 (apostilled, California Secretary of State No. 44327)"

LETTERS = [
    ("01_DENR_R5_Plans_Request.md", "Zschoche — Request for Lot 2-X subdivision plans, DENR Region V", "01_DENR_R5_Plans_Request_EMAIL.pdf"),
    ("02_LRA_Plans_Request.md", "Zschoche — Request for (LRC)/(LRA) plans, T-4497", "02_LRA_Plans_Request_COURIER.pdf"),
    ("03_RD_CamNorte_Subdivision_Instruments_Request.md", "Zschoche — Request for subdivision instruments, T-4497", "03_RD_CamNorte_Request_COURIER.pdf"),
]


def build(md, footer, out_name):
    letter_pdf = render_md(os.path.join(HERE, md), os.path.join(HERE, md.replace(".md", "_letter.pdf")), footer, letter_mode=True)
    esign(letter_pdf)
    spa = [stamp(normalize(p), "A") for p in PdfReader(SPA).pages]
    import fitz
    fd = fitz.open(letter_pdf)
    keep = [i for i, fp in enumerate(fd) if len(fp.get_text().strip()) > 80 or fp.get_images()]
    fd.close()
    pages = [normalize(p) for i, p in enumerate(PdfReader(letter_pdf).pages) if i in keep]
    pages += table_page("INDEX OF ANNEXES", footer.split("— ", 1)[-1],
                        [["<b>Annex</b>", "<b>Document</b>", "<b>Pages</b>"], ['"A"', ANNEX_DESC, len(spa)]],
                        [0.7 * inch, 5.2 * inch, 0.7 * inch])
    pages += spa
    w = PdfWriter()
    for p in pages:
        w.add_page(p)
    path = os.path.join(HERE, out_name)
    with open(path, "wb") as f:
        w.write(f)
    return path


def compress(path):
    """Re-encode scanned pages as JPEG (q75, <=1700 px wide); keep the signature PNG (alpha) as is."""
    import fitz
    d = fitz.open(path)
    done = set()
    for page in d:
        for img in page.get_images(full=True):
            xref, smask = img[0], img[1]
            if xref in done or smask:
                continue
            done.add(xref)
            pix = fitz.Pixmap(d, xref)
            if pix.alpha or pix.n > 4:
                continue
            if pix.width > 1700:
                pix = fitz.Pixmap(pix, 1700, int(pix.height * 1700 / pix.width), None)
            page.replace_image(xref, stream=pix.tobytes("jpeg", jpg_quality=75))
    tmp = path + ".tmp"
    d.save(tmp, garbage=4, deflate=True)
    d.close()
    os.replace(tmp, path)


if __name__ == "__main__":
    for md, footer, out in LETTERS:
        p = build(md, footer, out)
        compress(p)
        print(os.path.basename(p), len(PdfReader(p).pages), "pp,", round(os.path.getsize(p) / 1e6, 1), "MB")
