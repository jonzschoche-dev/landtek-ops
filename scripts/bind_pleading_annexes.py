#!/usr/bin/env python3
"""Bind a rendered pleading PDF with its annexes into one filing binder.

Usage:  python3 scripts/bind_pleading_annexes.py <binder.json>

binder.json:
{
  "pleading": "out/PETITION.pdf",              # rendered by render_pleading_pdf.py
  "output":   "out/PETITION_bound.pdf",
  "footer":   "short running title",
  "annexes": [
    {"tab": "A", "title": "...", "note": "...", "files": ["path.pdf", ...]},
    ...
  ]
}
Paths are relative to the json's directory unless absolute. A tab sheet is
generated for every annex (same 13" x 8.5" page as the pleading); documents
listed in "files" follow it as-is. An annex with no files gets a tab sheet
that says what is to be inserted and where it comes from - never a blank.
Every page of the binder is stamped bottom-right with the annex tab and a
running page number so the bound copy can be cited by page.
"""
import json
import sys
from pathlib import Path

import pymupdf
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

PAGE = (8.5 * inch, 13.0 * inch)  # A.M. 11-9-4-SC long bond
L, T, R, B = 1.5 * inch, 1.2 * inch, 1.0 * inch, 1.0 * inch
FONT, FONT_B = "Times-Roman", "Times-Bold"


def wrap(c, text, font, size, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if c.stringWidth(t, font, size) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def tab_sheet(path, tab, title, note, files_desc):
    c = canvas.Canvas(str(path), pagesize=PAGE)
    w = PAGE[0] - L - R
    y = PAGE[1] - T - 1.2 * inch
    c.setFont(FONT_B, 28)
    c.drawCentredString(PAGE[0] / 2, y, f'ANNEX "{tab}"')
    y -= 0.6 * inch
    c.setFont(FONT_B, 14)
    for ln in wrap(c, title, FONT_B, 14, w):
        c.drawCentredString(PAGE[0] / 2, y, ln)
        y -= 0.28 * inch
    y -= 0.3 * inch
    c.setFont(FONT, 12)
    for para in [note] + files_desc:
        if not para:
            continue
        for ln in wrap(c, para, FONT, 12, w):
            c.drawString(L, y, ln)
            y -= 0.22 * inch
        y -= 0.16 * inch
    c.showPage()
    c.save()


def main(json_path):
    jp = Path(json_path).resolve()
    base = jp.parent
    job = json.loads(jp.read_text())
    rel = lambda p: (Path(p) if Path(p).is_absolute() else base / p)
    out = rel(job["output"])
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.parent / "_tabs"
    tmp.mkdir(exist_ok=True)

    binder = pymupdf.open()
    labels = []  # (tab, first_page_index) for stamping
    pl = pymupdf.open(rel(job["pleading"]))
    binder.insert_pdf(pl)
    labels.append(("", 0))
    for ax in job["annexes"]:
        tab = ax["tab"]
        files = [rel(f) for f in ax.get("files", [])]
        desc = []
        for f, d in zip(files, ax.get("files_desc", [])):
            desc.append(d)
        if not files:
            desc.append(ax.get("missing", "Not yet in hand; to be inserted before filing."))
        ts = tmp / f"tab_{tab.replace('-', '_')}.pdf"
        tab_sheet(ts, tab, ax["title"], ax.get("note", ""), desc)
        labels.append((tab, len(binder)))
        binder.insert_pdf(pymupdf.open(ts))
        for f in files:
            binder.insert_pdf(pymupdf.open(f))

    # stamp every page: "Annex X · binder p. N of M"
    n = len(binder)
    cur = ""
    starts = {i: t for t, i in labels}
    for i, page in enumerate(binder):
        if i in starts:
            cur = starts[i]
        text = (f'Annex "{cur}"  ·  ' if cur else "Petition  ·  ") + f"binder p. {i + 1} of {n}"
        r = page.rect
        page.insert_text((r.x1 - 2.6 * inch, r.y1 - 0.35 * inch), text,
                         fontsize=8, fontname="helv", color=(0.3, 0.3, 0.3))
    binder.set_metadata({"title": job.get("footer", ""), "producer": "landtek bind_pleading_annexes"})
    binder.save(str(out), garbage=3, deflate=True)
    print(f"wrote {out}  {n} pages  {out.stat().st_size // 1024} KB")
    for t, i in labels:
        print(f"  {t or 'Petition':>4}  p.{i + 1}")


if __name__ == "__main__":
    main(sys.argv[1])
