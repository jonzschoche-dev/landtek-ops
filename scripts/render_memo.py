#!/usr/bin/env python3
"""render_memo.py — render a hand-authored markdown memo to PDF and send to Telegram. $0.

For matters/outputs authored directly (frontier-reasoned) rather than via the case_memo DB pipeline —
e.g. a new/thin matter where a careful human-grade read beats the local generator. Supports basic
markdown: #/##/### headings, **bold**, `code`, - bullets, numbered lists, | table rows |, --- rules,
and *italic note* lines.

  python3 scripts/render_memo.py memo.md "Caption text" --send
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
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

CHAT = "6513067717"


def _tok():
    for line in open("/root/landtek/.env"):
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            return line.split("=", 1)[1].strip()
    return None


def _inline(s):
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", s)
    return s


def render(md_path, out_path):
    s = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=s["Heading1"], fontSize=15, spaceAfter=3)
    h2 = ParagraphStyle("h2", parent=s["Heading2"], fontSize=12, spaceBefore=9, spaceAfter=3, textColor=colors.HexColor("#1e293b"))
    h3 = ParagraphStyle("h3", parent=s["Heading3"], fontSize=10.5, spaceBefore=6, spaceAfter=2)
    bdy = ParagraphStyle("bdy", parent=s["BodyText"], fontSize=9.5, leading=13)
    note = ParagraphStyle("note", parent=bdy, fontSize=8, textColor=colors.HexColor("#6b7280"))
    f = []
    for raw in open(md_path):
        t = raw.rstrip("\n").strip()
        if not t:
            f.append(Spacer(1, 4)); continue
        if t.startswith("# "):
            f.append(Paragraph(_inline(t[2:]), h1))
        elif t.startswith("## "):
            f.append(Paragraph(_inline(t[3:]), h2))
        elif t.startswith("### "):
            f.append(Paragraph(_inline(t[4:]), h3))
        elif t.startswith("---"):
            f.append(Spacer(1, 6))
        elif t.startswith("|"):
            cells = [c.strip() for c in t.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue   # markdown separator row
            f.append(Paragraph(" &nbsp;|&nbsp; ".join(_inline(c) for c in cells), bdy))
        elif t.startswith(("- ", "* ")):
            f.append(Paragraph("&bull; " + _inline(t[2:]), bdy))
        elif re.match(r"\d+\. ", t):
            f.append(Paragraph(_inline(t), bdy))
        elif t.startswith("*") and t.endswith("*"):
            f.append(Paragraph(_inline(t.strip("*")), note))
        else:
            f.append(Paragraph(_inline(t), bdy))
    SimpleDocTemplate(out_path, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch).build(f)


def main():
    md = sys.argv[1]
    cap = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else "Memo"
    out = "/tmp/" + os.path.basename(md).replace(".md", "") + ".pdf"
    render(md, out)
    print(f"[render] {out}")
    if "--send" in sys.argv:
        tok = _tok()
        r = subprocess.run(["curl", "-s", "-F", f"chat_id={CHAT}", "-F", f"caption={cap}",
                            "-F", f"document=@{out}", f"https://api.telegram.org/bot{tok}/sendDocument"],
                           capture_output=True, text=True)
        print("[send] sent ✓" if '"ok":true' in r.stdout else f"[send] FAIL {r.stdout[:160]}")


if __name__ == "__main__":
    main()
