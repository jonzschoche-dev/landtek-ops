#!/usr/bin/env python3
"""finalize_docx.py — the FINALIZER. Turn a grounded markdown dossier/brief into a professional Word
document. Separates content (the grounded .md = source of truth) from presentation. $0, local (python-docx).

Produces: a title page, a Table of Contents field, Word heading styles, properly styled tables (markdown
pipe-tables → shaded-header Word tables), a footer (CONFIDENTIAL — Prepared by LandTek · Page X of Y),
and clean typography. Editable by counsel. Front matter is everything before the first '---'; the body
(with the TOC) follows.

  python3 scripts/finalize_docx.py in.md out.docx
"""
import re
import sys

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

CONTENT_W = 6.5  # inches, US Letter @ 1" margins
NARROW = {"status", "exhibit", "date", "¶", "support"}


def _field(paragraph, instr, placeholder=""):
    r = paragraph.add_run()
    b = OxmlElement("w:fldChar"); b.set(qn("w:fldCharType"), "begin"); r._r.append(b)
    i = OxmlElement("w:instrText"); i.set(qn("xml:space"), "preserve"); i.text = instr; r._r.append(i)
    s = OxmlElement("w:fldChar"); s.set(qn("w:fldCharType"), "separate"); r._r.append(s)
    if placeholder:
        t = OxmlElement("w:t"); t.text = placeholder; r._r.append(t)
    e = OxmlElement("w:fldChar"); e.set(qn("w:fldCharType"), "end"); r._r.append(e)


def _inline(paragraph, text, base_size=None, color=None):
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 (\2)", text)   # links → text (url)
    for part in re.split(r"(\*\*.+?\*\*|`.+?`)", text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2]); run.bold = True
        elif part.startswith("`") and part.endswith("`"):
            run = paragraph.add_run(part[1:-1]); run.font.name = "Consolas"
        else:
            run = paragraph.add_run(part)
        if base_size:
            run.font.size = Pt(base_size)
        if color:
            run.font.color.rgb = color


def _shade(cell, fill):
    shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(shd)


def _widths(headers):
    cells = len(headers)
    narrow_idx = [i for i, h in enumerate(headers) if h.strip().lower() in NARROW]
    if not narrow_idx or len(narrow_idx) == cells:
        return [CONTENT_W / cells] * cells
    nw = 0.95
    rest = (CONTENT_W - nw * len(narrow_idx)) / (cells - len(narrow_idx))
    return [nw if i in narrow_idx else rest for i in range(cells)]


def _table(doc, rows):
    headers = [c.strip() for c in rows[0]]
    ncols = len(headers)
    t = doc.add_table(rows=len(rows), cols=ncols)
    t.style = "Table Grid"
    t.alignment = WD_ALIGN_PARAGRAPH.LEFT
    t.autofit = False
    widths = _widths(headers)
    for ri, row in enumerate(rows):
        for ci in range(ncols):
            cell = t.cell(ri, ci)
            cell.width = Inches(widths[ci])
            p = cell.paragraphs[0]; p.text = ""
            _inline(p, row[ci].strip() if ci < len(row) else "", base_size=8.5)
            if ri == 0:
                _shade(cell, "334155")
                for run in p.runs:
                    run.bold = True; run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    doc.add_paragraph()


def _toc(doc):
    doc.add_heading("Contents", level=1)
    p = doc.add_paragraph()
    _field(p, 'TOC \\o "1-2" \\h \\z \\u', "Open in Word and choose “Update Field” to build the table of contents.")
    doc.add_page_break()


def build(md_path, out_path):
    doc = Document()
    n = doc.styles["Normal"]; n.font.name = "Calibri"; n.font.size = Pt(10.5)
    for sec in doc.sections:
        sec.top_margin = sec.bottom_margin = sec.left_margin = sec.right_margin = Inches(1)
    # footer: CONFIDENTIAL · Page X of Y
    fp = doc.sections[0].footer.paragraphs[0]; fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = fp.add_run("CONFIDENTIAL — Prepared by LandTek for counsel review      Page ")
    r.font.size = Pt(8); r.font.color.rgb = RGBColor(0x80, 0x80, 0x80)
    _field(fp, "PAGE"); run = fp.add_run(" of "); run.font.size = Pt(8); _field(fp, "NUMPAGES")
    for rr in fp.runs:
        rr.font.size = Pt(8); rr.font.color.rgb = RGBColor(0x80, 0x80, 0x80)

    lines = open(md_path).read().splitlines()
    # split front matter (before first '---') from body
    div = next((i for i, l in enumerate(lines) if l.strip() == "---"), None)
    front = lines[:div] if div is not None else lines[:1]
    body = lines[div + 1:] if div is not None else lines[1:]

    # ── title page ──
    first = True
    for raw in front:
        t = raw.strip()
        if not t:
            continue
        if t.startswith("# ") and first:
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(t[2:]); run.bold = True; run.font.size = Pt(22); run.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)
            first = False
        elif t.startswith("## "):
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _inline(p, t[3:], base_size=13, color=RGBColor(0x33, 0x41, 0x55))
        elif t.startswith(("# ", "### ")):
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; _inline(p, re.sub(r"^#+ ", "", t), base_size=12)
        else:
            p = doc.add_paragraph(); _inline(p, t)
    doc.add_page_break()
    _toc(doc)

    # ── body ──
    rows = []
    def flush():
        if rows:
            _table(doc, rows); rows.clear()
    for raw in body:
        t = raw.rstrip()
        st = t.strip()
        if st.startswith("|"):
            cells = [c.strip() for c in st.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            rows.append(cells); continue
        flush()
        if not st:
            continue
        if st.startswith("## "):
            doc.add_heading(re.sub(r"\*\*", "", st[3:]), level=1)
        elif st.startswith("### "):
            doc.add_heading(re.sub(r"\*\*", "", st[4:]), level=2)
        elif st.startswith("# "):
            doc.add_heading(re.sub(r"\*\*", "", st[2:]), level=1)
        elif st.startswith(">"):
            p = doc.add_paragraph(style="Intense Quote"); _inline(p, st.lstrip("> ").strip())
        elif st.startswith(("- ", "* ")):
            p = doc.add_paragraph(style="List Bullet"); _inline(p, st[2:])
        elif re.match(r"\d+\.\s", st):
            p = doc.add_paragraph(style="List Number"); _inline(p, re.sub(r"^\d+\.\s", "", st))
        elif st == "---":
            continue
        else:
            p = doc.add_paragraph(); _inline(p, st)
    flush()
    doc.save(out_path)


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: finalize_docx.py in.md out.docx")
    build(sys.argv[1], sys.argv[2])
    print(f"[finalize] {sys.argv[2]}")


if __name__ == "__main__":
    main()
