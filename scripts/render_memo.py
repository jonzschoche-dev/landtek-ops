#!/usr/bin/env python3
"""render_memo.py — render a markdown document to a PROFESSIONALLY-FORMATTED PDF. $0.

For frontier-authored outputs (briefs, dossiers, package front matter). Professional form:
a title block, a running footer (prepared-by · CONFIDENTIAL · Page X of Y), REAL tables (grid,
header row), clickable [links](url), and consistent typography. Markdown supported: #/##/### headings,
**bold**, `code`, [text](url), - bullets, numbered lists, | tables |, --- rules, *italic notes*.

  python3 scripts/render_memo.py memo.md "Caption" [--send] [--footer "Prepared by …"]
"""
import html
import os
import re
import subprocess
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

CHAT = "6513067717"
DEFAULT_FOOTER = "Prepared by LandTek — for counsel review"
MARGIN = 0.75 * inch


def _tok():
    for line in open("/root/landtek/.env"):
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            return line.split("=", 1)[1].strip()
    return None


def _inline(s):
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"<a href='\2' color='#2563eb'>\1</a>", s)
    return s


def _numbered_canvas(footer_left):
    class C(_canvas.Canvas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k); self._saved = []
        def showPage(self):
            self._saved.append(dict(self.__dict__)); self._startPage()
        def save(self):
            total = len(self._saved)
            for st in self._saved:
                self.__dict__.update(st); self._foot(total); super().showPage()
            super().save()
        def _foot(self, total):
            y = 0.45 * inch
            self.setStrokeColor(colors.HexColor("#e5e7eb"))
            self.line(MARGIN, y + 11, letter[0] - MARGIN, y + 11)
            self.setFont("Helvetica", 7); self.setFillColor(colors.HexColor("#9ca3af"))
            self.drawString(MARGIN, y, footer_left)
            self.drawCentredString(letter[0] / 2, y, "CONFIDENTIAL")
            self.drawRightString(letter[0] - MARGIN, y, f"Page {self._pageNumber} of {total}")
    return C


def render(md_path, out_path, footer_left=DEFAULT_FOOTER):
    s = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=s["Title"], fontSize=16, leading=20, spaceAfter=6, textColor=colors.HexColor("#0f172a"))
    h2 = ParagraphStyle("h2", parent=s["Heading2"], fontSize=12, spaceBefore=11, spaceAfter=3, textColor=colors.HexColor("#1e293b"))
    h3 = ParagraphStyle("h3", parent=s["Heading3"], fontSize=10.5, spaceBefore=6, spaceAfter=2, textColor=colors.HexColor("#374151"))
    bdy = ParagraphStyle("bdy", parent=s["BodyText"], fontSize=9.5, leading=13.5, spaceAfter=2)
    note = ParagraphStyle("note", parent=bdy, fontSize=8, textColor=colors.HexColor("#6b7280"))
    cell = ParagraphStyle("cell", parent=bdy, fontSize=8.5, leading=11.5, spaceAfter=0)
    cellh = ParagraphStyle("cellh", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")
    flow, rows = [], []
    seen_title = [False]

    def flush_table():
        if not rows:
            return
        ncols = max(len(r) for r in rows)
        norm = [[r[i] if i < len(r) else "" for i in range(ncols)] for r in rows]
        data = [[Paragraph(_inline(c), cellh if ri == 0 else cell) for c in row] for ri, row in enumerate(norm)]
        w = (letter[0] - 2 * MARGIN) / ncols
        tbl = Table(data, colWidths=[w] * ncols, hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        flow.append(tbl); flow.append(Spacer(1, 7)); rows.clear()

    for raw in open(md_path):
        t = raw.rstrip("\n").strip()
        if t.startswith("|"):
            cells = [c.strip() for c in t.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            rows.append(cells); continue
        flush_table()
        if not t or t.startswith("# #") or t.startswith("#!"):   # blank or a comment-ish line
            if not t:
                flow.append(Spacer(1, 4))
            continue
        if t.startswith("# "):
            flow.append(Paragraph(_inline(t[2:]), title if not seen_title[0] else h2)); seen_title[0] = True
        elif t.startswith("## "):
            flow.append(Paragraph(_inline(t[3:]), h2))
        elif t.startswith("### "):
            flow.append(Paragraph(_inline(t[4:]), h3))
        elif t.startswith("---"):
            flow.append(Spacer(1, 6))
        elif t.startswith(("- ", "* ")):
            flow.append(Paragraph("&bull;&nbsp; " + _inline(t[2:]), bdy))
        elif re.match(r"\d+\. ", t):
            flow.append(Paragraph(_inline(t), bdy))
        elif t.startswith("*") and t.endswith("*") and len(t) > 2:
            flow.append(Paragraph(_inline(t.strip("*")), note))
        else:
            flow.append(Paragraph(_inline(t), bdy))
    flush_table()
    SimpleDocTemplate(out_path, pagesize=letter, topMargin=0.7 * inch, bottomMargin=0.75 * inch,
                      leftMargin=MARGIN, rightMargin=MARGIN).build(flow, canvasmaker=_numbered_canvas(footer_left))


def main():
    md = sys.argv[1]
    cap = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else "Memo"
    footer = sys.argv[sys.argv.index("--footer") + 1] if "--footer" in sys.argv else DEFAULT_FOOTER
    out = "/tmp/" + os.path.basename(md).replace(".md", "") + ".pdf"
    render(md, out, footer)
    print(f"[render] {out}")
    if "--send" in sys.argv:
        tok = _tok()
        r = subprocess.run(["curl", "-s", "-F", f"chat_id={CHAT}", "-F", f"caption={cap}",
                            "-F", f"document=@{out}", f"https://api.telegram.org/bot{tok}/sendDocument"],
                           capture_output=True, text=True)
        print("[send] sent ✓" if '"ok":true' in r.stdout else f"[send] FAIL {r.stdout[:160]}")


if __name__ == "__main__":
    main()
