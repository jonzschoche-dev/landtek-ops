#!/usr/bin/env python3
"""capabilities_pdf.py — LeoLandTek capability assessment PDF, pushed to Telegram. $0.

Honest, grounded in live metrics: what the stack SHOULD do, what it CAN do, what it NEEDS,
and what it'll take. Reflects the architecture problem found 2026-06-20 (no write-gate; inference
written as fact).

  python3 scripts/capabilities_pdf.py --send
"""
import argparse
import os
import subprocess
from datetime import date

import psycopg2
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
CHAT = "6513067717"
OUTDIR = "/root/landtek/drafts"


def _tok():
    try:
        for line in open("/root/landtek/.env"):
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None


def metrics():
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor()
    q = lambda s: (cur.execute(s) or cur.fetchone()[0])
    m = {
        "vf": q("SELECT count(*) FROM matter_facts WHERE provenance_level='verified'"),
        "inf": q("SELECT count(*) FROM matter_facts WHERE provenance_level<>'verified'"),
        "matters": q("SELECT count(*) FROM matters WHERE status IS NULL OR status NOT IN ('closed','archived')"),
        "dl": q("SELECT count(*) FROM matters WHERE next_deadline IS NOT NULL AND (status IS NULL OR status NOT IN ('closed','archived'))"),
        "docs": q("SELECT count(*) FROM documents"),
        "ents": q("SELECT count(*) FROM entities WHERE type='person'"),
        "chunks": q("SELECT count(*) FROM rag_local"),
        "issues": q("SELECT count(*) FROM client_issues"),
    }
    c.close()
    return m


def build():
    m = metrics()
    pct = round(100 * m["vf"] / max(1, m["vf"] + m["inf"]), 1)
    os.makedirs(OUTDIR, exist_ok=True)
    path = os.path.join(OUTDIR, f"LeoLandTek_capabilities_{date.today().isoformat()}.pdf")
    s = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=s["Heading1"], fontSize=17, spaceAfter=2)
    subt = ParagraphStyle("subt", parent=s["BodyText"], fontSize=9, textColor=colors.HexColor("#6b7280"))
    h2 = ParagraphStyle("h2", parent=s["Heading2"], fontSize=12.5,
                        textColor=colors.HexColor("#1e293b"), spaceBefore=12, spaceAfter=4)
    body = ParagraphStyle("body", parent=s["BodyText"], fontSize=9.5, leading=13)
    lead = ParagraphStyle("lead", parent=body, textColor=colors.HexColor("#b45309"))

    def bl(items):
        return ListFlowable([ListItem(Paragraph(t, body), leftIndent=10) for t in items],
                            bulletType="bullet", start="•")

    f = []
    f.append(Paragraph("LeoLandTek — Capability Assessment", h1))
    f.append(Paragraph(f"{date.today().isoformat()} &nbsp;·&nbsp; what it should do · can do · needs · "
                       "what it will take", subt))
    f.append(Spacer(1, 6))
    f.append(Paragraph(
        f"<b>The one-line truth:</b> today it is a strong <b>storage-and-retrieval</b> system with a "
        f"thin, mostly-untrustworthy <b>knowledge</b> layer — <b>{m['vf']} verified facts vs "
        f"{m['inf']:,} inferred ({pct}% trustworthy)</b>. The work ahead is turning what it STORES "
        f"into what it KNOWS.", lead))

    f.append(Paragraph("1. What it SHOULD do (the target)", h2))
    f.append(bl([
        "<b>Comprehend, not just store</b> — read a pleading, title, or letter and KNOW its parties, "
        "causes, dates, and obligations, each cited to the source.",
        "<b>Never assert inference as fact</b> — every claim cites a document or is marked unknown.",
        "<b>Track your real world</b> — every issue, matter, party, deadline, ₱-value, and how they "
        "relate (which case gates which, what cascades from what).",
        "<b>Be proactive</b> — surface what is due, overdue, or at risk, without being asked.",
        "<b>Decipher structure</b> — a multi-defendant, multi-cause case represented as it actually is.",
        "<b>Reason about leverage</b> — e.g. know that the guardianship grant unlocks the ₱20M DAR "
        "collection; prioritise by value and impact.",
        "<b>Self-maintain</b> — close finished tasks, reconcile state, stay current.",
        "<b>Drive recovery + revenue</b> — push the ₱20M collection, the title recovery, asset monetisation.",
        "<b>Run cheaply</b> — deterministic $0 engines do the standing work; LLM credits go only where "
        "they convert inference into cited, verified knowledge.",
    ]))

    f.append(Paragraph("2. What it CAN do today", h2))
    f.append(bl([
        f"<b>Store + retrieve at scale</b> — {m['docs']:,} documents, {m['chunks']:,} RAG chunks, "
        f"{m['ents']:,} de-duplicated person-entities (the conflation/mis-filing was fixed).",
        "<b>Ground-truth substrate built</b> — auto-generated SYSTEM_CONSTITUTION (verified facts + the "
        "void-SPA keystone), a cross-client sentinel that won't mix MWK / Paracale / NIBDC.",
        f"<b>Proactive deadline awareness</b> — the engine + daily digest now lead with what's due "
        f"(it caught 2 silently-overdue items). But only {m['dl']} of {m['matters']} matters carry a date.",
        f"<b>Your spine encoded</b> — the {m['issues']}-issue inventory as the canonical registry; the "
        "₱20M valued; the guardianship gate modelled; CV-26360 partially deciphered.",
        "<b>Output discipline for Leo</b> — the answer-gate blocks fabricated citations / ungrounded "
        "cascades (built + tested; not yet wired live — Leo is inactive pending credits).",
        f"<b>The honest limit</b> — only {m['vf']} verified facts vs {m['inf']:,} inferred. The "
        "knowledge layer has <b>no write-gate</b>, so inference can be written as fact (it was). Until "
        "that's fixed, the knowledge layer cannot be trusted.",
    ]))

    f.append(Paragraph("3. What it NEEDS", h2))
    f.append(bl([
        "<b>THE BLOCKER — a write-gate / provenance discipline.</b> 'verified' must require a cited "
        "source span; 'operator' (your assertion) and 'inferred' are separate, lower tiers. Nothing "
        "downstream is trustworthy until this exists.",
        "<b>Comprehension</b> — read the operative pleadings + key documents into cited verified facts "
        "(this is what turns the 5,183 inferred into trustworthy knowledge).",
        "<b>The structured legal model populated</b> — parties, causes, relationships across ALL matters.",
        "<b>The untracked issues stood up</b> — #3 tax assessments, #4 illegal structures, #10 "
        "Sangguniang Bayan (real grievances, 41 docs, zero matters today).",
        "<b>Maintenance loops</b> — task closure (148 stale items), state reconciliation, deadline backfill.",
        "<b>Leo wired + activated</b>, and <b>Anthropic credits</b> for the targeted comprehension reads.",
    ]))

    f.append(Paragraph("4. What it will TAKE (the path)", h2))
    f.append(bl([
        "<b>Phase 0 — Fix the architecture ($0, days):</b> the write-gate + provenance re-tiering + an "
        "audit test that flags every mis-labelled row. Nothing else is trustworthy until this lands.",
        "<b>Phase 1 — Stand up the truth ($0 + targeted credits):</b> replicate the spine + decipher "
        "across matters from your ground truth; targeted comprehension reads of the operative pleadings "
        "(cheap, citable). This is where 34 verified facts becomes hundreds.",
        "<b>Phase 2 — Maintenance + proactivity ($0):</b> close the task backlog, backfill deadlines, "
        "wire the spine into every surface (digest, dashboard, PDFs).",
        "<b>Phase 3 — Activate Leo (credits + wiring):</b> discernment-gated, grounded replies. The "
        "wiring is built and waiting.",
        "<b>Phase 4 — Leverage + recovery (ongoing):</b> drive the ₱20M collection via the guardianship "
        "gate, the SJ / title recovery, asset monetisation.",
        "<b>Cost reality:</b> Phase 0 and most of Phase 2 are $0 (deterministic). The verified-knowledge "
        "build and Leo are credit-bounded but TARGETED (pleadings, not corpus-wide) — not the old burn. "
        "The simulator (the money pit) stays dead.",
    ]))
    f.append(Spacer(1, 6))
    f.append(Paragraph(
        "<b>Bottom line:</b> the foundation is built. The missing pieces are (1) the discipline that "
        "makes the knowledge layer trustworthy, and (2) the targeted comprehension that fills it. Fix "
        "the architecture, then spend credits only where they convert inference into cited fact — "
        "that is the whole road.", body))

    SimpleDocTemplate(path, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                      title="LeoLandTek Capability Assessment").build(f)
    return path


def send(path):
    tok = _tok()
    if not tok:
        print("[send] no token"); return False
    cap = f"LeoLandTek — capability assessment ({date.today().isoformat()})"
    r = subprocess.run(["curl", "-s", "-F", f"chat_id={CHAT}", "-F", f"caption={cap}",
                        "-F", f"document=@{path}", f"https://api.telegram.org/bot{tok}/sendDocument"],
                       capture_output=True, text=True)
    print("[send] sent ✓" if '"ok":true' in r.stdout else f"[send] FAILED: {r.stdout[:200]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    a = ap.parse_args()
    p = build()
    print(f"[pdf] wrote {p} ({os.path.getsize(p)} bytes)")
    if a.send:
        send(p)


if __name__ == "__main__":
    main()
