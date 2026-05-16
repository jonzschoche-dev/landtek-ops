#!/usr/bin/env python3
"""Client Daily Brief — every pending matter, every pending event, every open intake.

Per [[feedback_landtek_management_style]]: WHAT / WHEN / WHO / OUTCOME / GOAL_LINK
on every pending event. Per [[feedback_legal_status_awareness]]: current stage
surfaced for every matter, not just the noisy one.

Outputs:
  • Markdown report → /root/landtek/drafts/daily_brief_YYYY-MM-DD.md
  • Telegram digest (HTML) to Jonathan
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, date
from pathlib import Path
import psycopg2, psycopg2.extras, requests

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
JONATHAN_TG = "6513067717"


def load_token():
    with open("/root/landtek/.env") as f:
        for line in f:
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.strip().split("=", 1)[1]
    return None


def fetch():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # All active matters in matters table
    cur.execute("""
        SELECT matter_code, client_code, matter_type, title, court_or_agency, docket_number,
               status, current_stage, next_event, next_deadline, next_event_owner, stage_notes,
               case_file, verified_document_count
          FROM matters WHERE status='active' ORDER BY id
    """)
    matters = cur.fetchall()

    # All open case_threads
    cur.execute("""
        SELECT thread_name, thread_type, status, parent_case_file, summary
          FROM case_threads WHERE status IN ('open','pending') ORDER BY id
    """)
    threads = cur.fetchall()

    # Pending deadlines + intake status
    cur.execute("""
        SELECT cd.id, cd.case_file, cd.title, cd.due_date, cd.stage_key, cd.status,
               cd.description, cd.notes,
               (SELECT COUNT(*) FROM stage_intake_response sir WHERE sir.deadline_id=cd.id AND sir.timing='pre' AND sir.status IN ('open','partial')) AS pre_open,
               (SELECT COUNT(*) FROM stage_intake_response sir WHERE sir.deadline_id=cd.id AND sir.timing='post' AND sir.status IN ('open','partial')) AS post_open
          FROM case_deadlines cd
         WHERE cd.status='pending' AND cd.due_date >= CURRENT_DATE - INTERVAL '30 days'
         ORDER BY cd.due_date NULLS LAST
    """)
    deadlines = cur.fetchall()

    # Open intakes
    cur.execute("""
        SELECT sir.id, sir.deadline_id, cd.title AS deadline_title, cd.case_file,
               sir.timing, sir.fired_at, sir.items_total, sir.items_received, sir.status,
               sit.title AS template_title, sit.checklist
          FROM stage_intake_response sir
          JOIN stage_intake_template sit ON sit.id = sir.template_id
          JOIN case_deadlines cd ON cd.id = sir.deadline_id
         WHERE sir.status IN ('open','partial')
         ORDER BY sir.fired_at DESC
    """)
    intakes = cur.fetchall()

    # Other case_files not in matters table (orphan matters)
    cur.execute("""
        SELECT case_file, COUNT(*) AS n_docs, MAX(doc_date) AS last_doc_date
          FROM documents
         WHERE case_file IS NOT NULL
           AND case_file NOT IN (SELECT DISTINCT case_file FROM matters)
           AND case_file NOT IN ('unknown','Unknown','Owner')
         GROUP BY case_file
         ORDER BY n_docs DESC
    """)
    orphan_matters = cur.fetchall()

    # Today's recent activity (last 14 days of filings/orders)
    # doc_date is stored as text in some rows — coerce safely.
    cur.execute("""
        SELECT d.case_file, d.doc_date, d.classification, LEFT(d.smart_filename, 60) AS fn,
               pf.filing_party
          FROM documents d
          LEFT JOIN case_party_filings pf ON pf.doc_id = d.id
         WHERE d.case_file IS NOT NULL
           AND d.doc_date IS NOT NULL
           AND d.doc_date ~ '^\\d{4}-\\d{2}-\\d{2}'
           AND d.doc_date::date >= CURRENT_DATE - INTERVAL '14 days'
           AND d.execution_status IN ('executed_filed','executed_notarized','government_issued')
         ORDER BY d.doc_date DESC
         LIMIT 10
    """)
    recent_activity = cur.fetchall()

    cur.close(); conn.close()
    return matters, threads, deadlines, intakes, orphan_matters, recent_activity


def days_to(due_date):
    if not due_date:
        return None
    if isinstance(due_date, str):
        due_date = date.fromisoformat(due_date)
    return (due_date - date.today()).days


def fmt_deadline_clock(due_date):
    if not due_date:
        return "—"
    d = days_to(due_date)
    if d is None:
        return str(due_date)
    if d < 0:
        return f"{due_date} ⚠️ T+{-d}d (past)"
    if d == 0:
        return f"{due_date} 🚨 TODAY"
    if d <= 3:
        return f"{due_date} 🟠 T-{d}d"
    if d <= 7:
        return f"{due_date} 🟡 T-{d}d"
    return f"{due_date} 🟢 T-{d}d"


def build_md(matters, threads, deadlines, intakes, orphan_matters, recent_activity):
    today = date.today().strftime("%a %b %d, %Y")
    lines = [
        f"# Client Daily Brief — {today}",
        f"_Auto-generated at {datetime.now(timezone.utc).strftime('%H:%M UTC')} per Landtek management-style rule._",
        "",
        "## At a glance",
        "",
        f"- **Active matters:** {len(matters)}",
        f"- **Pending deadlines:** {len(deadlines)}",
        f"- **Open intakes (your input needed):** {len(intakes)}",
        f"- **Open case-threads:** {len(threads)}",
        f"- **Orphan matters (need triage):** {len(orphan_matters)}",
        "",
        "---",
        "",
    ]

    # ─── Section: Open intakes awaiting Jonathan ─────────────────────────
    if intakes:
        lines.append("## 📨 Open intakes — your input needed")
        lines.append("")
        for i, x in enumerate(intakes, 1):
            checklist = x["checklist"] if isinstance(x["checklist"], list) else json.loads(x["checklist"] or "[]")
            lines.append(f"### {i}. {x['template_title']}  _[{x['case_file']}]_")
            lines.append(f"- Fired: {x['fired_at'].strftime('%Y-%m-%d %H:%M UTC')}")
            lines.append(f"- For deadline: {x['deadline_title']}")
            lines.append(f"- Items: {x['items_received']}/{x['items_total']} received")
            for j, item in enumerate(checklist, 1):
                lines.append(f"  - [ ] {j}. {item}")
            lines.append("")

    # ─── Section: Per-matter status ─────────────────────────────────────
    lines.append("## 🗂 Per-matter status")
    lines.append("")
    for m in matters:
        lines.append(f"### {m['matter_code']} — {m['title']}")
        lines.append(f"- **Type:** {m['matter_type']} · {m['court_or_agency'] or '—'} · Docket: `{m['docket_number'] or '—'}`")
        lines.append(f"- **Current stage:** `{m['current_stage'] or '(not set)'}`")
        if m["next_event"]:
            lines.append(f"- **WHAT (next):** {m['next_event']}")
        if m["next_deadline"]:
            lines.append(f"- **WHEN:** {fmt_deadline_clock(m['next_deadline'])}")
        if m["next_event_owner"]:
            lines.append(f"- **WHO:** {m['next_event_owner']}")
        if m["stage_notes"]:
            lines.append(f"- **NOTES:** {m['stage_notes']}")
        lines.append("")

    # ─── Section: All pending deadlines (across all matters) ────────────
    if deadlines:
        lines.append("## ⏰ Pending deadlines")
        lines.append("")
        lines.append("| When | Case | Deadline | Stage | Pre / Post |")
        lines.append("|---|---|---|---|---|")
        for d in deadlines:
            pre = "📨" if d["pre_open"] else "—"
            post = "📋" if d["post_open"] else "—"
            lines.append(f"| {fmt_deadline_clock(d['due_date'])} | {d['case_file']} | {d['title'][:60]} | `{d['stage_key'] or '—'}` | {pre} / {post} |")
        lines.append("")

    # ─── Section: Open case-threads ────────────────────────────────────
    if threads:
        lines.append("## 🧵 Open sub-threads")
        lines.append("")
        for t in threads:
            lines.append(f"- **{t['thread_name']}** _({t['thread_type']}, {t['status']})_ — {t['summary'][:140]}")
        lines.append("")

    # ─── Section: Orphan matters that need triage ──────────────────────
    if orphan_matters:
        lines.append("## ❓ Orphan matters — need your context")
        lines.append("")
        lines.append("These case_files have documents in the corpus but are **not in the matters table**. Tell Leo what they are so they can get proper stage tracking.")
        lines.append("")
        for o in orphan_matters:
            lines.append(f"- **`{o['case_file']}`** — {o['n_docs']} docs · most recent: {o['last_doc_date'] or '(no date)'}")
        lines.append("")

    # ─── Recent activity ────────────────────────────────────────────────
    if recent_activity:
        lines.append("## 📰 Recent filings (last 14 days)")
        lines.append("")
        for r in recent_activity[:8]:
            party = r["filing_party"] or "—"
            lines.append(f"- `{r['doc_date']}` [{r['case_file']}] **{party}** filed: {r['classification'] or '?'} — {r['fn']}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_Per memory `feedback_landtek_management_style`: every pending event must surface with WHAT / WHEN / WHO / OUTCOME / GOAL_LINK. We do not wait — we drive results._")
    return "\n".join(lines)


def build_telegram_digest(matters, deadlines, intakes, orphan_matters):
    """Compact HTML version for Telegram (must fit under ~4000 chars)."""
    today = date.today().strftime("%a %b %d, %Y")
    lines = [f"📰 <b>Client Daily Brief — {today}</b>", ""]
    lines.append(f"<b>{len(matters)}</b> active matters · <b>{len(deadlines)}</b> pending deadlines · <b>{len(intakes)}</b> open intakes")
    lines.append("")

    if intakes:
        lines.append("📨 <b>Open intakes (you):</b>")
        for x in intakes[:4]:
            lines.append(f"  • <i>{x['template_title']}</i> [{x['case_file']}] — {x['items_received']}/{x['items_total']} items")
        lines.append("")

    lines.append("🗂 <b>Per-matter status:</b>")
    for m in matters:
        stage = m["current_stage"] or "(not set)"
        next_ev = (m["next_event"] or "—")[:90]
        when = ""
        if m["next_deadline"]:
            when = " · " + fmt_deadline_clock(m["next_deadline"])
        lines.append(f"\n<b>{m['matter_code']}</b> — <code>{stage}</code>{when}")
        lines.append(f"   <i>{next_ev}</i>")
    lines.append("")

    if deadlines:
        lines.append("⏰ <b>Pending deadlines:</b>")
        for d in deadlines[:5]:
            lines.append(f"  • {fmt_deadline_clock(d['due_date'])} — {d['title'][:55]}")
        lines.append("")

    if orphan_matters:
        lines.append("❓ <b>Orphan matters (need context):</b>")
        for o in orphan_matters[:3]:
            lines.append(f"  • <code>{o['case_file']}</code> — {o['n_docs']} docs")

    text = "\n".join(lines)
    return text[:4000]


def send_tg(text, token):
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": JONATHAN_TG, "text": text, "parse_mode": "HTML",
                            "disable_web_page_preview": True}, timeout=15)
    return r.status_code == 200, r.text[:200]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-tg", action="store_true", help="skip Telegram send")
    ap.add_argument("--no-file", action="store_true", help="skip file write")
    args = ap.parse_args()

    matters, threads, deadlines, intakes, orphan_matters, recent_activity = fetch()
    md = build_md(matters, threads, deadlines, intakes, orphan_matters, recent_activity)

    if not args.no_file:
        out_dir = Path("/root/landtek/drafts"); out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"daily_brief_{date.today().strftime('%Y-%m-%d')}.md"
        out_path.write_text(md)
        print(f"  Brief written: {out_path} ({len(md):,} chars)")

    if not args.no_tg:
        token = load_token()
        if token:
            tg_text = build_telegram_digest(matters, deadlines, intakes, orphan_matters)
            ok, info = send_tg(tg_text, token)
            print(f"  Telegram: {'sent' if ok else 'FAILED'} ({len(tg_text)} chars) {info if not ok else ''}")
        else:
            print("  Telegram: no token, skipped")


if __name__ == "__main__":
    main()
