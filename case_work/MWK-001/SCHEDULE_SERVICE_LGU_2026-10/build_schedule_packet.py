#!/usr/bin/env python3
"""Schedule of Reasonable Compensation — LGU Mercedes service packet (Oct 2026), 8.5x13, 14 pt.
DRAFT — HELD for Jonathan's go. Not e-signed. Every page carries a DRAFT mark until the go.
  01 cover letter (Mayor; cc SB Presiding Officer, MLGOO) · 02 Schedule · annex index · A-1..A-4."""
import os, sys, io
from pypdf import PdfReader, PdfWriter

HERE = os.path.dirname(os.path.abspath(__file__))
MWK = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(MWK, "DENR_ASSESSOR_PACKET_2026-10"))
sys.path.insert(0, os.path.join(MWK, "OP_1321_packet"))
from build_op_packet import render_md, normalize, stamp  # noqa: E402
from build_packet import table_page  # noqa: E402
from reportlab.lib.units import inch  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

FOOTER = "Zschoche — Schedule of Reasonable Compensation, TCT No. T-32911 (municipal compound)"
ANNEXES = [
    ("A-1", "TCT No. T-32911, Lot 2-A, (LRA) Psd-221861 (corpus doc 2539)", "source/A1_TCT_T-32911.pdf"),
    ("A-2", "DENR records projection LMS-25-550: Lots 401, 403, 405 within Lot 2-A, 8,706 sq m (corpus doc 1070)", "source/A2_DENR_LMS-25-550.pdf"),
    ("A-3", "Municipality's Declaration of Real Property, ARP No. GR-2014-HH-07-005-00236 (₱943,810 / 973 sq m) (corpus doc 152)", "source/A3_LGU_ARP_00236.pdf"),
    ("A-4", "Special Power of Attorney, Patricia Keesey Zschoche to Jonathan Paul Zschoche, 18 May 2026 (apostilled)", "source/A4_SPA_apostilled.pdf"),
    ("A-5", "Municipality's Declaration of Real Property, ARP No. GR-2023-II-07-005-00213, Lot 401, 5,015 sq m, ₱8,324,900 (27 Jul 2023) (corpus doc 528, page 1 only)", "source/A5_LGU_ARP_00213_Lot401_2023.pdf"),
]
PAGES_ONLY = {"A-5": [0]}   # doc 528's scan also holds an unrelated Dilogo deed of donation: never annexed


def draft_mark(page):
    w, h = float(page.mediabox.width), float(page.mediabox.height)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    c.setFont("Helvetica-Bold", 10)
    c.setFillColorRGB(0.75, 0.1, 0.1)
    c.drawString(36, h - 22, "DRAFT — HELD FOR JONATHAN'S GO — NOT FOR SERVICE")
    c.save()
    buf.seek(0)
    page.merge_page(PdfReader(buf).pages[0])
    return page


def main():
    pages = []
    for md in ("01_Cover_Letter_Mayor_Schedule.md", "02_Schedule_of_Reasonable_Compensation.md"):
        pdf = render_md(os.path.join(HERE, md), os.path.join(HERE, md.replace(".md", ".pdf")), FOOTER, letter_mode=md.startswith("01"))
        pages += [normalize(p) for p in PdfReader(pdf).pages if (p.extract_text() or "").strip()]
    annex_pages, rows = [], [["<b>Annex</b>", "<b>Document</b>", "<b>Pages</b>"]]
    for label, desc, path in ANNEXES:
        src = PdfReader(os.path.join(HERE, path)).pages
        ap = [stamp(normalize(src[i]), label) for i in PAGES_ONLY.get(label, range(len(src)))]
        rows.append([f'"{label}"', desc, len(ap)])
        annex_pages += ap
    pages += table_page("INDEX OF ANNEXES", FOOTER.split("— ", 1)[-1], rows, [0.7 * inch, 5.2 * inch, 0.7 * inch])
    pages += annex_pages
    w = PdfWriter()
    for p in pages:
        w.add_page(draft_mark(p))
    out = os.path.join(HERE, "MWK-001_SCHEDULE_LGU_PACKET_DRAFT_8.5x13.pdf")
    with open(out, "wb") as f:
        w.write(f)
    print(out, len(pages), "pages")


if __name__ == "__main__":
    main()
