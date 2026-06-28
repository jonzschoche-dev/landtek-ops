#!/usr/bin/env python3
"""case_bundle.py — a professional, self-contained CASE BUNDLE: clean front matter + the actual supporting
documents bound in as labeled exhibits. $0, local (reportlab + PyMuPDF). Ghostscript-free.

Unlike the action memo (analysis) or the dossier (text index), this is the filing-grade article: a reader
opens ONE pdf and finds a cover, a clean statement of facts (each fact cross-referenced to its exhibit),
an index of exhibits, and then the exhibits themselves — the real document pages, downsampled for delivery.

  python3 scripts/case_bundle.py MWK-ARTA-1891 [--send] [--dpi 120] [--quality 50]
"""
import datetime
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
from reportlab.platypus import Paragraph, PageBreak, SimpleDocTemplate, Spacer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from humanize import doc_titles as _doc_titles, matter_names as _matter_names, humanize as _humanize

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
CHAT = "6513067717"


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
        return 0   # operative pleadings first
    if re.search(r"annex|minutes|resolution|hearing|record|exhibit|certificat", f):
        return 1   # the core evidence
    if re.search(r"referral|notice|indorsement", f):
        return 2
    if re.search(r"letter|response|order|reply", f):
        return 3
    return 4


def _gather(mc):
    c = psycopg2.connect(DSN); cur = c.cursor()
    cur.execute("SELECT coalesce(title,''), coalesce(docket_number,''), coalesce(forum,court_or_agency,'') FROM matters WHERE matter_code=%s", (mc,))
    title, docket, forum = cur.fetchone() or ("", "", "")
    DT = _doc_titles(cur, mc); MN = _matter_names(cur)
    cur.execute("SELECT doc_id FROM matter_relevance WHERE focal_matter=%s AND tier='OFF-PROFILE'", (mc,))
    off = {r[0] for r in cur.fetchall()}
    cur.execute("""SELECT d.id, coalesce(d.original_filename,d.smart_filename,'?'), d.doc_date, d.file_path,
                   (SELECT count(*) FROM matter_facts f WHERE f.matter_code=%s AND f.source_id=d.id::text
                      AND f.provenance_level='verified') nf
                   FROM documents d
                   WHERE (d.matter_code=%s OR d.id IN (SELECT doc_id FROM document_matter_links WHERE matter_code=%s))
                     AND d.file_path IS NOT NULL
                     AND coalesce(d.original_filename, d.smart_filename, '') !~* 'sample|template'
                   ORDER BY d.id""", (mc, mc, mc))
    docs = []
    for did, fn, dd, fp, nf in cur.fetchall():
        if did in off or not (fp and os.path.exists(fp)):
            continue
        if nf == 0 and _rank(fn) > 1:        # skip fact-less peripheral letters; keep operative + core evidence
            continue
        try:
            pc = fitz.open(fp).page_count
        except Exception:
            continue
        docs.append([did, DT.get(did, fn), dd, fp, nf, pc])
    docs.sort(key=lambda r: (_rank(r[1]), -r[4], r[0]))
    docs = docs[:14]                         # pick the most-relevant, then…
    # …bind them in CHRONOLOGICAL order so the exhibits follow the dossier's timeline outline —
    # complaint first, then each response/order in sequence — for prompt examination in order.
    docs.sort(key=lambda r: (str(r[2]) if r[2] else "9999-99-99", r[0]))
    exmap = {docs[i][0]: chr(65 + i) for i in range(len(docs))}
    cur.execute("""SELECT statement, source_id FROM matter_facts WHERE matter_code=%s AND provenance_level='verified'
                   ORDER BY (source_id ~ '^[0-9]+$') DESC, source_id, id""", (mc,))
    facts = [(st, sid) for st, sid in cur.fetchall() if not (sid and sid.isdigit() and int(sid) in off)]
    tmap = {}
    if docs:
        cur.execute("SELECT id, left(coalesce(extracted_text,''),60000) FROM documents WHERE id = ANY(%s)",
                    ([d[0] for d in docs],))
        tmap = {r[0]: r[1] for r in cur.fetchall()}
    c.close()
    return title, docket, forum, docs, exmap, facts, DT, MN, tmap


def _front_matter(path, mc, title, docket, forum, docs, exmap, facts, DT, MN, brief=False):
    s = getSampleStyleSheet()
    cover_t = ParagraphStyle("ct", parent=s["Title"], fontSize=22, leading=26, alignment=1, spaceAfter=6)
    cover_s = ParagraphStyle("cs", parent=s["Normal"], fontSize=12, leading=16, alignment=1, textColor=colors.HexColor("#374151"))
    h = ParagraphStyle("h", parent=s["Heading2"], fontSize=12.5, spaceBefore=12, spaceAfter=4, textColor=colors.HexColor("#111827"))
    body = ParagraphStyle("b", parent=s["BodyText"], fontSize=10, leading=14, spaceAfter=2)
    idx = ParagraphStyle("i", parent=body, fontSize=10, leading=15)
    note = ParagraphStyle("n", parent=body, fontSize=8, textColor=colors.HexColor("#6b7280"))
    f = []
    today = datetime.date.today().strftime("%B %d, %Y")

    if not brief:                                       # full mode: cover + auto statement of facts
        # ── Cover ──
        f.append(Spacer(1, 1.6 * inch))
        f.append(Paragraph(_e(title or mc), cover_t))
        f.append(Spacer(1, 8))
        f.append(Paragraph("CASE BUNDLE", ParagraphStyle("cb", parent=cover_s, fontSize=14, textColor=colors.HexColor("#1e293b"))))
        f.append(Paragraph("Statement of Facts &amp; Supporting Exhibits", cover_s))
        f.append(Spacer(1, 18))
        f.append(Paragraph(f"{_e(forum)}{(' &nbsp;·&nbsp; Docket ' + _e(docket)) if docket else ''}", cover_s))
        f.append(Paragraph(f"{len(docs)} exhibits &nbsp;·&nbsp; {today}", cover_s))
        f.append(Spacer(1, 30))
        f.append(Paragraph("Prepared by LandTek — for review by counsel. Facts are drawn verbatim from the exhibits; "
                           "any item requiring confirmation is marked.", note))
        f.append(PageBreak())
        # ── Statement of Facts (clean, numbered, exhibit-cross-referenced) ──
        f.append(Paragraph("Statement of Facts", h))
        f.append(Paragraph("Each fact is established by the exhibit cited; exhibits follow this front matter.", note))
        f.append(Spacer(1, 4))
        n = 0
        for st, sid in facts:
            n += 1
            xref = f" <b>(Exhibit {exmap[int(sid)]})</b>" if (sid and sid.isdigit() and int(sid) in exmap) else ""
            f.append(Paragraph(f"{n}.&nbsp; {_e(_humanize(st, DT, MN))}{xref}", body))
        f.append(PageBreak())

    # ── Index of Exhibits ── (in brief mode the analytical dossier precedes this page)
    f.append(Paragraph("Index of Exhibits", h))
    if brief:
        f.append(Paragraph("The analytical dossier precedes this index. The exhibits below follow it, bound in "
                           "chronological order so the primary documents can be examined in sequence.", note))
        f.append(Spacer(1, 4))
    for did, nm, dd, fp, nf, pc in docs:
        L = exmap[did]
        meta = (f"{dd} · " if dd else "") + f"{pc} page{'s' if pc != 1 else ''}"
        f.append(Paragraph(f"<b>Exhibit {L}</b> &nbsp; {_e(nm)} &nbsp; <font size='8' color='#6b7280'>({meta})</font>", idx))
    f.append(Paragraph("&nbsp;", body))
    f.append(Paragraph("Scanned exhibits are reproduced as imaged; selectable-text pages are preserved as text.", note))

    SimpleDocTemplate(path, pagesize=letter, topMargin=0.8 * inch, bottomMargin=0.7 * inch,
                      title=f"{mc} Case Bundle").build(f)


def _divider(out, label, subtitle):
    pg = out.new_page(width=612, height=792)
    pg.draw_rect(fitz.Rect(60, 250, 552, 420), color=(0.85, 0.87, 0.9), width=1)
    pg.insert_text((84, 320), label, fontsize=30, fontname="hebo")
    # wrap subtitle
    words = subtitle.split(); line = ""; y = 360
    for w in words:
        if len(line) + len(w) > 60:
            pg.insert_text((84, y), line, fontsize=12, fontname="helv"); y += 18; line = ""
        line += w + " "
    if line:
        pg.insert_text((84, y), line, fontsize=12, fontname="helv")


def _render_text_pages(out, text, label):
    """Last resort for a non-PDF/non-image exhibit (e.g. .docx, no libreoffice): render it from its
    extracted text so the CONTENT is still in the bundle, examinable in order. Clearly marked as
    text-rendered, not the native file."""
    head = (f"[Exhibit rendered from extracted text — original file: {label}. "
            f"Examine the native document for exact formatting / signatures.]")
    pg = out.new_page(); y = 56
    for raw in (head + "\n\n" + (text or "(no extractable text)")).split("\n"):
        for k in range(0, max(len(raw), 1), 96):
            if y > 770:
                pg = out.new_page(); y = 56
            pg.insert_text((52, y), raw[k:k + 96], fontsize=9, fontname="helv"); y += 12


def _append_doc(out, fp, dpi, quality, text="", label=""):
    try:
        src = fitz.open(fp)
    except Exception:
        src = None
    if src is not None and getattr(src, "is_pdf", False):
        for i in range(src.page_count):
            pg = src[i]
            if not pg.get_images():                              # pure text/vector page — keep crisp + tiny
                out.insert_pdf(src, from_page=i, to_page=i)
            else:                                                # page carries scan image(s) — downsample + JPEG
                pix = pg.get_pixmap(dpi=dpi)
                if pix.alpha:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                np = out.new_page(width=pg.rect.width, height=pg.rect.height)
                np.insert_image(np.rect, stream=pix.tobytes("jpeg", jpg_quality=quality))
        src.close(); return
    if src is not None:                                          # image/other fitz can rasterize → convert to PDF
        try:
            pdfb = src.convert_to_pdf(); src.close()
            out.insert_pdf(fitz.open("pdf", pdfb)); return
        except Exception:
            try:
                src.close()
            except Exception:
                pass
    _render_text_pages(out, text, label)                        # .docx etc. — render the content so it's in-bundle


def build(mc, dpi=110, quality=45, brief_md=None):
    title, docket, forum, docs, exmap, facts, DT, MN, tmap = _gather(mc)
    if not docs:
        sys.exit(f"[bundle] no local supporting documents found for {mc}")
    out = fitz.open()
    if brief_md and os.path.exists(brief_md):           # lead with the analytical dossier (render md → PDF)
        import render_memo
        bpdf = f"/tmp/_brief_{mc}.pdf"
        try:
            render_memo.render(brief_md, bpdf)
            out.insert_pdf(fitz.open(bpdf))
        except Exception as e:
            print(f"[bundle] brief render failed, continuing without it: {e}", file=sys.stderr)
    front = f"/tmp/_front_{mc}.pdf"
    _front_matter(front, mc, title, docket, forum, docs, exmap, facts, DT, MN, brief=bool(brief_md))
    out.insert_pdf(fitz.open(front))
    for did, nm, dd, fp, nf, pc in docs:
        _divider(out, f"EXHIBIT {exmap[did]}", f"{nm}" + (f"  ·  {dd}" if dd else ""))
        _append_doc(out, fp, dpi, quality, text=tmap.get(did, ""), label=nm)
    path = f"/tmp/bundle_{mc}.pdf"
    out.save(path, garbage=4, deflate=True)
    out.close()
    return path, len(docs)


def main():
    mc = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "MWK-ARTA-1891"
    dpi = int(sys.argv[sys.argv.index("--dpi") + 1]) if "--dpi" in sys.argv else 120
    q = int(sys.argv[sys.argv.index("--quality") + 1]) if "--quality" in sys.argv else 50
    brief = sys.argv[sys.argv.index("--brief") + 1] if "--brief" in sys.argv else None
    path, nex = build(mc, dpi, q, brief_md=brief)
    kb = os.path.getsize(path) // 1024
    print(f"[bundle] {mc}: {nex} exhibits → {path} ({kb} KB)")
    if "--send" in sys.argv:
        tok = _tok()
        r = subprocess.run(["curl", "-s", "-F", f"chat_id={CHAT}", "-F", f"caption={mc} — Case Bundle ({nex} exhibits)",
                            "-F", f"document=@{path}", f"https://api.telegram.org/bot{tok}/sendDocument"],
                           capture_output=True, text=True)
        print("[send] sent ✓" if '"ok":true' in r.stdout else f"[send] FAIL {r.stdout[:160]}")


if __name__ == "__main__":
    main()
