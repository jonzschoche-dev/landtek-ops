#!/usr/bin/env python3
"""CV6839-LBP-BALANCE step 1: e-signed letter + SPA (Annex A) for the e-mail draft.
Jonathan's go 20 Oct 2026: "make the draft from jonzschoche@gmail.com". Builds the PDF only; never sends."""
import os, sys
from pypdf import PdfReader, PdfWriter
HERE = os.path.dirname(os.path.abspath(__file__))
MWK = os.path.join(HERE, "..", "..", "MWK-001")
sys.path.insert(0, os.path.join(MWK, "DENR_ASSESSOR_PACKET_2026-10"))
sys.path.insert(0, os.path.join(MWK, "OP_1321_packet"))
from build_op_packet import render_md, normalize, stamp  # noqa
import build_packet  # noqa
import fitz  # noqa


def esign(pdf_path):
    """Same placement as build_packet.esign, but the drip close reads 'Respectfully yours,'."""
    doc = fitz.open(pdf_path)
    for page in doc:
        hits = page.search_for("JONATHAN PAUL ZSCHOCHE")
        resp = page.search_for("Respectfully yours,") or page.search_for("Respectfully,")
        if hits and resp:
            name, r = hits[-1], resp[-1]
            h = name.y0 - r.y1 + 6
            w = h * 2383 / 1266
            box = fitz.Rect(name.x0 - 4, name.y0 - h + 4, name.x0 - 4 + w, name.y0 + 4)
            page.insert_image(box, filename=build_packet.SIG_IMG, overlay=True)
            doc.save(pdf_path + '.tmp'); doc.close(); os.replace(pdf_path + '.tmp', pdf_path)
            return True
    raise RuntimeError('no signature block')
FOOTER = "Zschoche — CV 6839 titles: release status and per-heir release requirements"
tmp = render_md(os.path.join(HERE, "step1_letter.md"), os.path.join(HERE, "_letter.pdf"), FOOTER, letter_mode=True)
esign(tmp)
pages = [normalize(p) for p in PdfReader(tmp).pages if (p.extract_text() or "").strip()]
pages += [stamp(normalize(p), "A") for p in PdfReader(os.path.join(MWK, "SCHEDULE_SERVICE_LGU_2026-10", "source", "A4_SPA_apostilled.pdf")).pages]
w = PdfWriter()
for p in pages:
    w.add_page(p)
out = os.path.join(HERE, "Zschoche_Letter_LandBank_FSSC5_CV6839_20Oct2026.pdf")
with open(out, "wb") as f:
    w.write(f)
os.remove(tmp)
print(out, len(pages), "pages")
