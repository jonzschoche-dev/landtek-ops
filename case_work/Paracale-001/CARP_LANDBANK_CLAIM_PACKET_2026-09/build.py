#!/usr/bin/env python3
"""Bound review packet: Inocalla CARP / Land Bank claims. Runs on the VPS (source scans live in uploads/).

  python3 build.py   ->  INOCALLA_CARP_LANDBANK_PACKET_2026-09-22.pdf
"""
import os
import re
import subprocess
import tempfile

import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
U = "/root/landtek/uploads"
SRC = {
    670: f"{U}/Unclassified/670_Scan_Mar_21__2026_at_4.42_PM.pdf",
    663: f"{U}/Unclassified/663_Scan_Mar_21__2026_at_5.42_PM.pdf",
    666: f"{U}/Unclassified/666_Scan_Mar_21__2026_at_5.02_PM.pdf",
    665: f"{U}/Unclassified/665_Scan_Mar_21__2026_at_5.09_PM.pdf",
    497: f"{U}/scannerpro/1XKtKSgNCAFDZHrYP0FjM4-7d-FtiNZ5E.pdf",
    669: f"{U}/Unclassified/669_Scan_Mar_21__2026_at_4.44_PM.pdf",
    1611: f"{U}/drive_new_4043064952650545.pdf",
}
# (tab, title, doc, 1-based pages)
EXHIBITS = [
    ("A-1", "Land Bank Summary of Land Transfer Claim 05-CA-99-1788 (TCT T-1722) + payment-release checklist", 670, [2, 3, 4]),
    ("A-2", "Land Bank AOC-V approval letters, 16 Sep 2019 (claims 05-CA-99-1787 and 1788)", 666, [8, 9, 10, 11]),
    ("A-3", "Land Bank AOC-V letter 10 May 2018 + claim-folder copies / checklists", 663, [18, 19, 20, 21, 22, 24, 25, 26, 28, 29, 30]),
    ("B-1", "DAR MARO Certification, 16 May 2012 (T-1722 under compulsory acquisition)", 666, [7]),
    ("B-2", "DAR MARPO letter to Municipal Treasurer, 16 Sep 2019 (CLOA list, tax status)", 663, [5]),
    ("B-3", "DAR Secretary Order EXC-0804-156, 14 Apr 2008 (202.10 ha excluded; 56.76 ha directed into CARP)", 1611, [9, 10, 11, 12, 13, 14]),
    ("C-1", "TCT T-1722 (Lots 1 & 2, Plan H-36999), Vicente L. Inocalla", 665, [1, 2, 3, 4, 5]),
    ("C-2", "TCT T-1827, LRA certified true copy", 497, [1, 2, 3, 4]),
    ("C-3", "CLOA titles to farmer-beneficiaries, survey plans, heirs' landholding inventory", 669, list(range(2, 24))),
    ("C-4", "Titles marked 'Cancelled' supplied with the family claim file", 663, [31, 32, 33] + list(range(35, 48))),
    ("D", "Heirs' documents gathered for Land Bank (checklist, IDs, birth/death certificates, RPT statement)", 663, [1, 3, 4] + list(range(6, 18)) + [34]),
]
DPI, QUALITY = 110, 55
PW, PH, M = 612, 936, 18   # 8.5 x 13 in (folio), portrait, 0.25in margin


def osd_rotation(pix):
    """Degrees (clockwise) Tesseract says the page needs, or 0 if not confident."""
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        pix.save(f.name)
        r = subprocess.run(["tesseract", f.name, "-", "--psm", "0"], capture_output=True, text=True)
    out = r.stdout + r.stderr
    rot = re.search(r"Rotate: (\d+)", out)
    conf = re.search(r"Orientation confidence: ([\d.]+)", out)
    if rot and conf and float(conf.group(1)) >= 1.0:
        return int(rot.group(1))
    return 0


OVERRIDE = {(663, 28): 270, (669, 4): 270, (663, 4): 90}   # (doc, page) -> final clockwise degrees; OSD misread these (visually checked)
LOG = []


def divider(out, tab, title, doc, pages):
    p = out.new_page(width=PW, height=PH)
    p.insert_text((72, 300), f"EXHIBIT {tab}", fontsize=30, fontname="hebo")
    p.insert_textbox(fitz.Rect(72, 330, 540, 460), title, fontsize=14, fontname="helv")
    p.insert_text((72, 490), f"Source: LandTek corpus document {doc}, scan pages {pages[0]}-{pages[-1]} ({len(pages)} pp.)",
                  fontsize=9, fontname="helv", color=(0.35, 0.35, 0.35))


def main():
    memo_pdf = os.path.join(HERE, "_memo.pdf")
    subprocess.run(["weasyprint", os.path.join(HERE, "memo.html"), memo_pdf], check=True)
    out = fitz.open()
    out.insert_pdf(fitz.open(memo_pdf))
    toc = [[1, "Cover memo", 1]]
    cache = {}
    for tab, title, doc, pages in EXHIBITS:
        src = cache.setdefault(doc, fitz.open(SRC[doc]))
        divider(out, tab, title, doc, pages)
        toc.append([1, f"Exhibit {tab} - {title}", len(out)])
        for n in pages:
            sp = src[n - 1]
            pix = sp.get_pixmap(dpi=DPI)
            cw = OVERRIDE.get((doc, n))
            if cw is None:
                cw = osd_rotation(sp.get_pixmap(dpi=150))
            w, h = (pix.height, pix.width) if cw in (90, 270) else (pix.width, pix.height)
            if w > h and (doc, n) not in OVERRIDE:   # true landscape content -> turn to portrait, top toward the binding
                cw = (cw + 270) % 360
                w, h = h, w
            s_ = min((PW - 2 * M) / w, (PH - 2 * M) / h)
            iw, ih = w * s_, h * s_
            rect = fitz.Rect((PW - iw) / 2, (PH - ih) / 2, (PW + iw) / 2, (PH + ih) / 2)
            np_ = out.new_page(width=PW, height=PH)
            # PyMuPDF rotate is counter-clockwise; Tesseract reports clockwise correction
            np_.insert_image(rect, stream=pix.tobytes("jpeg", jpg_quality=QUALITY), rotate=(360 - cw) % 360)
            LOG.append((tab, doc, n, cw))
    out.set_toc(toc)
    for row in LOG:
        print("rot", *row)
    out.set_metadata({"title": "Inocalla CARP / Land Bank claims - review packet", "author": "LandTek"})
    dst = os.path.join(HERE, "INOCALLA_CARP_LANDBANK_PACKET_2026-09-22.pdf")
    out.save(dst, garbage=4, deflate=True)
    os.remove(memo_pdf)
    print(dst, len(out), "pages", round(os.path.getsize(dst) / 1e6, 1), "MB")


if __name__ == "__main__":
    main()
