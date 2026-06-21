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
                   FROM documents d WHERE d.matter_code=%s ORDER BY nf DESC, d.id""", (mc,))
    annex = [(did, fn, *_avail(dl, drid, p), exc, nf) for did, fn, dl, drid, p, exc, nf in cur.fetchall() if did not in off]
    missing = [a for a in annex if not a[3]]

    is_admin = bool(_forums(forum)) and mc not in JUDICIAL
    usable = ("Not yet — source documents missing/unavailable" if missing else
              "With additional verification — operator/counsel review required")

    # Discerning reasoning: the multi-step legal harness (element-map → draft → self-critique) on the 14B
    _la = _legal_analyze(mc)
    emap, derived = _la["element_map"], _la["analysis"]
    if os.environ.get("MEMO_PRINT"):
        print("ELEMENT MAP:\n" + emap + "\n---\nANALYSIS:\n" + derived + "\n" + "=" * 60)

    s = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=s["Heading1"], fontSize=15, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=s["BodyText"], fontSize=8.5, textColor=colors.HexColor("#6b7280"))
    h2 = ParagraphStyle("h2", parent=s["Heading2"], fontSize=12, spaceBefore=11, spaceAfter=3, textColor=colors.HexColor("#1e293b"))
    bdy = ParagraphStyle("bdy", parent=s["BodyText"], fontSize=9.5, leading=13)
    note = ParagraphStyle("note", parent=bdy, fontSize=8, textColor=colors.HexColor("#6b7280"))
    warn = ParagraphStyle("warn", parent=bdy, textColor=colors.HexColor("#b91c1c"))
    fence = ParagraphStyle("fence", parent=bdy, backColor=colors.HexColor("#f3f4f6"), borderPadding=4)
    f = []

    f.append(Paragraph(f"{_e(mc)} — Action Memo", h1))
    f.append(Paragraph(f"{_e(title)}<br/>Forum: {_e(forum)} &nbsp;·&nbsp; Docket: {_e(docket)} &nbsp;·&nbsp; "
                       f"Generated by LandTek (assisted) — operator review required", sub))
    f.append(Paragraph(f"<b>Usable for filing?</b> {_e(usable)} &nbsp;|&nbsp; "
                       f"<b>Verification:</b> {len(facts)} verified facts; {len(missing)} source(s) unavailable", sub))
    f.append(Spacer(1, 4))

    # Relationship / strict separation
    f.append(Paragraph("Relationship to other matters (separation)", h2))
    if is_admin:
        f.append(Paragraph(f"&bull; <b>This matter ({_e(mc)})</b> is an ADMINISTRATIVE red-tape / records-obstruction "
                           f"track ({_e(forum)}). It is NOT a court case and cannot itself decide any judicial matter.", bdy))
        f.append(Paragraph("&bull; <b>CV-26360</b> is a SEPARATE judicial proceeding (RTC; Aug-12-2026 testimony). "
                           "Its outcome is independent of this matter.", bdy))
        f.append(Paragraph("&bull; <b>Strategic value (note — counsel review):</b> this matter can generate "
                           "<i>contemporaneous evidence of LGU Mercedes obstruction</i> usable as pattern evidence in "
                           "CV-26360 manifestations and the larger Accion Reivindicatoria — nothing more.", note))
    if related:
        f.append(Paragraph("&bull; Corpus cross-refs (shared parties/property, distinct matters): "
                           + _e(relstr), note))

    # Substantive allegations + key verified facts (provenance-tagged, with excerpts)
    f.append(Paragraph(f"Verified facts &amp; substantive allegations — provenance-tagged ({len(facts)})", h2))
    for s_, e_, src in facts[:16]:
        f.append(Paragraph(f"&bull; {_e(s_)} <font size='7' color='#059669'>[VERIFIED · doc:{_e(src)}]</font>", bdy))
        if e_:
            f.append(Paragraph(f"&nbsp;&nbsp;<font size='7' color='#6b7280'>“{_e(' '.join(e_.split())[:150])}”</font>", note))
    if len(facts) > 16:
        f.append(Paragraph(f"…+{len(facts)-16} more verified facts (full set in the matter dossier).", note))

    # Evidence-to-element map (which verified facts prove which legal elements; gaps flagged)
    f.append(Paragraph("Evidence-to-element map — DERIVED (facts → elements; unsupported elements = gaps)", h2))
    for ln in emap.split("\n"):
        ln = ln.strip()
        if ln:
            f.append(Paragraph(_e(ln), bdy))

    # Derived block — fenced
    f.append(Paragraph("Analysis &amp; recommendations — DERIVED REASONING (LandTek-assisted; counsel must verify)", h2))
    for line in derived.split("\n"):
        ln = line.strip()
        if ln:
            f.append(Paragraph(_e(ln), fence if ln[:1].isdigit() or ln.isupper() or ":" in ln[:22] else bdy))

    # Gaps & verification
    f.append(Paragraph("Gaps &amp; verification required", h2))
    if missing:
        f.append(Paragraph(f"&#9888; {len(missing)} cited source document(s) are NOT available "
                           f"(no link/file): " + ", ".join(f"doc:{a[0]}" for a in missing) + " — retrieve before filing.", warn))
    else:
        f.append(Paragraph("&bull; All cited source documents are available (link/file confirmed).", bdy))
    cur.execute("SELECT provenance_level, count(*) FROM matter_facts WHERE matter_code=%s GROUP BY 1", (mc,))
    pv = dict(cur.fetchall())
    f.append(Paragraph(f"&bull; Provenance: verified {pv.get('verified',0)} · operator-asserted "
                       f"{pv.get('operator',0)} (not in the record above) · inferred "
                       f"{pv.get('inferred_strong',0)+pv.get('inferred_weak',0)} (excluded). See the DERIVED block for issue-specific gaps.", note))

    # Appendices
    tl = [e for e in timeline(cur, mc) if not (e[4] and str(e[4]).isdigit() and int(e[4]) in off)]
    f.append(Paragraph(f"Appendix A — Chronology ({len(tl)})", h2))
    for key, disp, kind, text, src in tl:
        lab = "" if kind == "event" else "[submission] "
        f.append(Paragraph(f"<b>{disp}</b> &nbsp; {lab}{_e(text[:150])}{(' [doc:'+_e(src)+']') if src else ''}", bdy))
    f.append(Paragraph(f"Appendix B — Annexes (with excerpts &amp; availability) ({len(annex)})", h2))
    for did, fn, link, ok, exc, nf in annex:
        flag = "" if ok else " <font color='#b91c1c'>[SOURCE NOT AVAILABLE]</font>"
        f.append(Paragraph(f"<b>doc:{did}</b> {_e(fn[:54])} {('['+str(nf)+'f]') if nf else ''}{flag}<br/>"
                           f"<font size='7' color='#6b7280'>{_e(' '.join(exc.split())[:140])}…</font><br/>"
                           f"<font size='7' color='#2563eb'>{_e(link)}</font>", bdy))
    f.append(Spacer(1, 6))
    f.append(Paragraph("LandTek Assisted — Operator/Counsel Review Required. Verified facts are corpus-grounded; "
                       "the Analysis &amp; Recommendations block is derived reasoning, not legal advice.", note))

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
