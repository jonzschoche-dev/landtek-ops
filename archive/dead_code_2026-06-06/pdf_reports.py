#!/usr/bin/env python3
"""PDF report generator — deploy_109.

Generates landscape-quality case briefings as PDFs from existing data:
  - clients.client_intelligence_summary + goals + risks + gaps
  - top verified entities by mention count
  - case assets ledger (TCT/OCT)
  - recent chat_notes filtered to verified + corroborated
  - top action items + open inquiries

Usage:
  python3 pdf_reports.py --case MWK-001                 # generates + DMs to Jonathan
  python3 pdf_reports.py --case MWK-001 --no-send       # generates only
  python3 pdf_reports.py --case MWK-001 --out /path     # custom output path

Powered by weasyprint (HTML+CSS → PDF).
"""
import argparse
import os
import sys
import urllib.request
import urllib.parse
import mimetypes
from datetime import datetime, timezone
from html import escape

import psycopg2
import psycopg2.extras

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
JONATHAN_TG_ID = "6513067717"


def _token():
    for l in open("/root/landtek/.env"):
        if l.startswith("TELEGRAM_BOT_TOKEN="):
            return l.split("=", 1)[1].strip()


def tg_send_document(file_path, caption=""):
    """Send a file (PDF) to Jonathan via Telegram sendDocument."""
    tok = _token()
    if not tok:
        return False
    # Use multipart/form-data manually
    import requests
    with open(file_path, "rb") as f:
        files = {"document": (os.path.basename(file_path), f, "application/pdf")}
        data = {"chat_id": JONATHAN_TG_ID, "caption": caption[:1024], "parse_mode": "HTML"}
        try:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendDocument",
                              data=data, files=files, timeout=60)
            return r.status_code == 200
        except Exception as e:
            print(f"  tg send_document failed: {e}", file=sys.stderr)
            return False


CSS = """
@page { size: A4; margin: 1.4cm 1.3cm 1.6cm 1.3cm; @bottom-center { content: counter(page) " / " counter(pages); font-size: 9pt; color: #888; } }
body { font-family: 'Helvetica', sans-serif; color: #1c2333; font-size: 10.5pt; line-height: 1.45; }
h1 { font-size: 22pt; color: #143d68; margin: 0 0 0.2em 0; }
h2 { font-size: 14pt; color: #143d68; margin: 1em 0 0.4em 0; border-bottom: 2px solid #c4d3e6; padding-bottom: 0.2em; }
h3 { font-size: 11pt; color: #2b5a8c; margin: 0.7em 0 0.3em 0; }
.meta { color: #677788; font-size: 9.5pt; margin-bottom: 1.2em; }
.pill { display: inline-block; padding: 0.1em 0.55em; border-radius: 0.5em; background: #eaf2fb; font-size: 9pt; color: #2b5a8c; margin-right: 4px; }
.pill.critical { background: #fdecea; color: #b3261e; }
.pill.high { background: #fff4e5; color: #b66d00; }
.pill.medium { background: #fffae5; color: #946d00; }
.summary { padding: 0.6em 0.9em; background: #f6f8fb; border-left: 4px solid #2b5a8c; margin: 0.5em 0 0.8em 0; }
.kv { width: 100%; border-collapse: collapse; }
.kv th { text-align: left; background: #f0f4fa; padding: 0.3em 0.5em; font-weight: 600; font-size: 9.5pt; }
.kv td { padding: 0.3em 0.5em; border-bottom: 1px solid #e6ebf2; font-size: 9.5pt; vertical-align: top; }
.tag-V { color: #1a7a3a; font-weight: 600; }
.tag-C { color: #946d00; }
.tag-I { color: #5a6a82; }
.tag-U { color: #b3261e; }
.bullet { margin: 0.3em 0; padding-left: 1em; }
.footer { font-size: 8pt; color: #888; margin-top: 1em; border-top: 1px solid #ddd; padding-top: 0.4em; }
.tag-pill { font-size: 8.5pt; padding: 1px 6px; border-radius: 3px; background: #eaf2fb; color: #2b5a8c; }
.tag-pill.V { background: #e3f5e9; color: #1a7a3a; }
.tag-pill.C { background: #fff4e5; color: #946d00; }
.tag-pill.I { background: #ebeef4; color: #5a6a82; }
.tag-pill.U { background: #fdecea; color: #b3261e; }
"""

PROV_TAG = {
    "verified": "V",
    "inferred_corroborated": "C",
    "inferred_strong": "I",
    "inferred_weak": "I",
    "self_researched_unverified": "U",
    "hallucinated": "U",
}


def fetch_case_data(cur, case_file):
    cur.execute("SELECT * FROM clients WHERE case_file = %s LIMIT 1", (case_file,))
    client = cur.fetchone()
    if not client:
        return None
    cur.execute("""
        SELECT canonical_name, type, mentions_count, provenance_level, notes
          FROM entities
         WHERE provenance_level IN ('verified', 'inferred_corroborated')
           AND mentions_count >= 3
         ORDER BY
           CASE provenance_level WHEN 'verified' THEN 1 ELSE 2 END,
           mentions_count DESC LIMIT 60;
    """)
    entities = cur.fetchall()
    cur.execute("""
        SELECT canonical_id, asset_type, area_sqm, current_status,
               provenance_level, LEFT(notes, 200) AS notes_excerpt
          FROM assets
         WHERE case_file = %s
         ORDER BY area_sqm DESC NULLS LAST, id DESC LIMIT 40;
    """, (case_file,))
    assets = cur.fetchall()
    cur.execute("""
        SELECT id, topic, importance, summary, LEFT(content, 300) AS content_excerpt,
               provenance_level, created_at::date AS the_date
          FROM chat_notes
         WHERE related_case = %s
           AND provenance_level IN ('verified', 'inferred_corroborated', 'inferred_strong')
         ORDER BY importance DESC NULLS LAST, id DESC LIMIT 25;
    """, (case_file,))
    notes = cur.fetchall()
    cur.execute("""
        SELECT id, description, due_date, priority
          FROM action_items
         WHERE case_file = %s AND status = 'Open'
         ORDER BY due_date ASC NULLS LAST LIMIT 20;
    """, (case_file,))
    actions = cur.fetchall()
    cur.execute("""
        SELECT id, question, answered_at IS NOT NULL AS answered, created_at::date AS the_date
          FROM pending_questions
         WHERE case_file = %s OR asked_of_telegram_id = '6513067717'
         ORDER BY created_at DESC LIMIT 15;
    """, (case_file,))
    questions = cur.fetchall()
    return {"client": client, "entities": entities, "assets": assets,
            "notes": notes, "actions": actions, "questions": questions}


def build_html(case_file, data):
    c = data["client"]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    prio = (c.get("priority_level") or "?").lower()
    prio_class = prio if prio in ("critical", "high", "medium", "low") else "medium"

    def safe_html(s):
        return escape(str(s or "")).replace("\n", "<br>")

    def safe_lines(s, max_chars=2000):
        return safe_html((s or "")[:max_chars])

    entities_html = ""
    for e in data["entities"]:
        tag = PROV_TAG.get(e["provenance_level"], "I")
        notes_short = escape((e["notes"] or "")[:140])
        entities_html += (
            f"<tr><td><span class='tag-pill {tag}'>{tag}</span></td>"
            f"<td>{escape(e['canonical_name'])}</td>"
            f"<td>{escape(e['type'])}</td>"
            f"<td>{e['mentions_count']}</td>"
            f"<td>{notes_short}</td></tr>"
        )

    assets_html = ""
    for a in data["assets"]:
        tag = PROV_TAG.get(a["provenance_level"], "I")
        area = f"{a['area_sqm']:,.0f} sqm" if a["area_sqm"] else "—"
        assets_html += (
            f"<tr><td><span class='tag-pill {tag}'>{tag}</span></td>"
            f"<td>{escape(a['canonical_id'])}</td>"
            f"<td>{escape(a['asset_type'] or '')}</td>"
            f"<td>{area}</td>"
            f"<td>{escape(a['current_status'] or '')}</td>"
            f"<td style='font-size:8.5pt'>{escape((a['notes_excerpt'] or '')[:120])}</td></tr>"
        )

    notes_html = ""
    for n in data["notes"]:
        tag = PROV_TAG.get(n["provenance_level"], "I")
        notes_html += (
            f"<div class='bullet'>"
            f"<span class='tag-pill {tag}'>{tag}</span> "
            f"<span style='color:#677788'>[note:{n['id']}] {n['the_date']} "
            f"({escape(n['topic'] or '?')}, imp {n['importance']})</span> "
            f"<b>{escape(n['summary'] or '')}</b> — {escape((n['content_excerpt'] or '')[:200])}"
            f"</div>"
        )

    actions_html = ""
    for a in data["actions"]:
        due = a["due_date"].strftime("%Y-%m-%d") if a["due_date"] else "no date"
        actions_html += f"<li><b>{due}</b> [{escape(a['priority'] or '?')}]: {escape(a['description'])}</li>"

    questions_html = ""
    for q in data["questions"]:
        marker = "✓" if q["answered"] else "○"
        questions_html += f"<li>{marker} <span style='color:#677788'>#{q['id']} ({q['the_date']})</span> — {escape(q['question'][:300])}</li>"

    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<style>{CSS}</style>
</head><body>
<h1>{escape(c['name'])}</h1>
<div class="meta">
  Case: <span class="pill">{escape(case_file)}</span>
  Priority: <span class="pill {prio_class}">{escape(c.get('priority_level') or '—')}</span>
  Generated: {today}
  Intelligence updated: {c.get('intelligence_updated_at') or '—'}
</div>

<h2>Project status</h2>
<div class="summary">{safe_lines(c.get('project_status'))}</div>

<h2>Intelligence summary</h2>
<div class="summary">{safe_lines(c.get('client_intelligence_summary'), 6000)}</div>

<h2>Next milestone</h2>
<div class="summary">{safe_lines(c.get('next_milestone'))}</div>

<h2>Current goals</h2>
<div class="summary">{safe_lines(c.get('current_goals'), 4000)}</div>

<h2>Key risks</h2>
<div class="summary">{safe_lines(c.get('key_risks'), 4000)}</div>

<h2>Open strategic gaps</h2>
<div class="summary">{safe_lines(c.get('open_strategic_gaps'), 4000)}</div>

<h2>Asset ledger ({len(data['assets'])} entries)</h2>
<table class="kv">
  <tr><th></th><th>Asset ID</th><th>Type</th><th>Area</th><th>Status</th><th>Notes</th></tr>
  {assets_html}
</table>

<h2>Top entities (verified/corroborated, top 60 by mentions)</h2>
<table class="kv">
  <tr><th></th><th>Name</th><th>Type</th><th>Mentions</th><th>Notes</th></tr>
  {entities_html}
</table>

<h2>Recent chat notes (top 25)</h2>
{notes_html or '<p>(none)</p>'}

<h2>Open action items ({len(data['actions'])})</h2>
<ul>{actions_html or '<li>(none)</li>'}</ul>

<h2>Pending / answered questions ({len(data['questions'])})</h2>
<ul>{questions_html or '<li>(none)</li>'}</ul>

<div class="footer">
  Provenance legend:
  <span class="tag-pill V">V</span> verified (source-quoted) ·
  <span class="tag-pill C">C</span> corroborated (multi-mention) ·
  <span class="tag-pill I">I</span> inferred (single LLM extraction) ·
  <span class="tag-pill U">U</span> unverified
  <br>
  Generated by LandTek Leo · pdf_reports.py · {today}
</div>
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-send", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(**DSN); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    print(f"  [1/4] fetching {args.case} data...")
    data = fetch_case_data(cur, args.case)
    if not data:
        sys.exit(f"FATAL: no client found for case_file={args.case}")
    print(f"        client={data['client']['name']}, entities={len(data['entities'])}, "
          f"assets={len(data['assets'])}, notes={len(data['notes'])}, "
          f"actions={len(data['actions'])}, questions={len(data['questions'])}")
    cur.close(); conn.close()

    print(f"  [2/4] building HTML...")
    html = build_html(args.case, data)

    print(f"  [3/4] rendering PDF via weasyprint...")
    out_dir = "/root/landtek/reports"
    os.makedirs(out_dir, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = args.out or f"{out_dir}/{args.case}_brief_{today}.pdf"

    import weasyprint
    weasyprint.HTML(string=html, base_url="/root/landtek").write_pdf(out_path)
    size_kb = os.path.getsize(out_path) / 1024
    print(f"        wrote {out_path} ({size_kb:.0f} KB)")

    print(f"  [4/4] sending to Telegram..." if not args.no_send else f"  [4/4] not sending (--no-send)")
    if not args.no_send:
        caption = f"📄 <b>{args.case} brief</b> — generated {today}"
        ok = tg_send_document(out_path, caption=caption)
        print(f"        {'✓ sent' if ok else '✗ send failed'}")

    print(f"\n  ✓ Done: {out_path}")


if __name__ == "__main__":
    main()
