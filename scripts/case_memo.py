#!/usr/bin/env python3
"""case_memo.py — all-in-one legal ACTION MEMO for a matter → Telegram. Local-LLM + grounded. $0.

The decision-grade output: an analyst-written memo (status · substantive allegations · pattern &
strategy vs the broader estate · legal analysis w/ governing law · recommended next actions w/ draft
language · gaps) reasoned over the matter's VERIFIED facts + GOVERNING LAW + RELATED matters, then
grounded appendices (chronology, key facts, annexes WITH excerpts, coverage). The memo body is DERIVED
REASONING (labeled, counsel-vetted); the appendices are the cited record. Runs on the in-house Ollama
tier. Where the record lacks substance, the memo is instructed to write GAP rather than invent.

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

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://100.117.118.47:11434")
MODEL = os.environ.get("VERIFY_WORKER_OLLAMA_MODEL", "qwen2.5:7b-instruct")
CHAT = "6513067717"


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


def _ollama(prompt):
    body = {"model": MODEL, "stream": False, "options": {"temperature": 0.4}, "prompt": prompt}
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read()).get("response", "").strip()


def build(mc, path):
    c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("SELECT title, coalesce(forum,court_or_agency,'') FROM matters WHERE matter_code=%s", (mc,))
    title, forum = cur.fetchone() or ("", "")
    cur.execute("SELECT doc_id, tier FROM matter_relevance WHERE focal_matter=%s", (mc,))
    rel = dict(cur.fetchall())
    off = {d for d, t in rel.items() if t == "OFF-PROFILE"}
    cur.execute("""SELECT statement, source_id FROM matter_facts WHERE matter_code=%s AND provenance_level='verified'
                   ORDER BY (source_id ~ '^[0-9]+$') DESC, source_id, id""", (mc,))
    facts = [(s, src) for s, src in cur.fetchall() if not (src and src.isdigit() and int(src) in off)]
    factstr = "\n".join(f"- {s} [doc:{src}]" for s, src in facts)[:11000]
    laws = []
    for lf in _forums(forum):
        try:
            for cit, txt, vf, d in retrieve_chunks(lf, (title or "") + " " + factstr[:400], 2):
                laws.append(f"[{lf} {cit}] {txt.strip()[:240]}")
        except Exception:
            pass
    lawstr = "\n".join(laws)[:2500]
    cur.execute("""SELECT doc_matter, count(*) FROM matter_relevance WHERE focal_matter=%s AND tier='RELATED'
                   AND doc_matter IS NOT NULL AND doc_matter<>%s GROUP BY 1 ORDER BY 2 DESC LIMIT 6""", (mc, mc))
    relstr = ", ".join(f"{m} ({n})" for m, n in cur.fetchall())

    prompt = f"""You are a Philippine litigation strategist preparing an ACTION MEMO for counsel on
matter {mc} ({title}; forum: {forum}). Use ONLY the material below. Where the record lacks something
needed, write 'GAP: ...' — do NOT invent. Be concrete and concise. Produce these sections:

A. STATUS & POSTURE (2-3 sentences)
B. SUBSTANTIVE ALLEGATIONS — what the underlying complaint actually alleges + the evidence; if the
   specific allegations/evidence are NOT in the facts, write 'GAP: underlying complaint substance not in record — obtain it.'
C. PATTERN & STRATEGY — how this connects to the broader estate / CV-26360 reivindicatory action (use RELATED MATTERS)
D. LEGAL ANALYSIS — strengths, risks, and the governing provisions (cite the GOVERNING LAW excerpts)
E. RECOMMENDED NEXT ACTIONS — prioritized, with short draft language where useful
F. GAPS & VERIFICATION NEEDED

VERIFIED FACTS:
{factstr}

GOVERNING LAW (excerpts):
{lawstr or '(none loaded for these forums)'}

RELATED MATTERS (share parties/property): {relstr or '(none)'}"""
    memo = _ollama(prompt)
    if os.environ.get("MEMO_PRINT"):
        print(memo + "\n" + "=" * 60)

    s = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=s["Heading1"], fontSize=15, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=s["BodyText"], fontSize=9, textColor=colors.HexColor("#6b7280"))
    h2 = ParagraphStyle("h2", parent=s["Heading2"], fontSize=12, spaceBefore=12, spaceAfter=4,
                        textColor=colors.HexColor("#1e293b"))
    bdy = ParagraphStyle("bdy", parent=s["BodyText"], fontSize=9.5, leading=13)
    note = ParagraphStyle("note", parent=bdy, fontSize=8, textColor=colors.HexColor("#6b7280"))
    f = [Paragraph(f"{_e(mc)} — Action Memo", h1),
         Paragraph(f"{_e(title)} &nbsp;·&nbsp; {_e(forum)}", sub),
         Paragraph("Sections A–F are DERIVED REASONING (counsel-vetted, not verified fact); the "
                   "appendices are the cited record.", note), Spacer(1, 6)]
    for line in memo.split("\n"):
        ln = line.strip()
        if not ln:
            continue
        st = h2 if (len(ln) > 1 and ln[0] in "ABCDEF" and ln[1] in ". ") else bdy
        f.append(Paragraph(_e(ln), st))

    # Appendix 1: chronology
    tl = [e for e in timeline(cur, mc) if not (e[4] and str(e[4]).isdigit() and int(e[4]) in off)]
    f.append(Paragraph(f"Appendix A — Chronology ({len(tl)})", h2))
    for key, disp, kind, text, src in tl:
        lab = "" if kind == "event" else "[submission] "
        f.append(Paragraph(f"<b>{disp}</b> &nbsp; {lab}{_e(text[:160])}{(' [doc:'+_e(src)+']') if src else ''}", bdy))
    # Appendix 2: annexes with excerpts
    cur.execute("""SELECT d.id, coalesce(d.original_filename,d.smart_filename,'?'), d.drive_link, d.drive_file_id,
                   d.file_path, left(coalesce(d.extracted_text,''),200),
                   (SELECT count(*) FROM matter_facts mf WHERE mf.provenance_level='verified' AND mf.source_kind='doc' AND mf.source_id=d.id::text) nf
                   FROM documents d WHERE d.matter_code=%s ORDER BY nf DESC, d.id""", (mc,))
    docs = [r for r in cur.fetchall() if r[0] not in off]
    f.append(Paragraph(f"Appendix B — Annexes with excerpts ({len(docs)})", h2))
    for did, fn, dl, drid, p, exc, nf in docs:
        link = dl or (f"https://drive.google.com/file/d/{drid}/view" if drid else p) or ""
        f.append(Paragraph(f"<b>doc:{did}</b> {_e(fn[:54])} {('['+str(nf)+'f]') if nf else ''}<br/>"
                           f"<font size='7' color='#6b7280'>{_e(' '.join(exc.split())[:150])}…</font><br/>"
                           f"<font size='7' color='#2563eb'>{_e(link)}</font>", bdy))
    cur.execute("SELECT provenance_level, count(*) FROM matter_facts WHERE matter_code=%s GROUP BY 1", (mc,))
    pv = dict(cur.fetchall())
    f.append(Paragraph(f"Coverage: verified {pv.get('verified',0)} · operator {pv.get('operator',0)} · "
                       f"inferred {pv.get('inferred_strong',0)+pv.get('inferred_weak',0)}.", note))
    SimpleDocTemplate(path, pagesize=letter, topMargin=0.7*inch, bottomMargin=0.7*inch, title=f"{mc} action memo").build(f)
    return len(facts), len(docs)


def main():
    mc = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "MWK-ARTA-1891"
    path = f"/tmp/memo_{mc}.pdf"
    nf, nd = build(mc, path)
    print(f"[case-memo] {mc}: {nf} verified facts, {nd} annexes → {path}")
    if "--send" in sys.argv:
        tok = _tok()
        r = subprocess.run(["curl", "-s", "-F", f"chat_id={CHAT}", "-F", f"caption={mc} — Action Memo",
                            "-F", f"document=@{path}", f"https://api.telegram.org/bot{tok}/sendDocument"],
                           capture_output=True, text=True)
        print("[send] sent ✓" if '"ok":true' in r.stdout else f"[send] FAIL {r.stdout[:150]}")


if __name__ == "__main__":
    main()
