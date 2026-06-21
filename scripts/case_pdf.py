#!/usr/bin/env python3
"""case_pdf.py — organized case-brief PDF for a matter, pushed to Telegram. Top-to-bottom + annexes.

Assembles one readable PDF: identity → parties → causes of action → the VERIFIED fact corpus (each
cited to its annex doc) → forum routing (candidate bodies + remedies) → ANNEXES (every relevant
document with a link to the original) → coverage/disclaimers. Only document-proven facts in the body;
operator/derived items are labeled. Sent via the Telegram bot sendDocument.

  python3 scripts/case_pdf.py MWK-CV26360 --send
"""
import html
import subprocess
import sys
from datetime import date

import psycopg2
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
CHAT = "6513067717"


def _tok():
    try:
        for line in open("/root/landtek/.env"):
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None


def _e(s):
    return html.escape(str(s or ""))


def _link(dl, did, path):
    if dl:
        return dl
    if did:
        return f"https://drive.google.com/file/d/{did}/view"
    return path or "(stored in corpus)"


def build(mc, path):
    c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("""SELECT title, coalesce(forum,court_or_agency,''), coalesce(docket_number,''),
                   coalesce(status,''), coalesce(current_stage,''), next_deadline
                   FROM matters WHERE matter_code=%s""", (mc,))
    m = cur.fetchone() or ("", "", "", "", "", None)
    title, forum, docket, status, stage, deadline = m

    s = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=s["Heading1"], fontSize=16, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=s["BodyText"], fontSize=9, textColor=colors.HexColor("#6b7280"))
    h2 = ParagraphStyle("h2", parent=s["Heading2"], fontSize=12, spaceBefore=12, spaceAfter=4,
                        textColor=colors.HexColor("#1e293b"))
    body = ParagraphStyle("body", parent=s["BodyText"], fontSize=9.5, leading=13)
    cite = ParagraphStyle("cite", parent=body, fontSize=8, textColor=colors.HexColor("#2563eb"))
    note = ParagraphStyle("note", parent=body, fontSize=8, textColor=colors.HexColor("#6b7280"))
    f = []

    f.append(Paragraph(f"{_e(mc)} &mdash; {_e(title)}", h1))
    meta = " &nbsp;·&nbsp; ".join(x for x in [
        _e(forum), (f"Docket: {_e(docket)}" if docket else ""),
        (f"Status: {_e(status)}/{_e(stage)}" if status else ""),
        (f"Next deadline: {_e(deadline)}" if deadline else "")] if x)
    f.append(Paragraph(meta, sub))
    f.append(Paragraph(f"Generated {date.today().isoformat()} — verified corpus only in the body; "
                       "operator/derived items flagged. Drafts for review, not filings.", note))

    cur.execute("""SELECT side, party_name, role FROM matter_parties WHERE matter_code=%s
                   AND provenance_level='verified' ORDER BY side DESC, id""", (mc,))
    parties = cur.fetchall()
    if parties:
        f.append(Paragraph("Parties", h2))
        f.append(ListFlowable([ListItem(Paragraph(f"<b>{_e(sd)}</b> — {_e(pn)}: {_e(role)}", body))
                               for sd, pn, role in parties], bulletType="bullet", leftIndent=10))

    cur.execute("""SELECT cause, against_parties, basis FROM matter_causes WHERE matter_code=%s
                   AND provenance_level='verified' ORDER BY id""", (mc,))
    causes = cur.fetchall()
    if causes:
        f.append(Paragraph("Causes of action", h2))
        f.append(ListFlowable([ListItem(Paragraph(f"<b>{_e(ca)}</b> — vs {_e(ag)}. {_e(bs)}", body))
                               for ca, ag, bs in causes], bulletType="bullet", leftIndent=10))

    cur.execute("""SELECT statement, source_id FROM matter_facts WHERE matter_code=%s
                   AND provenance_level='verified' ORDER BY (source_id ~ '^[0-9]+$') DESC, source_id, id""", (mc,))
    facts = cur.fetchall()
    f.append(Paragraph(f"Verified facts — the document-proven record ({len(facts)})", h2))
    for i, (st, src) in enumerate(facts, 1):
        tag = f' <font color="#2563eb">[Annex doc:{_e(src)}]</font>' if src else ""
        f.append(Paragraph(f"{i}. {_e(st)}{tag}", body))

    cur.execute("""SELECT DISTINCT cf.forum_code, am.name, cf.remedy FROM client_issues ci
                   JOIN case_forums cf ON cf.issue_no=ci.issue_no
                   LEFT JOIN agency_mandates am ON am.code=cf.forum_code
                   WHERE %s = ANY(ci.maps_to_matters) ORDER BY cf.forum_code""", (mc,))
    forums = cur.fetchall()
    if forums:
        f.append(Paragraph("Forum routing — where this can be pressed", h2))
        f.append(ListFlowable([ListItem(Paragraph(f"<b>{_e(fc)}</b> ({_e(nm)}): {_e(rem)}", body))
                               for fc, nm, rem in forums], bulletType="bullet", leftIndent=10))

    cur.execute("""SELECT d.id, coalesce(d.original_filename,d.smart_filename,d.file_name,'?'),
                   d.drive_link, d.drive_file_id, d.file_path,
                   (SELECT count(*) FROM matter_facts mf WHERE mf.provenance_level='verified'
                      AND mf.source_kind='doc' AND mf.source_id=d.id::text) nf
                   FROM documents d WHERE d.matter_code=%s ORDER BY nf DESC, d.id""", (mc,))
    docs = cur.fetchall()
    f.append(Paragraph(f"Annexes — all documents on file ({len(docs)})", h2))
    for did, fn, dl, drid, p, nf in docs:
        mark = f"[{nf} facts] " if nf else ""
        f.append(Paragraph(f"<b>doc:{did}</b> {mark}{_e(fn)}<br/>"
                           f'<font color="#2563eb" size="7">{_e(_link(dl, drid, p))}</font>', body))

    cur.execute("SELECT provenance_level, count(*) FROM matter_facts WHERE matter_code=%s GROUP BY 1", (mc,))
    pv = dict(cur.fetchall())
    f.append(Paragraph(f"Coverage: verified {pv.get('verified',0)} · operator-asserted {pv.get('operator',0)} "
                       f"· inferred {pv.get('inferred_strong',0)+pv.get('inferred_weak',0)}. "
                       "Operator/inferred items are NOT in the verified record above; confirm before relying.", note))

    SimpleDocTemplate(path, pagesize=letter, topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                      title=f"{mc} case brief").build(f)
    return len(facts), len(docs)


def send(mc, path):
    tok = _tok()
    if not tok:
        print("[send] no TELEGRAM_BOT_TOKEN"); return False
    cap = f"{mc} — case brief, {date.today().isoformat()}"
    r = subprocess.run(["curl", "-s", "-F", f"chat_id={CHAT}", "-F", f"caption={cap}",
                        "-F", f"document=@{path}", f"https://api.telegram.org/bot{tok}/sendDocument"],
                       capture_output=True, text=True)
    ok = '"ok":true' in r.stdout
    print("[send] sent ✓ to Telegram" if ok else f"[send] FAILED: {r.stdout[:200]}")
    return ok


def main():
    mc = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "MWK-CV26360"
    path = f"/tmp/case_{mc}.pdf"
    nf, nd = build(mc, path)
    print(f"[case-pdf] {mc}: {nf} verified facts, {nd} annexes → {path}")
    if "--send" in sys.argv:
        send(mc, path)


if __name__ == "__main__":
    main()
