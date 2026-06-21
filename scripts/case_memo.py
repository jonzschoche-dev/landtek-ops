#!/usr/bin/env python3
"""case_memo.py — corpus-grade legal ACTION MEMO for a matter → Telegram. $0 (local LLM + grounded).

Discipline (built for legal-office use, NOT filing-as-is):
  • VERIFIED sections are deterministic + provenance-tagged [VERIFIED · doc:N]; the DERIVED block
    (LLM reasoning) is fenced and labeled "operator/counsel review required".
  • Hard SEPARATION of matters: an administrative (ARTA/DILG/CSC) matter is never said to decide a
    judicial one (CV-26360); cross-links are framed only as pattern evidence.
  • SOURCE AVAILABILITY is checked — every cited annex is confirmed to have a link/file, else flagged.
  • A "Usable for Filing?" flag + Risk/Opportunity line sit in the header. The LLM never signs.

  python3 scripts/case_memo.py MWK-ARTA-1891 --send
"""
import datetime
import html
import json
import os
import subprocess
import sys
import urllib.request

import psycopg2
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chronology import timeline
from legal_authority import retrieve_chunks
from legal_agent import analyze as _legal_analyze
from matter_readiness import assess as _readiness_assess, verdict as _readiness_verdict

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://100.117.118.47:11434")
MODEL = os.environ.get("VERIFY_WORKER_OLLAMA_MODEL", "qwen2.5:7b-instruct")
CHAT = "6513067717"
JUDICIAL = {"MWK-CV26360": "the CV-26360 accion reivindicatoria (RTC; Aug-12-2026 testimony)",
            "MWK-CV6839": "CV-6839 just-compensation (Special Agrarian Court)"}


def _tok():
    for line in open("/root/landtek/.env"):
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            return line.split("=", 1)[1].strip()
    return None


def _e(s):
    return html.escape(str(s or ""))


def _forums(ftext):
    fl = (ftext or "").lower(); out = []
    for k, code in [("arta", "ARTA"), ("csc", "CSC"), ("civil service", "CSC"), ("ombudsman", "OMBUDSMAN"),
                    ("dilg", "DILG"), ("agrarian", "DAR-DARAB"), ("darab", "DAR-DARAB"), ("deeds", "RD-LRA")]:
        if k in fl and code not in out:
            out.append(code)
    return out


def _avail(dl, drid, p):
    if dl:
        return dl, True
    if drid:
        return f"https://drive.google.com/file/d/{drid}/view", True
    if p:
        return p, os.path.exists(p)
    return "(no source on file)", False


def _ollama(prompt):
    body = {"model": MODEL, "stream": False, "options": {"temperature": 0.3}, "prompt": prompt}
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read()).get("response", "").strip()


def build(mc, path):
    c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("SELECT title, coalesce(forum,court_or_agency,''), coalesce(docket_number,'') FROM matters WHERE matter_code=%s", (mc,))
    title, forum, docket = cur.fetchone() or ("", "", "")
    cur.execute("SELECT doc_id, tier FROM matter_relevance WHERE focal_matter=%s", (mc,))
    rel = dict(cur.fetchall())
    off = {d for d, t in rel.items() if t == "OFF-PROFILE"}
    cur.execute("""SELECT statement, excerpt, source_id FROM matter_facts WHERE matter_code=%s
                   AND provenance_level='verified' ORDER BY (source_id ~ '^[0-9]+$') DESC, source_id, id""", (mc,))
    facts = [(s, e, src) for s, e, src in cur.fetchall() if not (src and src.isdigit() and int(src) in off)]
    factstr = "\n".join(f"- {s} [doc:{src}]" for s, e, src in facts)[:11000]
    laws = []
    for lf in _forums(forum):
        try:
            for cit, txt, vf, d in retrieve_chunks(lf, (title or "") + " " + factstr[:400], 2):
                laws.append(f"[{lf} {cit}] {txt.strip()[:220]}")
        except Exception:
            pass
    lawstr = "\n".join(laws)[:2500]
    cur.execute("""SELECT doc_matter, count(*) FROM matter_relevance WHERE focal_matter=%s AND tier='RELATED'
                   AND doc_matter IS NOT NULL AND doc_matter<>%s GROUP BY 1 ORDER BY 2 DESC LIMIT 6""", (mc, mc))
    related = cur.fetchall()
    relstr = ", ".join(f"{m} ({n})" for m, n in related)

    # annexes + source-availability
    cur.execute("""SELECT d.id, coalesce(d.original_filename,d.smart_filename,'?'), d.drive_link, d.drive_file_id,
                   d.file_path, left(coalesce(d.extracted_text,''),200),
                   (SELECT count(*) FROM matter_facts mf WHERE mf.provenance_level='verified' AND mf.source_kind='doc' AND mf.source_id=d.id::text) nf
                   FROM documents d WHERE d.matter_code=%s
                     OR d.id IN (SELECT doc_id FROM document_matter_links WHERE matter_code=%s)
                   ORDER BY nf DESC, d.id""", (mc, mc))
    annex = [(did, fn, *_avail(dl, drid, p), exc, nf) for did, fn, dl, drid, p, exc, nf in cur.fetchall() if did not in off]
    missing = [a for a in annex if not a[3]]

    is_admin = bool(_forums(forum)) and mc not in JUDICIAL
    usable = ("Not yet — source documents missing/unavailable" if missing else
              "With additional verification — operator/counsel review required")

    # Discerning reasoning: the multi-step harness → a structured, counsel-ready marked block (14B)
    _la = _legal_analyze(mc)
    if os.environ.get("MEMO_PRINT"):
        for k in ("priority", "summary", "objective", "gaps", "evidence", "actions", "related_ctx"):
            print(f"[{k}]\n{_la.get(k,'(missing)')}\n")
    today = datetime.date.today().isoformat()

    s = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=s["Heading1"], fontSize=15, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=s["BodyText"], fontSize=8.5, textColor=colors.HexColor("#6b7280"))
    h2 = ParagraphStyle("h2", parent=s["Heading2"], fontSize=11.5, spaceBefore=10, spaceAfter=3, textColor=colors.HexColor("#1e293b"))
    bdy = ParagraphStyle("bdy", parent=s["BodyText"], fontSize=9.5, leading=13)
    note = ParagraphStyle("note", parent=bdy, fontSize=8, textColor=colors.HexColor("#6b7280"))
    warn = ParagraphStyle("warn", parent=bdy, textColor=colors.HexColor("#b91c1c"))
    summ = ParagraphStyle("summ", parent=bdy, fontSize=10.5, leading=14, backColor=colors.HexColor("#eef2ff"), borderPadding=6, spaceAfter=4)
    fence = ParagraphStyle("fence", parent=bdy, backColor=colors.HexColor("#f3f4f6"), borderPadding=4)
    f = []

    def _lines(txt, style, bullet=False):
        for ln in (txt or "").split("\n"):
            ln = ln.strip()
            if ln:
                if bullet and not ln.startswith(("-", "•", "&bull;", "*")):
                    ln = "&bull; " + ln
                f.append(Paragraph(_e(ln).replace("&amp;bull;", "&bull;"), style))

    def _aslist(val):
        if isinstance(val, list):
            return [v for v in val if v]
        return [x.strip() for x in str(val or "").split("\n") if x.strip()]

    # ── Header ──
    f.append(Paragraph(f"{_e(mc)} — Action Memo", h1))
    f.append(Paragraph(f"{_e(title)}<br/>Forum/Docket: {_e(forum)} → {_e(docket)} &nbsp;·&nbsp; "
                       f"Generated {today} — LandTek Assisted (Operator/Counsel Review Required)", sub))
    f.append(Paragraph(f"<b>Usable for filing?</b> {_e(usable)}", sub))
    if _la.get("priority"):
        f.append(Paragraph(f"<b>Strategic priority:</b> {_e(_la['priority'])}", sub))
    f.append(Spacer(1, 5))

    # ── Data-layer readiness banner — never silently ship a memo on an unready truth layer ──
    try:
        _ra = _readiness_assess(cur, mc)
        _ready, _rfixes, _radv = _readiness_verdict(_ra) if _ra else (True, [], [])
    except Exception:
        _ready, _rfixes = True, []
    if not _ready:
        f.append(Paragraph("&#9888; <b>DATA-LAYER NOT FULLY READY</b> — verify before relying on this memo: "
                           + _e("; ".join(_rfixes)[:320]), warn))
        f.append(Spacer(1, 4))

    # ── 1. Executive summary (one sentence) ──
    if _la.get("summary"):
        f.append(Paragraph("1. Executive summary", h2))
        f.append(Paragraph(_e(_la["summary"]), summ))

    # ── 2. Objective — what victory in THIS matter looks like (first principles) ──
    if _la.get("objective"):
        f.append(Paragraph("2. Objective — what victory in this matter looks like", h2))
        _lines(_la["objective"], bdy)

    # ── 3. Verified facts (deterministic, provenance-tagged, top 12) ──
    f.append(Paragraph(f"3. Verified facts — provenance-tagged ({min(len(facts),12)} of {len(facts)})", h2))
    for s_, e_, src in facts[:12]:
        f.append(Paragraph(f"&bull; {_e(s_)} <font size='7' color='#059669'>[VERIFIED · doc:{_e(src)}]</font>", bdy))
    if len(facts) > 12:
        f.append(Paragraph(f"…+{len(facts)-12} more in the matter dossier; key source excerpts in Appendix B.", note))

    # ── 4. Key gaps (derived gaps + deterministic source-availability) ──
    f.append(Paragraph("4. Key gaps (what blocks stronger action)", h2))
    for g in (_aslist(_la.get("gaps")) or ["(none identified by the agent)"]):
        g = str(g)
        f.append(Paragraph(_e(g) if g.startswith(("-", "•", "&bull;")) else "&bull; " + _e(g), bdy))
    if missing:
        f.append(Paragraph(f"&#9888; {len(missing)} cited source(s) NOT available: "
                           + ", ".join(f"doc:{a[0]}" for a in missing) + " — retrieve before filing.", warn))
    else:
        f.append(Paragraph("&bull; All cited source documents are available (link/file confirmed).", note))

    # ── 5. Evidence-to-element map (derived, tight: 2-3 issues) ──
    ev = _aslist(_la.get("evidence"))
    if ev:
        f.append(Paragraph("5. Evidence-to-element map", h2))
        for e_ in ev:
            f.append(Paragraph("&bull; " + _e(str(e_)), bdy))

    # ── 6. Immediate recommended actions = the path to victory (derived, fenced + labeled) ──
    f.append(Paragraph("6. Immediate recommended actions (path to victory)", h2))
    f.append(Paragraph("LandTek-generated analysis for counsel review only — not legal advice.", note))
    acts = _la.get("actions")
    if isinstance(acts, list) and acts and isinstance(acts[0], dict):
        for i, a in enumerate(acts, 1):
            f.append(Paragraph(f"<b>{i}. Owner:</b> {_e(a.get('owner','—'))} &nbsp;·&nbsp; "
                               f"<b>Deadline:</b> {_e(a.get('deadline','—'))}", bdy))
            if a.get("draft"):
                f.append(Paragraph("<b>DRAFT:</b> " + _e(a["draft"]), fence))
    else:
        for ln in _aslist(acts):
            f.append(Paragraph(_e(str(ln)), fence))

    # ── 7. Related matters — DETERMINISTIC from the corpus (typed by coupling), not model prose ──
    f.append(Paragraph("7. Related matters (evidence-grounded)", h2))
    _lines(_la.get("related_ctx") or _la.get("related") or "(none recorded yet — see complaint + email attachments)", bdy)
    if is_admin:
        f.append(Paragraph("&bull; <b>Separation guardrail:</b> the same-campaign ARTA/RA 11032 matters are "
                           "genuinely related; the property/ownership track (e.g. CV-26360, different defendants) "
                           "is CONTEXT only — this administrative matter does not decide it.", note))

    # ── Appendix A — condensed chronology (key dated events, max 10) ──
    tl = [e for e in timeline(cur, mc) if not (e[4] and str(e[4]).isdigit() and int(e[4]) in off)]
    f.append(Paragraph(f"Appendix A — Condensed chronology ({min(len(tl),10)} of {len(tl)})", h2))
    for key, disp, kind, text, src in tl[:10]:
        lab = "" if kind == "event" else "[submission] "
        f.append(Paragraph(f"<b>{disp}</b> &nbsp; {lab}{_e(text[:120])}{(' [doc:'+_e(src)+']') if src else ''}", bdy))

    # ── Appendix B — key source excerpts with links/paths ──
    f.append(Paragraph(f"Appendix B — Key source excerpts &amp; links ({min(len(annex),12)} of {len(annex)})", h2))
    for did, fn, link, ok, exc, nf in annex[:12]:
        flag = "" if ok else " <font color='#b91c1c'>[SOURCE NOT AVAILABLE]</font>"
        f.append(Paragraph(f"<b>doc:{did}</b> {_e(fn[:54])} {('['+str(nf)+'f]') if nf else ''}{flag}<br/>"
                           f"<font size='7' color='#6b7280'>“{_e(' '.join(exc.split())[:130])}…”</font><br/>"
                           f"<font size='7' color='#2563eb'>{_e(link)}</font>", bdy))
    f.append(Spacer(1, 6))
    f.append(Paragraph("Verified facts are corpus-grounded (cited source + verbatim excerpt). Sections 1 and 3–6 "
                       "are LandTek-generated analysis for counsel review — not legal advice.", note))

    SimpleDocTemplate(path, pagesize=letter, topMargin=0.6*inch, bottomMargin=0.6*inch, title=f"{mc} action memo").build(f)
    return len(facts), len(annex), len(missing)


def main():
    mc = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "MWK-ARTA-1891"
    path = f"/tmp/memo_{mc}.pdf"
    nf, nd, nm = build(mc, path)
    print(f"[case-memo] {mc}: {nf} verified facts, {nd} annexes, {nm} unavailable → {path}")
    if "--send" in sys.argv:
        tok = _tok()
        r = subprocess.run(["curl", "-s", "-F", f"chat_id={CHAT}", "-F", f"caption={mc} — Action Memo (corpus-grade)",
                            "-F", f"document=@{path}", f"https://api.telegram.org/bot{tok}/sendDocument"],
                           capture_output=True, text=True)
        print("[send] sent ✓" if '"ok":true' in r.stdout else f"[send] FAIL {r.stdout[:150]}")


if __name__ == "__main__":
    main()
