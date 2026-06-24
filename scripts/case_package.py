#!/usr/bin/env python3
"""case_package.py — counsel-ready PACKAGE for EXTERNAL delivery. $0, local (reportlab + PyMuPDF).

A brief (front matter) + the CORE documents bound in as labeled exhibits + an Index of Supporting
Documents listing every other relevant document as an OPEN public link (leo.hayuma.org/files/c/<id>,
served unauthenticated via nginx). One PDF you can send to outside counsel: the essentials are in hand,
the rest are one click away.

  python3 scripts/case_package.py MWK-ARTA-1891 --brief 1891_output/brief_1891.md \
          --core 708,709,700,724,1086,1195 [--send] [--dpi 110] [--quality 45]
"""
import html
import os
import re
import subprocess
import sys

import fitz  # PyMuPDF
import psycopg2
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from humanize import doc_titles as _doc_titles

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
PUBLIC = os.environ.get("LEO_PUBLIC_BASE_URL", "https://leo.hayuma.org")
CHAT = "6513067717"
EXLAB = "ABCDEFGHIJKLMN"


def _tok():
    for line in open("/root/landtek/.env"):
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            return line.split("=", 1)[1].strip()
    return None


def _e(s):
    return html.escape(str(s or ""))


def _rank(fn):
    f = (fn or "").lower()
    if re.search(r"complaint|petition|manifestation|affidavit|motion|answer", f):
        return 0
    if re.search(r"annex|minutes|resolution|hearing|record|exhibit|certificat", f):
        return 1
    if re.search(r"referral|notice|indorsement|nor-", f):
        return 2
    if re.search(r"letter|response|order|reply|demand|spa|power of attorney", f):
        return 3
    return 4


def _gather(mc, core_ids):
    c = psycopg2.connect(DSN); cur = c.cursor()
    cur.execute("SELECT coalesce(title,''), coalesce(docket_number,''), coalesce(forum,court_or_agency,'') FROM matters WHERE matter_code=%s", (mc,))
    mt, docket, forum = cur.fetchone() or ("", "", "")
    DT = _doc_titles(cur, mc)
    cur.execute("SELECT doc_id FROM matter_relevance WHERE focal_matter=%s AND tier='OFF-PROFILE'", (mc,))
    off = {r[0] for r in cur.fetchall()}
    cur.execute("""SELECT d.id, coalesce(d.original_filename,d.smart_filename,'?'), d.doc_date, d.file_path,
                   (SELECT count(*) FROM matter_facts f WHERE f.matter_code=%s AND f.source_id=d.id::text
                      AND f.provenance_level='verified') nf,
                   length(coalesce(d.extracted_text,'')) tl, coalesce(d.extracted_text,'')
                   FROM documents d
                   WHERE d.matter_code=%s OR d.id IN (SELECT doc_id FROM document_matter_links WHERE matter_code=%s)
                   ORDER BY d.id""", (mc, mc, mc))
    core, related = [], []
    for did, fn, dd, fp, nf, tl, txt in cur.fetchall():
        if did in off:
            continue
        title = DT.get(did, fn)
        if did in core_ids:
            core.append((did, title, dd, fp, txt))
        else:
            if tl < 40 and nf == 0:                  # image.png / zip / empty — not a usable exhibit
                continue
            if nf == 0 and _rank(fn) > 3:            # fact-less peripheral
                continue
            related.append((did, title, str(dd or ""), nf))
    c.close()
    core.sort(key=lambda r: core_ids.index(r[0]))
    related.sort(key=lambda r: (_rank(r[1]), -r[3], r[0]))
    return mt, docket, forum, core, related


def _support_index(path, mt, core, related):
    s = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=s["Heading2"], fontSize=13, spaceAfter=4, textColor=colors.HexColor("#111827"))
    body = ParagraphStyle("b", parent=s["BodyText"], fontSize=9.5, leading=14)
    note = ParagraphStyle("n", parent=body, fontSize=8, textColor=colors.HexColor("#6b7280"))
    f = [Paragraph("Index of Supporting Documents", h),
         Paragraph("The core documents are bound as Exhibits A–%s, immediately following this index. "
                   "The documents below are part of the record and are available online (view-only):"
                   % EXLAB[len(core) - 1], note),
         Spacer(1, 8)]
    for did, title, dd, nf in related:
        url = f"{PUBLIC}/files/c/{did}"
        meta = f" <font size='8' color='#6b7280'>· {dd}</font>" if dd else ""
        f.append(Paragraph(f"&bull; {_e(title)}{meta} &nbsp; <a href='{url}'><font color='#2563eb'>[open ↗]</font></a>", body))
        f.append(Paragraph(f"&nbsp;&nbsp;&nbsp;<font size='7.5' color='#9ca3af'>{_e(url)}</font>", note))
    f.append(Spacer(1, 8))
    f.append(Paragraph("Links resolve to a view-only copy of each document. If a link does not open, the "
                       "document is available on request.", note))
    SimpleDocTemplate(path, pagesize=letter, topMargin=0.8 * inch, bottomMargin=0.7 * inch).build(f)


def _text_exhibit(path, title, text):
    s = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=s["Heading3"], fontSize=10.5, spaceAfter=6)
    mono = ParagraphStyle("m", parent=s["BodyText"], fontSize=8.5, leading=12)
    f = [Paragraph(_e(title), h), Spacer(1, 4)]
    for para in re.split(r"\n\s*\n", text)[:60]:
        p = _e(para.strip()).replace("\n", "<br/>")
        if p:
            f.append(Paragraph(p, mono)); f.append(Spacer(1, 4))
    SimpleDocTemplate(path, pagesize=letter, topMargin=0.8 * inch, bottomMargin=0.7 * inch).build(f)


def _divider(out, label, subtitle):
    pg = out.new_page(width=612, height=792)
    pg.draw_rect(fitz.Rect(60, 250, 552, 420), color=(0.82, 0.85, 0.9), width=1)
    pg.insert_text((84, 320), label, fontsize=30, fontname="hebo")
    line, y = "", 360
    for w in subtitle.split():
        if len(line) + len(w) > 58:
            pg.insert_text((84, y), line, fontsize=12, fontname="helv"); y += 18; line = ""
        line += w + " "
    if line:
        pg.insert_text((84, y), line, fontsize=12, fontname="helv")


def _append_pdf(out, fp, dpi, quality):
    src = fitz.open(fp)
    for i in range(src.page_count):
        pg = src[i]
        if not pg.get_images():
            out.insert_pdf(src, from_page=i, to_page=i)
        else:
            pix = pg.get_pixmap(dpi=dpi)
            if pix.alpha:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            np = out.new_page(width=pg.rect.width, height=pg.rect.height)
            np.insert_image(np.rect, stream=pix.tobytes("jpeg", jpg_quality=quality))
    src.close()


def build(mc, brief_md, core_ids, dpi=110, quality=45):
    mt, docket, forum, core, related = _gather(mc, core_ids)
    # 1. front matter — render the brief markdown to PDF (reuse render_memo)
    subprocess.run(["python3", os.path.join(HERE, "render_memo.py"), brief_md, "brief"],
                   capture_output=True, text=True)
    front = f"/tmp/{os.path.splitext(os.path.basename(brief_md))[0]}.pdf"
    # 2. supporting-documents index (open links)
    supp = f"/tmp/_supp_{mc}.pdf"
    _support_index(supp, mt, core, related)
    # 3. merge: brief + index + bound core exhibits
    out = fitz.open()
    out.insert_pdf(fitz.open(front))
    out.insert_pdf(fitz.open(supp))
    for i, (did, title, dd, fp, txt) in enumerate(core):
        _divider(out, f"EXHIBIT {EXLAB[i]}", f"{title}" + (f"  ·  {dd}" if dd else ""))
        if fp and os.path.exists(fp):
            _append_pdf(out, fp, dpi, quality)
        elif txt.strip():
            tx = f"/tmp/_tx_{did}.pdf"
            _text_exhibit(tx, title, txt)
            out.insert_pdf(fitz.open(tx))
    path = f"/tmp/package_{mc}.pdf"
    out.save(path, garbage=4, deflate=True)
    out.close()
    return path, len(core), len(related)


def main():
    mc = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "MWK-ARTA-1891"
    brief = sys.argv[sys.argv.index("--brief") + 1] if "--brief" in sys.argv else None
    core = [int(x) for x in sys.argv[sys.argv.index("--core") + 1].split(",")] if "--core" in sys.argv else []
    dpi = int(sys.argv[sys.argv.index("--dpi") + 1]) if "--dpi" in sys.argv else 110
    q = int(sys.argv[sys.argv.index("--quality") + 1]) if "--quality" in sys.argv else 45
    if not brief or not core:
        sys.exit("usage: case_package.py MATTER --brief brief.md --core 708,709,... [--send]")
    path, nc, nr = build(mc, brief, core, dpi, q)
    kb = os.path.getsize(path) // 1024
    print(f"[package] {mc}: {nc} core exhibits bound + {nr} supporting docs linked → {path} ({kb} KB)")
    if "--send" in sys.argv:
        tok = _tok()
        r = subprocess.run(["curl", "-s", "-F", f"chat_id={CHAT}", "-F", f"caption={mc} — Case Package (for counsel)",
                            "-F", f"document=@{path}", f"https://api.telegram.org/bot{tok}/sendDocument"],
                           capture_output=True, text=True)
        print("[send] sent ✓" if '"ok":true' in r.stdout else f"[send] FAIL {r.stdout[:160]}")


if __name__ == "__main__":
    main()
