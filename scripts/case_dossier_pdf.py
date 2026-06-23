#!/usr/bin/env python3
"""case_dossier_pdf.py — a SCANNABLE corpus dossier for a matter → Telegram PDF. $0, deterministic.

Not the action memo (analysis) — this is the case bundle's front matter: everything a lawyer needs to
scan the matter's corpus fast and drill into any source. Sections:
  1. Cover / at-a-glance (status, counts, forums)
  2. Correspondence & referral timeline (chronological: date · from → subject) — every email/letter, linked
  3. Documents by category (pleadings / referrals & notices / responses & letters / evidence & annexes /
     authority) — each: title, date, 1-line excerpt, [N facts], tap-to-open link
  4. Verified facts grouped by source document (the grounded substance, provenance-tagged + linked)
Every doc reference is a clickable link to the dashboard serve endpoint (disk-or-Drive, Tailscale).

  python3 scripts/case_dossier_pdf.py MWK-ARTA-1891 --send
"""
import datetime
import html
import os
import re
import subprocess
import sys

import psycopg2
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from humanize import doc_titles as _doc_titles, matter_names as _matter_names, humanize as _humanize

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
DOCBASE = os.environ.get("LANDTEK_DOC_BASE", "http://100.85.203.58:8765")
CHAT = "6513067717"


def _tok():
    for line in open("/root/landtek/.env"):
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            return line.split("=", 1)[1].strip()
    return None


def _e(s):
    return html.escape(str(s or ""))


def _cat(fn):
    f = (fn or "").lower()
    if re.search(r"complaint|petition|manifestation|affidavit|motion|ejectment|answer", f):
        return "1. Operative pleadings"
    if re.search(r"referral|nor-|indorsement|notice of", f):
        return "2. Referrals & notices"
    if re.search(r"letter|response|order|reply|resolution", f):
        return "3. Agency responses, letters & orders"
    if re.search(r"annex|exhibit|minutes|record|hearing|certificat", f):
        return "4. Evidence & annexes"
    if re.search(r"spa|power of attorney", f):
        return "5. Authority (SPAs)"
    return "6. Other / supporting"


def _link(did, ok):
    return f"<a href='{DOCBASE}/files/c/{did}'>doc:{did} ↗</a>" if ok else f"doc:{did}"


def build(mc, path):
    c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("SELECT title, coalesce(docket_number,''), coalesce(forum,court_or_agency,''), coalesce(status,'') FROM matters WHERE matter_code=%s", (mc,))
    title, docket, forum, status = cur.fetchone() or ("", "", "", "")
    cur.execute("SELECT doc_id FROM matter_relevance WHERE focal_matter=%s AND tier='OFF-PROFILE'", (mc,))
    off = {r[0] for r in cur.fetchall()}

    # documents of the matter (matter_code OR linked), with excerpt + availability + facts count
    cur.execute("""SELECT d.id, coalesce(d.original_filename,d.smart_filename,'?'), d.doc_date,
                   left(coalesce(d.extracted_text,''),200),
                   (d.file_path IS NOT NULL OR coalesce(d.drive_file_id,'')<>'') ok,
                   (SELECT count(*) FROM matter_facts f WHERE f.matter_code=%s AND f.provenance_level='verified'
                      AND f.source_kind='doc' AND f.source_id=d.id::text) nf,
                   length(coalesce(d.extracted_text,'')) tl
                   FROM documents d WHERE d.matter_code=%s
                     OR d.id IN (SELECT doc_id FROM document_matter_links WHERE matter_code=%s)
                   ORDER BY d.id""", (mc, mc, mc))
    docs = [r for r in cur.fetchall() if r[0] not in off]

    # correspondence ledger (gmail)
    tok0 = docket.split()[-1] if docket else mc
    cur.execute("""SELECT coalesce(sent_at::date::text,received_at::date::text,'?') dt,
                   left(coalesce(from_name,from_addr,'?'),24), left(coalesce(subject,''),60)
                   FROM gmail_messages WHERE subject ILIKE %s OR body_plain ILIKE %s
                   ORDER BY coalesce(sent_at,received_at)""", (f"%{tok0}%", f"%{tok0}%"))
    corr = cur.fetchall()

    # verified facts grouped by source doc
    cur.execute("""SELECT source_id, statement FROM matter_facts WHERE matter_code=%s AND provenance_level='verified'
                   ORDER BY (source_id ~ '^[0-9]+$') DESC, source_id, id""", (mc,))
    facts = [(s, st) for s, st in cur.fetchall() if not (s and s.isdigit() and int(s) in off)]
    DT = _doc_titles(cur, mc); MN = _matter_names(cur)   # human titles / names (no internal ids on the page)

    s = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=s["Heading1"], fontSize=15, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=s["BodyText"], fontSize=8.5, textColor=colors.HexColor("#6b7280"))
    h2 = ParagraphStyle("h2", parent=s["Heading2"], fontSize=12, spaceBefore=11, spaceAfter=3, textColor=colors.HexColor("#1e293b"))
    h3 = ParagraphStyle("h3", parent=s["Heading3"], fontSize=10, spaceBefore=6, spaceAfter=1, textColor=colors.HexColor("#374151"))
    bdy = ParagraphStyle("bdy", parent=s["BodyText"], fontSize=9, leading=12)
    note = ParagraphStyle("note", parent=bdy, fontSize=7.5, textColor=colors.HexColor("#6b7280"))
    f = []

    # 1. cover
    f.append(Paragraph(f"{_e(mc)} — Case Corpus Dossier", h1))
    f.append(Paragraph(f"{_e(title)}<br/>Forum/Docket: {_e(forum)} → {_e(docket)} &nbsp;·&nbsp; Status: {_e(status)} "
                       f"&nbsp;·&nbsp; Generated {datetime.date.today().isoformat()} — LandTek", sub))
    f.append(Paragraph(f"<b>At a glance:</b> {len(docs)} documents · {len(corr)} logged communications · "
                       f"{len(facts)} verified facts. Document links open the source (LandTek viewer, over Tailscale).", sub))
    f.append(Spacer(1, 5))

    # 2. correspondence timeline
    f.append(Paragraph(f"1. Correspondence &amp; referral timeline ({len(corr)})", h2))
    for dt, frm, subj in corr:
        f.append(Paragraph(f"<b>{_e(dt)}</b> &nbsp; {_e(frm)} &nbsp;→&nbsp; {_e(subj)}", bdy))
    if not corr:
        f.append(Paragraph("(no logged email correspondence)", note))

    # 3. documents by category
    f.append(Paragraph(f"2. Documents by category ({len(docs)})", h2))
    bycat = {}
    for did, fn, dd, exc, ok, nf, tl in docs:
        bycat.setdefault(_cat(fn), []).append((did, fn, dd, exc, ok, nf, tl))
    for cat in sorted(bycat):
        f.append(Paragraph(_e(cat), h3))
        for did, fn, dd, exc, ok, nf, tl in bycat[cat]:
            nm = DT.get(did, fn)
            meta = (f" · {dd}" if dd else "") + (f" · <font color='#059669'>{nf} cited fact{'s' if nf!=1 else ''}</font>" if nf else (" · <font color='#b45309'>not yet read</font>" if tl > 800 else ""))
            link = f"<a href='{DOCBASE}/files/c/{did}'><b>{_e(nm[:60])}</b> ↗</a>" if ok else f"<b>{_e(nm[:60])}</b>"
            f.append(Paragraph(f"&bull; {link}{meta}", bdy))
            if exc.strip():
                f.append(Paragraph(f"&nbsp;&nbsp;<font size='7' color='#6b7280'>“{_e(' '.join(exc.split())[:150])}…”</font>", note))

    # 4. verified facts by source
    f.append(Paragraph(f"3. Verified facts by source ({len(facts)})", h2))
    cursrc = None
    for src, st in facts:
        if src != cursrc:
            cursrc = src
            if src and src.isdigit():
                nm = DT.get(int(src), "source document")
                tag = f"<a href='{DOCBASE}/files/c/{int(src)}'>{_e(nm)} ↗</a>"
            else:
                tag = _e(src or "record")
            f.append(Paragraph(f"<b>Source: {tag}</b>", h3))
        f.append(Paragraph(f"&bull; {_e(_humanize(st[:240], DT, MN))}", bdy))
    f.append(Spacer(1, 6))
    f.append(Paragraph("Corpus dossier — verified facts are corpus-grounded (cited source + excerpt). For analysis "
                       "& recommended actions see the Action Memo. LandTek Assisted — operator/counsel review.", note))

    SimpleDocTemplate(path, pagesize=letter, topMargin=0.6*inch, bottomMargin=0.6*inch, title=f"{mc} dossier").build(f)
    return len(docs), len(corr), len(facts)


def main():
    mc = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "MWK-ARTA-1891"
    path = f"/tmp/dossier_{mc}.pdf"
    nd, nc, nf = build(mc, path)
    print(f"[dossier] {mc}: {nd} docs, {nc} comms, {nf} facts → {path}")
    if "--send" in sys.argv:
        tok = _tok()
        r = subprocess.run(["curl", "-s", "-F", f"chat_id={CHAT}", "-F", f"caption={mc} — Case Corpus Dossier",
                            "-F", f"document=@{path}", f"https://api.telegram.org/bot{tok}/sendDocument"],
                           capture_output=True, text=True)
        print("[send] sent ✓" if '"ok":true' in r.stdout else f"[send] FAIL {r.stdout[:150]}")


if __name__ == "__main__":
    main()
