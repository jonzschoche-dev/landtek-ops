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

try:  # outward-action chokepoint (deploy_717) — closes the raw-sendDocument bypass
    import outward_guard
except Exception:
    outward_guard = None

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


# foundational narrative doc-types that belong in the packet even when no matter_fact cites them by id
CORE_RE = __import__("re").compile(
    r"inquiry|request|letter|cease|demand|reply|respons|complaint|escalation|rejoinder|manifest|"
    r"order|resolution|\bnsr\b|\bosca\b|affidavit|indorsement|referral|notice", __import__("re").I)


def _gather(mc, exclude=frozenset(), core=False):
    c = psycopg2.connect(DSN); cur = c.cursor()
    cur.execute("SELECT coalesce(title,''), coalesce(docket_number,''), coalesce(forum,court_or_agency,'') FROM matters WHERE matter_code=%s", (mc,))
    title, docket, forum = cur.fetchone() or ("", "", "")
    DT = _doc_titles(cur, mc); MN = _matter_names(cur)
    cur.execute("SELECT doc_id FROM matter_relevance WHERE focal_matter=%s AND tier='OFF-PROFILE'", (mc,))
    off = {r[0] for r in cur.fetchall()}
    cur.execute("""SELECT d.id, coalesce(d.original_filename,d.smart_filename,'?'), d.doc_date, d.file_path,
                   (SELECT count(*) FROM matter_facts f WHERE f.matter_code=%s AND f.source_id=d.id::text
                      AND f.provenance_level='verified') nf,
                   coalesce(d.content_hash,''),
                   lower(regexp_replace(left(coalesce(d.extracted_text,''),1200),'[^a-z0-9]','','g'))
                   FROM documents d
                   WHERE (d.matter_code=%s OR d.id IN (SELECT doc_id FROM document_matter_links WHERE matter_code=%s))
                     AND d.file_path IS NOT NULL
                     AND coalesce(d.original_filename, d.smart_filename, '') !~* 'sample|template'
                     AND coalesce(d.original_filename, d.smart_filename, '') !~* '[.]zip$'
                   ORDER BY d.id""", (mc, mc, mc))
    docs, seen_hash, seen_near = [], set(), set()
    for did, fn, dd, fp, nf, chash, tkey in cur.fetchall():
        if did in off or did in exclude or not (fp and os.path.exists(fp)):
            continue
        # keep the NARRATIVE: a doc earns a place if it is fact-cited, OR a core doc-type, OR simply dated
        # (the initial letters / correspondence up to the complaint). Drop only undated fact-less non-core noise.
        if nf == 0 and _rank(fn) > 1 and not dd and not CORE_RE.search(fn or ""):
            continue
        # DEDUP — bind each document once: drop exact-byte dups AND same-day same-content re-scans
        # (e.g. the complaint ingested under two filenames) by (date, first-300 alnum of text).
        nearkey = (str(dd), tkey[:300]) if len(tkey) >= 300 else None
        if (chash and chash in seen_hash) or (nearkey and nearkey in seen_near):
            continue
        try:
            pc = fitz.open(fp).page_count
        except Exception:
            continue
        if chash:
            seen_hash.add(chash)
        if nearkey:
            seen_near.add(nearkey)
        docs.append([did, DT.get(did, fn), dd, fp, nf, pc])
    _chrono = lambda r: (str(r[2]) if r[2] else "9999-99-99", r[0])
    if core:                                  # SLIM working copy: the spine, the rest go to a linked index
        chrono = sorted(docs, key=_chrono)
        early = chrono[:6]                     # the initial letters → the complaint (precipitating narrative)
        rest = sorted([d for d in docs if d not in early], key=lambda r: (_rank(r[1]), -r[4], r[0]))
        bound = early + rest[:6]               # + the key dispositions / operative documents
        supporting = [d for d in docs if d not in bound]
    else:                                      # FULL archive: bind the whole record (capped)
        docs.sort(key=lambda r: (_rank(r[1]), -r[4], r[0]))
        bound, supporting = docs[:20], []
    bound.sort(key=_chrono)                    # bind chronologically (initial letters → complaint → orders)
    supporting.sort(key=_chrono)
    exmap = {bound[i][0]: chr(65 + i) for i in range(len(bound))}
    facts = _projected_facts(cur, mc, off)   # A75: verified slice through the case-bundle profile
    tmap = {}
    if bound:
        cur.execute("SELECT id, left(coalesce(extracted_text,''),60000) FROM documents WHERE id = ANY(%s)",
                    ([d[0] for d in bound],))
        tmap = {r[0]: r[1] for r in cur.fetchall()}
    c.close()
    return title, docket, forum, bound, supporting, exmap, facts, DT, MN, tmap


def _front_matter(path, mc, title, docket, forum, docs, exmap, facts, DT, MN, supporting=None, brief=False, startmap=None):
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
        loc = f" &nbsp; <b>p.&nbsp;{startmap[did]}</b>" if (startmap and did in startmap) else ""
        meta = (f"{dd} · " if dd else "") + f"{pc} page{'s' if pc != 1 else ''}"
        f.append(Paragraph(f"<b>Exhibit {L}</b> &nbsp; {_e(nm)}{loc} &nbsp; <font size='8' color='#6b7280'>({meta})</font>", idx))
    f.append(Paragraph("&nbsp;", body))
    f.append(Paragraph("Navigate via the PDF bookmarks (outline). Scanned exhibits are reproduced as imaged; "
                       "text-layer pages are preserved as selectable text.", note))
    # ── Index of Supporting Documents (core/working copy: the rest of the record, one open link each) ──
    if supporting:
        f.append(PageBreak())
        f.append(Paragraph("Index of Supporting Documents", h))
        f.append(Paragraph("Not bound in this working copy — each opens the full document on the case server:", note))
        f.append(Spacer(1, 4))
        for did, nm, dd, fp, nf, pc in supporting:
            url = f"https://leo.hayuma.org/files/c/{did}"
            when = f"{dd} · " if dd else ""
            f.append(Paragraph(f"&bull;&nbsp; {when}{_e(nm)} &nbsp; "
                               f"<link href='{url}'><font size='8' color='#1d4ed8'>{url}</font></link>", idx))

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


def _stamp_pagenums(out):
    for i in range(out.page_count):
        try:
            r = out[i].rect
            out[i].insert_text((r.width - 62, r.height - 22), f"p. {i + 1}", fontsize=8,
                               fontname="helv", color=(0.5, 0.5, 0.5))
        except Exception:
            pass


def _projected_facts(cur, mc, off):
    """A75: verified (statement, source handle) slice via the case-bundle RecipientProfile
    (WHO=A5 wall in-query); off-profile source docs dropped (preserved from the prior raw read)."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "leo_tools"))
    from recipient_projection import project_fact_slice
    return [(f["statement"], f["source_id"]) for f in project_fact_slice(cur, "case-bundle", mc)
            if f["provenance_level"] == "verified"
            and not (f["source_id"] and f["source_id"].isdigit() and int(f["source_id"]) in off)]


def build(mc, dpi=110, quality=45, brief_md=None, exclude=frozenset(), core=False):
    title, docket, forum, docs, supporting, exmap, facts, DT, MN, tmap = _gather(mc, exclude, core)
    if not docs:
        sys.exit(f"[bundle] no local supporting documents found for {mc}")
    # 1) the analytical brief (render md → PDF)
    brief_pdf = None
    if brief_md and os.path.exists(brief_md):
        import render_memo
        brief_pdf = f"/tmp/_brief_{mc}.pdf"
        try:
            render_memo.render(brief_md, brief_pdf)
        except Exception as e:
            print(f"[bundle] brief render failed, continuing without it: {e}", file=sys.stderr); brief_pdf = None
    B = fitz.open(brief_pdf).page_count if (brief_pdf and os.path.exists(brief_pdf)) else 0
    # 2) merge exhibits once into a side doc, recording each exhibit's start page (relative)
    ex = fitz.open(); rel = {}
    for did, nm, dd, fp, nf, pc in docs:
        rel[did] = ex.page_count
        _divider(ex, f"EXHIBIT {exmap[did]}", f"{nm}" + (f"  ·  {dd}" if dd else ""))
        _append_doc(ex, fp, dpi, quality, text=tmap.get(did, ""), label=nm)
    # 3) front matter — render to measure length F, then re-render with ABSOLUTE exhibit start pages
    front = f"/tmp/_front_{mc}.pdf"
    _front_matter(front, mc, title, docket, forum, docs, exmap, facts, DT, MN, supporting, bool(brief_md), None)
    F = fitz.open(front).page_count
    startmap = {did: B + F + rel[did] + 1 for did in rel}              # 1-based absolute page of each divider
    _front_matter(front, mc, title, docket, forum, docs, exmap, facts, DT, MN, supporting, bool(brief_md), startmap)
    # 4) assemble brief → front matter → exhibits, and build the navigable bookmark outline
    out = fitz.open(); toc = []
    if brief_pdf and os.path.exists(brief_pdf):
        out.insert_pdf(fitz.open(brief_pdf)); toc.append([1, "Analytical brief", 1])
    toc.append([1, "Index of exhibits", out.page_count + 1])
    out.insert_pdf(fitz.open(front))
    out.insert_pdf(ex)
    for did, nm, dd, fp, nf, pc in docs:
        toc.append([1, f"Exhibit {exmap[did]} — {nm[:46]}" + (f" ({dd})" if dd else ""), startmap[did]])
    _stamp_pagenums(out)
    try:
        out.set_toc(toc)
    except Exception as e:
        print(f"[bundle] bookmark set failed: {e}", file=sys.stderr)
    path = f"/tmp/bundle_{'core_' if core else ''}{mc}.pdf"
    out.save(path, garbage=4, deflate=True); out.close()
    return path, len(docs)


def main():
    mc = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "MWK-ARTA-1891"
    dpi = int(sys.argv[sys.argv.index("--dpi") + 1]) if "--dpi" in sys.argv else 120
    q = int(sys.argv[sys.argv.index("--quality") + 1]) if "--quality" in sys.argv else 50
    brief = sys.argv[sys.argv.index("--brief") + 1] if "--brief" in sys.argv else None
    exclude = frozenset(int(x) for x in sys.argv[sys.argv.index("--exclude") + 1].split(",")) \
        if "--exclude" in sys.argv else frozenset()
    core = "--core" in sys.argv
    # A70 incorporation gate — fail-closed: no bundle on a thin / gap-blind base.
    from incorporation_gate import require_incorporation
    _gc = psycopg2.connect(DSN)
    _v = require_incorporation(_gc.cursor(), mc, stakeholder="counsel", purpose="bundle")
    _gc.close()
    if _v["verdict"] != "READY":
        print(f"[bundle] {mc}: incorporation gate → {_v['verdict']} (verified={_v.get('verified_count')}) "
              f"— NOT binding a bundle on a base that can't ground it. reasons: {_v.get('reasons')}")
        return
    path, nex = build(mc, dpi, q, brief_md=brief, exclude=exclude, core=core)
    kb = os.path.getsize(path) // 1024
    kind = "Core packet" if core else "Full bundle"
    print(f"[bundle] {mc}: {kind} — {nex} exhibits bound → {path} ({kb} KB)")
    if "--send" in sys.argv:
        tok = _tok()
        # Outward chokepoint (deploy_717) — shadow logs; block holds an un-approved outward bundle.
        if outward_guard is not None:
            try:
                _d, _gi = outward_guard.guard("telegram", CHAT, source="case_bundle",
                                              preview=f"{mc} {kind} ({nex} exhibits) [document]")
            except Exception:
                _d = "allow"
            if _d == "hold":
                print(f"[send] HELD by outward_guard (order #{_gi.get('order')}) — not sent")
                return
        r = subprocess.run(["curl", "-s", "-F", f"chat_id={CHAT}", "-F", f"caption={mc} — {kind} ({nex} exhibits)",
                            "-F", f"document=@{path}", f"https://api.telegram.org/bot{tok}/sendDocument"],
                           capture_output=True, text=True)
        print("[send] sent ✓" if '"ok":true' in r.stdout else f"[send] FAIL {r.stdout[:160]}")


if __name__ == "__main__":
    main()
