#!/usr/bin/env python3
"""Daily strategic digest — every client + every matter + Landtek firm trajectory.

Per Jonathan 2026-05-17: "Let's just do a daily output on the priorities of each
client and Landtek, should encompass all pending issues with the clients and
their respective cases, and Leo/Landtek's trajectory to become the world's
greatest executive assistant with Filipino land and property."

Replaces generate_client_daily_brief.py. One output covering:
  PART I  — Per-client priorities (every active client + matters + open intakes + next moves)
  PART II — Landtek firm-level trajectory (firm goals + KPIs + leverage move today)
  PART III— Health flags from meta-agent (gaps Leo cannot self-fix)

Cost: zero LLM (SQL only).
Schedule: 23:00 UTC daily = 7AM Manila.

Usage:
  python3 daily_strategic_digest.py                 # markdown to stdout
  python3 daily_strategic_digest.py --out PATH      # write markdown to file
  python3 daily_strategic_digest.py --tg            # also send compact digest to Telegram
  python3 daily_strategic_digest.py --tg --tg-file  # plus attach the full markdown
"""
import argparse
import json
from datetime import datetime, date, timezone
from pathlib import Path
import sys

sys.path.insert(0, "/root/landtek")
from landtek_core import db, tg_send_raw, get


def days_to(d):
    if d is None:
        return None
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return (d - date.today()).days


def fmt_when(d):
    if d is None:
        return "—"
    n = days_to(d)
    if n is None:
        return str(d)
    if n < 0:
        return f"{d} ⚠ T+{-n}d (past)"
    if n == 0:
        return f"{d} 🚨 TODAY"
    if n <= 3:
        return f"{d} 🟠 T-{n}d"
    if n <= 14:
        return f"{d} 🟡 T-{n}d"
    return f"{d} 🟢 T-{n}d"


def fetch(cur):
    """Pull every input needed for the digest in one read pass."""
    out = {}

    # Active clients
    cur.execute("""
        SELECT c.client_code, c.name, c.status,
               (SELECT COUNT(*) FROM matters m
                 WHERE m.client_code = c.client_code
                   AND m.status IN ('active','pending_triage')) AS n_matters
          FROM clients c
         WHERE c.status = 'Active' AND c.client_code != 'PENDING_TRIAGE'
         ORDER BY n_matters DESC, c.client_code
    """)
    out["clients"] = cur.fetchall()

    # All non-closed matters
    cur.execute("""
        SELECT matter_code, client_code, matter_type, title, court_or_agency,
               docket_number, status, current_stage, next_event, next_deadline,
               next_event_owner, stage_notes, case_file
          FROM matters
         WHERE status IN ('active','pending_triage')
         ORDER BY client_code, matter_code
    """)
    out["matters"] = cur.fetchall()

    # Pending deadlines next 30 days
    cur.execute("""
        SELECT cd.id, cd.case_file, cd.title, cd.due_date, cd.stage_key,
               cd.description, cd.notes
          FROM case_deadlines cd
         WHERE cd.status = 'pending' AND cd.due_date <= CURRENT_DATE + INTERVAL '30 days'
         ORDER BY cd.due_date
    """)
    out["deadlines"] = cur.fetchall()

    # Open intakes
    cur.execute("""
        SELECT sir.id, sir.deadline_id, cd.case_file, cd.title AS deadline_title,
               sir.timing, sir.fired_at, sir.items_total, sir.items_received,
               sit.title AS template_title
          FROM stage_intake_response sir
          JOIN stage_intake_template sit ON sit.id = sir.template_id
          JOIN case_deadlines cd ON cd.id = sir.deadline_id
         WHERE sir.status IN ('open','partial')
         ORDER BY sir.fired_at DESC
    """)
    out["open_intakes"] = cur.fetchall()

    # Firm goals
    cur.execute("""
        SELECT id, priority, goal_category, goal_text
          FROM firm_goals
         ORDER BY CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                                WHEN 'medium' THEN 3 ELSE 4 END, id
    """)
    out["firm_goals"] = cur.fetchall()

    # Today's LLM spend
    cur.execute("""
        SELECT COALESCE(SUM(cost_usd),0) AS cost_today,
               COUNT(*) AS calls_today
          FROM llm_calls WHERE called_at >= date_trunc('day', NOW())
    """)
    out["llm_today"] = cur.fetchone()

    # Last 7 days spend
    cur.execute("""
        SELECT date_trunc('day', called_at)::date AS day,
               ROUND(SUM(cost_usd)::numeric, 4) AS cost
          FROM llm_calls
         WHERE called_at >= NOW() - INTERVAL '7 days'
         GROUP BY 1 ORDER BY 1
    """)
    out["last7d_spend"] = cur.fetchall()

    # Open inquiry queue depth
    cur.execute("""
        SELECT status, COUNT(*) AS n FROM tg_inquiry_queue
         WHERE status IN ('queued','active')
         GROUP BY status
    """)
    out["queue_status"] = cur.fetchall()

    # Latest meta-agent findings (last cycle)
    cur.execute("""
        SELECT message_text FROM deadline_alerts
         WHERE channel='telegram' AND sent_at >= NOW() - INTERVAL '24 hours'
         ORDER BY sent_at DESC LIMIT 5
    """)
    out["recent_alerts"] = cur.fetchall()

    # Recent verified evidence — back-test pass rate
    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE passed) AS passes,
               COUNT(*) AS total
          FROM back_test_runs WHERE run_at >= NOW() - INTERVAL '24 hours'
    """)
    out["backtest_today"] = cur.fetchone()

    # Validity audit distribution (corpus health KPI)
    cur.execute("""
        SELECT structured_value->>'validity_summary' AS verdict, COUNT(*) AS n
          FROM extraction_chunks WHERE chunk_type='validity_audit'
         GROUP BY 1 ORDER BY n DESC
    """)
    out["validity_audits"] = cur.fetchall()

    # Recent activity (last 7 days of new docs)
    cur.execute("""
        SELECT d.case_file, d.doc_date_norm, d.classification,
               LEFT(d.smart_filename, 60) AS fn
          FROM documents d
         WHERE d.doc_date_norm IS NOT NULL
           AND d.doc_date_norm >= CURRENT_DATE - INTERVAL '14 days'
           AND d.execution_status IN ('executed_filed','executed_notarized','government_issued')
         ORDER BY d.doc_date_norm DESC LIMIT 8
    """)
    out["recent_filings"] = cur.fetchall()

    return out


# ─── LANDTEK TRAJECTORY — what "world's greatest executive assistant" means ──
TRAJECTORY_PILLARS = [
    ("Evidence-grade discipline",     "% of cited facts with verified provenance (truth-negotiator-passed)"),
    ("Multi-client scalability",      "active clients > 1; ARR > $0; per-client cost trending down"),
    ("PH-property domain depth",      "title_chain edges verified; ARTA + RD + courts auto-monitored"),
    ("Proactive autonomy",            "intakes auto-fired on stage flips; gaps auto-surfaced (meta-agent); deadlines auto-completed via stage-awareness"),
    ("Cost-discipline",               "<$5/day LLM spend; prompt caching saves >30%; Sonnet only for verdicts"),
    ("Reliability",                   "zero hallucinations; meta-agent invariants green; <1 false alert / month"),
    ("Bilingual / cultural fluency",  "Filipino source-quote handling; PH Civil Code rubric coverage"),
    ("Multi-channel reach",           "Telegram + Web + Email + (future) WhatsApp + Voice"),
]


def render_md(d):
    today = date.today().strftime("%A, %B %d, %Y")
    cost_today = float(d["llm_today"]["cost_today"] or 0)
    calls_today = d["llm_today"]["calls_today"]
    queue_n = sum(q["n"] for q in d["queue_status"])

    lines = [
        f"# Daily Strategic Digest — {today}",
        f"_Generated {datetime.now(timezone.utc).strftime('%H:%M UTC')} · LLM spend today: ${cost_today:.4f} across {calls_today} calls · Open inquiries: {queue_n}_",
        "",
        "---",
        "",
        "## I. Per-client priorities",
        "",
    ]

    # Group matters by client
    by_client = {}
    for m in d["matters"]:
        by_client.setdefault(m["client_code"], []).append(m)

    for c in d["clients"]:
        cc = c["client_code"]
        ms = by_client.get(cc, [])
        if not ms:
            continue
        lines.append(f"### 👤 {c['name']}  _(client_code: `{cc}`)_")
        lines.append(f"**{len(ms)} active matter(s)**")
        lines.append("")
        for m in ms:
            lines.append(f"**{m['matter_code']}** — {(m['title'] or '—')[:80]}")
            if m["current_stage"]:
                lines.append(f"  · Stage: `{m['current_stage']}`")
            if m["next_event"]:
                lines.append(f"  · WHAT: {m['next_event'][:200]}")
            if m["next_deadline"]:
                lines.append(f"  · WHEN: {fmt_when(m['next_deadline'])}")
            if m["next_event_owner"]:
                lines.append(f"  · WHO: {m['next_event_owner']}")
            if m["court_or_agency"]:
                lines.append(f"  · Venue: {m['court_or_agency']} · Docket: `{m['docket_number'] or '—'}`")
            lines.append("")

    # Open intakes (asks awaiting Jonathan)
    if d["open_intakes"]:
        lines.append("### 📨 Open intakes awaiting your input")
        lines.append("")
        for i in d["open_intakes"][:8]:
            lines.append(f"- `{i['case_file']}` · **{i['template_title']}** — {i['items_received']}/{i['items_total']} items ({i['timing']})")
        lines.append("")

    # Pending deadlines (across all clients)
    if d["deadlines"]:
        lines.append("### ⏰ Upcoming deadlines (next 30 days, all clients)")
        lines.append("")
        lines.append("| When | Case | Deadline |")
        lines.append("|---|---|---|")
        for dd in d["deadlines"]:
            lines.append(f"| {fmt_when(dd['due_date'])} | `{dd['case_file']}` | {dd['title'][:70]} |")
        lines.append("")

    # ─── PART II: Firm trajectory ──────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## II. Landtek firm trajectory")
    lines.append("_Goal: world's greatest executive assistant for Filipino land + property._")
    lines.append("")

    lines.append("### Strategic goals (firm-level)")
    lines.append("")
    for g in d["firm_goals"]:
        pri_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡"}.get(g["priority"], "🟢")
        lines.append(f"- {pri_emoji} **{g['priority'].upper()} · {g['goal_category']}** — {g['goal_text'][:200]}")
    lines.append("")

    # KPIs
    lines.append("### Operational KPIs (today)")
    lines.append("")
    lines.append("| Pillar | Metric |")
    lines.append("|---|---|")
    n_clients = len([c for c in d["clients"] if c["client_code"] not in ('PENDING_TRIAGE','Owner')])
    n_matters = sum(len(v) for v in by_client.values())
    valid_dist = ", ".join(f"{v['verdict'][:30]}={v['n']}" for v in d["validity_audits"][:3])
    bt = d["backtest_today"]
    bt_str = f"{bt['passes']}/{bt['total']} pass" if bt and bt["total"] else "no runs today"
    last7d_avg = sum(float(r["cost"] or 0) for r in d["last7d_spend"]) / max(1, len(d["last7d_spend"]))
    lines.append(f"| Active clients | {n_clients} |")
    lines.append(f"| Active matters | {n_matters} |")
    lines.append(f"| LLM cost today | ${cost_today:.4f} (7d avg ${last7d_avg:.4f}) |")
    lines.append(f"| Truth-negotiator back-test today | {bt_str} |")
    lines.append(f"| Validity audits (corpus) | {valid_dist or 'none yet'} |")
    lines.append(f"| Open inquiry queue | {queue_n} |")
    lines.append("")

    lines.append("### Trajectory pillars — where we stand on each")
    lines.append("")
    for pillar, metric in TRAJECTORY_PILLARS:
        lines.append(f"- **{pillar}** — _{metric}_")
    lines.append("")

    # ─── PART III: Today's leverage move ───────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## III. Today's highest-leverage move")
    lines.append("")
    # Heuristic: nearest deadline OR oldest open intake
    leverage = None
    if d["deadlines"]:
        nearest = d["deadlines"][0]
        days_left = days_to(nearest["due_date"])
        if days_left is not None and days_left <= 7:
            leverage = (f"**Deadline T-{days_left}d**: `{nearest['case_file']}` — {nearest['title'][:100]}.")
    if not leverage and d["open_intakes"]:
        oldest = d["open_intakes"][-1]
        leverage = (f"**Close the oldest open intake**: `{oldest['case_file']}` — {oldest['template_title']} "
                    f"({oldest['items_received']}/{oldest['items_total']} items in).")
    if not leverage:
        leverage = "No urgent deadlines or stale intakes — use the day for primary-evidence retrieval (the 2016 Cesar→Hansol Deed, MWK death cert, 2005 SPA revocation instrument)."
    lines.append(leverage)
    lines.append("")

    # Recent meta-agent findings
    if d["recent_alerts"]:
        lines.append("---")
        lines.append("")
        lines.append("## IV. Meta-agent flags (last 24h)")
        lines.append("")
        for a in d["recent_alerts"][:3]:
            txt = (a["message_text"] or "")[:300].replace("\n", " ")
            lines.append(f"- {txt}")
        lines.append("")

    return "\n".join(lines)


def build_tg_compact(d, full_md_chars=None):
    today = date.today().strftime("%a %b %d, %Y")
    cost_today = float(d["llm_today"]["cost_today"] or 0)
    n_clients = len([c for c in d["clients"] if c["client_code"] not in ('PENDING_TRIAGE','Owner')])
    n_matters = sum(len(by_client_list(d["matters"]).get(c["client_code"], []))
                    for c in d["clients"])
    queue_n = sum(q["n"] for q in d["queue_status"])

    lines = [f"📰 <b>Daily Strategic Digest — {today}</b>", ""]
    lines.append(f"<b>{n_clients}</b> clients · <b>{n_matters}</b> matters · "
                 f"<b>{len(d['deadlines'])}</b> upcoming deadlines · "
                 f"<b>{queue_n}</b> open inquiries · today LLM <b>${cost_today:.4f}</b>")
    lines.append("")

    # Top matters per client
    lines.append("👥 <b>Clients</b>")
    for c in d["clients"]:
        if c["client_code"] in ('PENDING_TRIAGE','Owner'):
            continue
        ms = by_client_list(d["matters"]).get(c["client_code"], [])
        if not ms:
            continue
        lines.append(f"\n<b>{c['name']}</b> — {len(ms)} matter(s)")
        for m in ms[:3]:
            next_part = (m["next_event"] or "—")[:60]
            when = fmt_when(m["next_deadline"]) if m["next_deadline"] else ""
            lines.append(f"  • <code>{m['matter_code']}</code> {when}")
            lines.append(f"     <i>{next_part}</i>")
        if len(ms) > 3:
            lines.append(f"  • <i>(+{len(ms)-3} more)</i>")

    if d["deadlines"]:
        lines.append("\n⏰ <b>Upcoming</b>")
        for dd in d["deadlines"][:3]:
            lines.append(f"  {fmt_when(dd['due_date'])} · {dd['title'][:55]}")

    if d["open_intakes"]:
        lines.append("\n📨 <b>Open intakes</b>")
        for i in d["open_intakes"][:3]:
            lines.append(f"  • {i['template_title'][:50]} ({i['items_received']}/{i['items_total']})")

    lines.append("\n<i>Reply /matters /timeline &lt;X&gt; /status for more.</i>")
    if full_md_chars:
        lines.append(f"<i>Full digest ({full_md_chars:,} chars) at /root/landtek/drafts/</i>")

    text = "\n".join(lines)
    return text[:3900]


def by_client_list(matters):
    out = {}
    for m in matters:
        out.setdefault(m["client_code"], []).append(m)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="markdown output path; default = /root/landtek/drafts/daily_digest_YYYY-MM-DD.md")
    ap.add_argument("--tg", action="store_true", help="send compact digest via tg_send_raw")
    ap.add_argument("--tg-file", action="store_true", help="also send the full markdown file via Telegram document")
    args = ap.parse_args()

    with db() as cur:
        d = fetch(cur)

    md = render_md(d)
    out_path = Path(args.out or f"/root/landtek/drafts/daily_digest_{date.today().isoformat()}.md")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(md)
    print(f"  Wrote: {out_path} ({len(md):,} chars)")

    if args.tg:
        tg_text = build_tg_compact(d, full_md_chars=len(md))
        ok, info = tg_send_raw(tg_text)
        print(f"  TG digest: {'sent' if ok else 'FAILED'} {info if not ok else ''}")

    if args.tg_file:
        # Send the full markdown as a document
        import requests
        token = get("TELEGRAM_BOT_TOKEN")
        with open(out_path, "rb") as fh:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendDocument",
                              data={"chat_id": "6513067717",
                                    "caption": f"Daily digest — full markdown ({len(md):,} chars)"},
                              files={"document": fh}, timeout=30)
        print(f"  TG file: {'sent' if r.status_code == 200 else 'FAILED'}")


if __name__ == "__main__":
    main()
