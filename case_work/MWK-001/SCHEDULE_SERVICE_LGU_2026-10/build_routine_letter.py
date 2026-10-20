#!/usr/bin/env python3
"""Routine drip letter (Rope 1), LGU Mercedes, compound record request (Oct 2026), 8.5x13, 14 pt.
DRAFT, HELD for Jonathan's go. Not e-signed. One small ask; the only annex is the SPA (authority).
The Schedule of Reasonable Compensation stays in HELD_LATER_RUNG/ until the record supports a later rung."""
import os, sys, io
from pypdf import PdfReader, PdfWriter

HERE = os.path.dirname(os.path.abspath(__file__))
MWK = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(MWK, "DENR_ASSESSOR_PACKET_2026-10"))
sys.path.insert(0, os.path.join(MWK, "OP_1321_packet"))
from build_op_packet import render_md, normalize, stamp  # noqa: E402
from build_schedule_packet import draft_mark  # noqa: E402

FOOTER = "Zschoche — Particulars of the documents cited in the letter of 21 May 2025"
MD = "01_Routine_Request_Mayor_Compound_Record.md"


def main():
    pdf = render_md(os.path.join(HERE, MD), os.path.join(HERE, MD.replace(".md", ".pdf")), FOOTER, letter_mode=True)
    pages = [normalize(p) for p in PdfReader(pdf).pages if (p.extract_text() or "").strip()]
    pages += [stamp(normalize(p), "A") for p in PdfReader(os.path.join(HERE, "source", "A4_SPA_apostilled.pdf")).pages]
    w = PdfWriter()
    for p in pages:
        w.add_page(draft_mark(p))
    out = os.path.join(HERE, "MWK-001_ROUTINE_REQUEST_COMPOUND_RECORD_DRAFT_8.5x13.pdf")
    with open(out, "wb") as f:
        w.write(f)
    os.remove(pdf)
    print(out, len(pages), "pages")


if __name__ == "__main__":
    main()
