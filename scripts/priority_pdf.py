#!/usr/bin/env python3
"""priority_pdf.py — generate the MWK priority-items PDF and push it to Telegram. $0, no LLM.

Pulls live deadlines from matters.next_deadline (the clean structured source) + a curated
priority structure, renders a one-page PDF via reportlab, and sends it to Jonathan's Telegram
via the bot sendDocument endpoint.

  python3 scripts/priority_pdf.py            # build the PDF only (prints path)
  python3 scripts/priority_pdf.py --send      # build + push to Telegram
"""
import argparse
import html
import os
import subprocess
from datetime import date, datetime

import psycopg2
import psycopg2.extras
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
CHAT = "6513067717"
OUTDIR = "/root/landtek/drafts"
NORTH = date(2026, 8, 12)


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


def fetch_deadlines(today):
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""SELECT matter_code, coalesce(current_stage,status) AS label, next_deadline
                     FROM matters WHERE case_file='MWK-001' AND next_deadline IS NOT NULL
                    ORDER BY next_deadline""")
    rows = cur.fetchall(); conn.close()
    out = []
    for r in rows:
        out.append({**r, "days": (r["next_deadline"] - today).days})
    return out


def build(today):
    dls = fetch_deadlines(today)
    overdue = [d for d in dls if d["days"] < 0]
    upcoming = [d for d in dls if d["days"] >= 0]
    os.makedirs(OUTDIR, exist_ok=True)
    path = os.path.join(OUTDIR, f"MWK_priorities_{today.isoformat()}.pdf")

    s = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=s["Heading1"], fontSize=17, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=s["BodyText"], fontSize=9, textColor=colors.HexColor("#6b7280"))
    h2 = ParagraphStyle("h2", parent=s["Heading2"], fontSize=12,
                        textColor=colors.HexColor("#1e293b"), spaceBefore=12, spaceAfter=4)
    body = ParagraphStyle("body", parent=s["BodyText"], fontSize=10, leading=14)
    red = ParagraphStyle("red", parent=body, textColor=colors.HexColor("#dc2626"))

    def bullets(items, style=body):
        return ListFlowable([ListItem(Paragraph(t, style), leftIndent=12) for t in items],
                            bulletType="bullet", start="•")

    f = []
    f.append(Paragraph("MWK-001 &mdash; Priority Items", h1))
    f.append(Paragraph(f"As of {today.isoformat()} &nbsp;·&nbsp; North star: testimony in "
                       f"<b>{(NORTH - today).days} days</b> (Aug 12, 2026 &mdash; CV-26360, MTC Mercedes)", sub))
    f.append(Spacer(1, 6))

    f.append(Paragraph("1. Overdue — act / confirm now", h2))
    if overdue:
        f.append(bullets([f"<b>{_e(d['matter_code'])}</b> — {_e(d['label'])} "
                          f"(<b>{-d['days']}d overdue</b>, was due {d['next_deadline'].isoformat()})"
                          for d in overdue], red))
    else:
        f.append(Paragraph("None.", body))

    f.append(Paragraph("2. CV-26360 — live Summary-Judgment fight (the Aug 12 north star)", h2))
    f.append(bullets([
        "Active drafting with Atty. Barandon: Motion for Summary Judgment, Reply, Complaint + Judicial Affidavit.",
        f"Mediation impasse &rarr; trial track. Next deadline "
        f"{(upcoming[0]['next_deadline'].isoformat() + f' (in {upcoming[0]['days']}d)') if upcoming else '2026-08-01'}; "
        "testimony Aug 12.",
        "SJ kill-shot: the 1992 SPA grants only &lsquo;to negotiate&rsquo;, not to sell &rarr; the 2016 Balane deed is void.",
    ]))

    f.append(Paragraph("3. Evidence gaps blocking the SJ pack", h2))
    f.append(bullets([
        "<b>2016 Balane Deed of Absolute Sale</b> — certified copy still not in the corpus (the operative void instrument).",
        "Certified copies of T-52540 / T-52539 / T-31298 / T-4494; exhibit-to-claim linking for the void chain.",
    ]))

    f.append(Paragraph("4. ARTA campaign — awaiting responses (need follow-up dates)", h2))
    f.append(bullets([
        "0690 / 0792 appealed to the Office of the President + endorsed to CSC; 1210 notice-of-compliance issued; "
        "1891 / DILG referral awaiting; 1378 submitted for resolution.",
    ]))

    f.append(Paragraph("5. Data integrity — reconcile", h2))
    f.append(bullets([
        "Guardianship: matter stage says &lsquo;pending filing&rsquo; but MASTER_PLAN says <b>FILED</b> "
        "(Atty. Botor counsel of record) — stale, reconcile.",
        "148 open action items, ~82% stale / duplicated — a cleanup pass would surface the ~10–15 that actually need you.",
    ]))

    SimpleDocTemplate(path, pagesize=letter, topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                      title="MWK-001 Priority Items").build(f)
    return path


def send(path):
    tok = _tok()
    if not tok:
        print("[send] no TELEGRAM_BOT_TOKEN"); return False
    cap = f"MWK-001 priority items — {date.today().isoformat()}"
    r = subprocess.run(["curl", "-s", "-F", f"chat_id={CHAT}", "-F", f"caption={cap}",
                        "-F", f"document=@{path}",
                        f"https://api.telegram.org/bot{tok}/sendDocument"],
                       capture_output=True, text=True)
    ok = '"ok":true' in r.stdout
    print("[send] sent ✓ to Telegram" if ok else f"[send] FAILED: {r.stdout[:200]}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--today")
    a = ap.parse_args()
    today = datetime.strptime(a.today, "%Y-%m-%d").date() if a.today else date.today()
    path = build(today)
    print(f"[pdf] wrote {path} ({os.path.getsize(path)} bytes)")
    if a.send:
        send(path)


if __name__ == "__main__":
    main()
