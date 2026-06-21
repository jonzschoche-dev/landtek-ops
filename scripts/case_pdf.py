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

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chronology import timeline, parse_dates
from legal_authority import retrieve_chunks as _law_chunks

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


def _legal_forums(forum_text):
    """A matter can run in several forums (e.g. ARTA referred to CSC + DILG) — return ALL."""
    fl = (forum_text or "").lower()
    out = []
    if "arta" in fl: out.append("ARTA")
    if "csc" in fl or "civil service" in fl: out.append("CSC")
    if "ombudsman" in fl: out.append("OMBUDSMAN")
    if "dilg" in fl: out.append("DILG")
    if "agrarian" in fl or "darab" in fl: out.append("DAR-DARAB")
    if "deeds" in fl or "lra" in fl: out.append("RD-LRA")
    if any(k in fl for k in ("rtc", "mtc", " court")) and "CIVIL" not in out: out.append("CIVIL")
    return out


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

    # relevance map — label, never conflate
    cur.execute("SELECT doc_id, tier, connection, doc_matter FROM matter_relevance WHERE focal_matter=%s", (mc,))
    rel = {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}
    off_docs = {d for d, v in rel.items() if v[0] == "OFF-PROFILE"}
    warn = ParagraphStyle("warn", parent=body, textColor=colors.HexColor("#b91c1c"))

    cur.execute("""SELECT statement, source_id FROM matter_facts WHERE matter_code=%s
                   AND provenance_level='verified' ORDER BY (source_id ~ '^[0-9]+$') DESC, source_id, id""", (mc,))
    facts = cur.fetchall()
    def _off(src):
        return bool(src) and src.isdigit() and int(src) in off_docs
    clean = [(st, src) for st, src in facts if not _off(src)]
    flagged = [(st, src) for st, src in facts if _off(src)]
    # Lead with the date-ordered chronology (events from verified facts + submissions), off-profile excluded
    tl = [e for e in timeline(cur, mc) if not (e[4] and str(e[4]).isdigit() and int(e[4]) in off_docs)]
    f.append(Paragraph(f"Chronology — evidence &amp; submissions by date ({len(tl)})", h2))
    for key, disp, kind, text, src in tl:
        cite = f' <font color="#2563eb">[doc:{_e(src)}]</font>' if src else ""
        lab = "" if kind == "event" else "<b>[submission]</b> "
        f.append(Paragraph(f"<b>{disp}</b> &nbsp; {lab}{_e(text[:240])}{cite}", body))
    undated = [(st, src) for st, src in clean if not parse_dates(st)]
    if undated:
        f.append(Paragraph(f"Additional verified facts (undated) ({len(undated)})", h2))
        for st, src in undated:
            tag = f' <font color="#2563eb">[doc:{_e(src)}]</font>' if src else ""
            f.append(Paragraph(f"&bull; {_e(st)}{tag}", body))

    # Governing law — pull each forum's verbatim statute from the law library (multi-forum aware)
    lfs = _legal_forums(forum)
    if lfs:
        q = (title or "") + " " + " ".join(st for st, _ in clean[:4])
        f.append(Paragraph(f"Governing law — forum(s): {', '.join(lfs)}", h2))
        for lf in lfs:
            try:
                law = _law_chunks(lf, q, 2)
            except Exception:
                law = []
            if law:
                f.append(Paragraph(f"<b>{lf}</b> &nbsp;<font size='7' color='#6b7280'>({law[0][2]})</font>", body))
                for cit, txt, vfl, dist in law:
                    f.append(Paragraph(f"&nbsp;&nbsp;<b>{_e(cit)}</b> — {_e(txt.strip()[:240])}…", body))
            else:
                f.append(Paragraph(f"<b>{lf}</b> — statute not yet in the law library (pending official copy).", note))

    cur.execute("""SELECT DISTINCT cf.forum_code, am.name, cf.remedy FROM client_issues ci
                   JOIN case_forums cf ON cf.issue_no=ci.issue_no
                   LEFT JOIN agency_mandates am ON am.code=cf.forum_code
                   WHERE %s = ANY(ci.maps_to_matters) ORDER BY cf.forum_code""", (mc,))
    forums = cur.fetchall()
    if forums:
        f.append(Paragraph("Forum routing — where this can be pressed", h2))
        f.append(ListFlowable([ListItem(Paragraph(f"<b>{_e(fc)}</b> ({_e(nm)}): {_e(rem)}", body))
                               for fc, nm, rem in forums], bulletType="bullet", leftIndent=10))

    # Annexes, tiered by relevance — CORE = this matter's own files
    cur.execute("""SELECT d.id, coalesce(d.original_filename,d.smart_filename,d.file_name,'?'),
                   d.drive_link, d.drive_file_id, d.file_path,
                   (SELECT count(*) FROM matter_facts mf WHERE mf.provenance_level='verified'
                      AND mf.source_kind='doc' AND mf.source_id=d.id::text) nf
                   FROM documents d WHERE d.matter_code=%s ORDER BY nf DESC, d.id""", (mc,))
    core = [r for r in cur.fetchall() if r[0] not in off_docs]
    f.append(Paragraph(f"Annexes — CORE: this matter's own files ({len(core)})", h2))
    for did, fn, dl, drid, p, nf in core:
        mark = f"[{nf} facts] " if nf else ""
        f.append(Paragraph(f"<b>doc:{did}</b> {mark}{_e(fn)}<br/>"
                           f'<font color="#2563eb" size="7">{_e(_link(dl, drid, p))}</font>', body))

    related = [(d, rel[d][2], rel[d][1]) for d in rel if rel[d][0] == "RELATED"]
    if related:
        bym = {}
        for d, dm, conn in related:
            bym.setdefault(dm or "(unlinked)", []).append((d, conn))
        f.append(Paragraph(f"Related — distinct matters sharing parties/property ({len(related)} docs) "
                           "— context only, NOT this case's record", h2))
        for dm, items in sorted(bym.items(), key=lambda x: -len(x[1])):
            ex = ", ".join("doc:" + str(d) for d, _ in items[:5])
            f.append(Paragraph(f"<b>{_e(dm)}</b> — {len(items)} docs; shares {_e(items[0][1][:70])} (e.g. {ex})", body))

    ctx = [d for d in rel if rel[d][0] == "CONTEXTUAL"]
    if ctx:
        f.append(Paragraph(f"Loosely connected — {len(ctx)} docs share only a name (e.g. 'Keesey'/'Balane'); "
                           "background, not evidence in this matter.", note))

    if off_docs or flagged:
        f.append(Paragraph(f"&#9888; Flagged — possible mis-file ({len(off_docs)} docs, {len(flagged)} facts): "
                           "reads like a DIFFERENT proceeding — NOT this matter's record; verify.", h2))
        for d in sorted(off_docs):
            f.append(Paragraph(f"doc:{d} — {_e(rel[d][1])}", warn))
        for st, src in flagged:
            f.append(Paragraph(f"&#9888; {_e(st)} [doc:{_e(src)}]", warn))

    cur.execute("SELECT provenance_level, count(*) FROM matter_facts WHERE matter_code=%s GROUP BY 1", (mc,))
    pv = dict(cur.fetchall())
    f.append(Paragraph(f"Coverage: verified {pv.get('verified',0)} (record above excludes {len(flagged)} flagged) "
                       f"· operator {pv.get('operator',0)} · inferred {pv.get('inferred_strong',0)+pv.get('inferred_weak',0)}. "
                       "Operator/inferred items NOT in the record; confirm before relying.", note))

    SimpleDocTemplate(path, pagesize=letter, topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                      title=f"{mc} case brief").build(f)
    return len(clean), len(core)


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
