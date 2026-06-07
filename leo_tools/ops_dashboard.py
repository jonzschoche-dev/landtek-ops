"""LandTek ops dashboard — Jonathan control room.

Mount at /ops/ on leo_tools (port 8765). SQL-only views — no LLM.
"""
from __future__ import annotations

import html
import json
import os
import subprocess
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from flask import Blueprint, abort, request

PG_DSN = os.getenv("LEO_TOOLS_PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

bp = Blueprint("ops", __name__, url_prefix="/ops")

KEY_TIMERS = [
    ("landtek-backup.timer", "Backup"),
    ("landtek-correspondence-matcher.timer", "Email matcher"),
    ("landtek-email-briefer.timer", "Email briefer"),
    ("landtek-doc-triage.timer", "Doc triage"),
    ("holes-dispatcher.timer", "Holes L1"),
    ("landtek-shadow-traffic.timer", "Shadow traffic"),
    ("leo-qa-runner.timer", "QA runner"),
    ("landtek-micro-probe.timer", "Micro probes"),
    ("leo-rapid-fire.timer", "Rapid-fire L4"),
    ("leo-watchdog.timer", "Leo watchdog"),
    ("landtek-connection-sentinel.timer", "Connection sentinel"),
    ("n8n-n8n-1", "n8n container"),
]

MWK_LANES = [
    ("MWK-ARTA-0747", "ARTA admin", "resolution_noc_op_appeal_window"),
    ("MWK-ARTA-1210", "ARTA admin", "complaint_filed_awaiting_response"),
    ("MWK-OP-PETITION", "OP supervisory", "petition_filed_awaiting_op_action"),
    ("MWK-CV26360", "Civil trial", "mediation_impasse_trial_pending"),
]


def _db():
    return psycopg2.connect(PG_DSN)


def _esc(s):
    if s is None:
        return ""
    return html.escape(str(s))


def _layout(title: str, body: str, active: str = "home") -> str:
    nav = [
        ("home", "/", "Home"),
        ("clients", "/clients", "Clients"),
        ("mwk", "/mwk", "MWK"),
        ("health", "/health", "Health"),
        ("files", "/files/", "Files"),
        ("rate", "/rate", "Rate Leo"),
    ]
    links = []
    for key, href, label in nav:
        prefix = "/ops" if key != "files" and key != "rate" else ""
        full = f"{prefix}{href}" if href.startswith("/") else href
        if key == "files":
            full = "/files/"
        elif key == "rate":
            full = "/rate"
        else:
            full = f"/ops{href}"
        cls = ' class="active"' if key == active else ""
        links.append(f'<a href="{full}"{cls}>{label}</a>')
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)} — LandTek</title>{CSS}</head><body>
<header class="topbar">
  <div class="brand">LandTek <span class="muted">ops</span></div>
  <nav>{''.join(links)}</nav>
  <div class="ts">{now}</div>
</header>
<main class="wrap">{body}</main>
</body></html>"""


CSS = """
<style>
:root { --bg:#f6f7f9; --card:#fff; --line:#e5e7eb; --text:#111827; --muted:#6b7280;
  --ok:#059669; --warn:#d97706; --bad:#dc2626; --link:#2563eb; }
* { box-sizing:border-box; }
body { margin:0; font:14px/1.45 -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;
  background:var(--bg); color:var(--text); }
.topbar { display:flex; align-items:center; gap:16px; padding:10px 20px; background:#1e293b; color:#fff; flex-wrap:wrap; }
.brand { font-weight:700; font-size:16px; }
.brand .muted { font-weight:400; opacity:.7; }
.topbar nav a { color:#cbd5e1; text-decoration:none; margin-right:12px; font-size:13px; }
.topbar nav a.active { color:#fff; border-bottom:2px solid #38bdf8; padding-bottom:2px; }
.topbar .ts { margin-left:auto; font-size:12px; opacity:.75; }
.wrap { max-width:1280px; margin:0 auto; padding:20px; }
h1 { font-size:22px; margin:0 0 4px; }
.lead { color:var(--muted); margin:0 0 20px; }
.grid { display:grid; gap:16px; }
.grid-2 { grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); }
.grid-3 { grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); }
.grid-4 { grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }
.section-title { font-size:15px; font-weight:600; margin:24px 0 10px; color:var(--text); }
.muted { color:var(--muted); }
.card h2 { font-size:14px; margin:0 0 10px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
table { width:100%; border-collapse:collapse; font-size:13px; }
th,td { padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }
th { color:var(--muted); font-weight:600; font-size:12px; }
tr:hover { background:#fafafa; }
.badge { display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:600; }
.badge-ok { background:#d1fae5; color:var(--ok); }
.badge-warn { background:#fef3c7; color:var(--warn); }
.badge-bad { background:#fee2e2; color:var(--bad); }
.badge-off { background:#f3f4f6; color:var(--muted); }
.badge-sim { background:#ede9fe; color:#6d28d9; }
.stat { font-size:28px; font-weight:700; line-height:1.1; }
.stat-sub { font-size:12px; color:var(--muted); }
.lane { border-left:4px solid #3b82f6; padding-left:12px; margin-bottom:14px; }
.lane.civil { border-color:#ef4444; }
.lane.op { border-color:#8b5cf6; }
.lane.arta { border-color:#0ea5e9; }
a { color:var(--link); text-decoration:none; }
a:hover { text-decoration:underline; }
.searchbar input { padding:10px 12px; width:min(520px,100%); border:1px solid var(--line); border-radius:8px; font-size:14px; }
.searchbar button { padding:10px 16px; background:#1e293b; color:#fff; border:none; border-radius:8px; cursor:pointer; }
.empty { color:var(--muted); font-style:italic; }
.alert { padding:10px 12px; border-radius:8px; margin-bottom:8px; font-size:13px; }
.alert-bad { background:#fee2e2; color:#991b1b; }
.alert-warn { background:#fef3c7; color:#92400e; }
.alert-ok { background:#d1fae5; color:#065f46; }
</style>
"""


def _watchdog_state() -> str:
    try:
        with open("/var/lib/landtek/watchdog_state.json") as f:
            return json.load(f).get("state", "?")
    except Exception:
        return "?"


def _n8n_healthy() -> bool:
    try:
        r = subprocess.run(
            ["curl", "-sf", "--max-time", "3", "http://localhost:5678/healthz"],
            capture_output=True,
            timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def _timer_rows() -> list[dict]:
    rows = []
    for unit, label in KEY_TIMERS:
        if unit == "n8n-n8n-1":
            try:
                r = subprocess.run(
                    ["docker", "inspect", "-f", "{{.State.Status}}", unit],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                status = (r.stdout or "").strip() or "unknown"
                rows.append({
                    "unit": unit,
                    "label": label,
                    "enabled": status,
                    "active": status,
                    "next": "—",
                    "note": "container",
                })
            except Exception:
                rows.append({"unit": unit, "label": label, "enabled": "?", "active": "?", "next": "—", "note": "container"})
            continue
        try:
            en = subprocess.run(
                ["systemctl", "is-enabled", unit],
                capture_output=True,
                text=True,
                timeout=5,
            )
            ac = subprocess.run(
                ["systemctl", "is-active", unit],
                capture_output=True,
                text=True,
                timeout=5,
            )
            enabled = (en.stdout or "").strip()
            active = (ac.stdout or "").strip()
        except Exception:
            enabled = active = "?"
        next_run = "—"
        try:
            r = subprocess.run(
                ["systemctl", "show", unit, "-p", "NextElapseUSecRealtime", "--value"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            nxt = (r.stdout or "").strip()
            if nxt and nxt not in ("n/a", "0"):
                next_run = nxt[:19] if len(nxt) > 19 else nxt
        except Exception:
            pass
        rows.append({
            "unit": unit,
            "label": label,
            "enabled": enabled,
            "active": active,
            "next": next_run,
            "note": "timer",
        })
    return rows


def _safe_fetch(cur, conn, sql: str, params=(), default=None, one: bool = False):
    try:
        cur.execute(sql, params)
        return cur.fetchone() if one else cur.fetchall()
    except Exception:
        conn.rollback()
        return default


def _stat_card(title: str, value, sub: str = "") -> str:
    sub_html = f'<div class="stat-sub">{sub}</div>' if sub else ""
    return f'<div class="card"><h2>{_esc(title)}</h2><div class="stat">{_esc(value)}</div>{sub_html}</div>'


def _pct(n, d) -> str:
    if not d:
        return "—"
    return f"{round(100 * n / d, 1)}%"


def _badge_timer(row: dict) -> str:
    unit = row["unit"]
    active = row.get("active", "")
    enabled = row.get("enabled", "")
    if unit == "leo-rapid-fire.timer":
        if enabled == "enabled" or active == "active":
            return '<span class="badge badge-bad">SHOULD BE OFF</span>'
        return '<span class="badge badge-ok">disabled ✓</span>'
    if unit == "n8n-n8n-1":
        if active == "running":
            return '<span class="badge badge-ok">running</span>'
        return f'<span class="badge badge-bad">{_esc(active)}</span>'
    if active == "active":
        return '<span class="badge badge-ok">active</span>'
    if enabled == "enabled":
        return '<span class="badge badge-warn">enabled</span>'
    return f'<span class="badge badge-off">{_esc(enabled)}</span>'


@bp.route("/")
def home():
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    deadlines = _safe_fetch(cur, conn, """
        SELECT id, title, due_date, status, case_file
          FROM case_deadlines
         WHERE status != 'completed' AND due_date IS NOT NULL
           AND due_date >= CURRENT_DATE - interval '3 days'
         ORDER BY due_date ASC
         LIMIT 8
    """, default=[])

    obligations = _safe_fetch(cur, conn, """
        SELECT id, short_label, status, priority, due_by, client_code, risk_window,
               NULL::text AS matter_code
          FROM v_obligations_at_risk
         ORDER BY priority DESC, due_by ASC NULLS LAST
         LIMIT 8
    """, default=[])
    if not obligations:
        obligations = _safe_fetch(cur, conn, """
            SELECT id, short_label, status, priority, due_by, matter_code, client_code,
                   NULL::text AS risk_window
              FROM landtek_obligations
             WHERE status IN ('open', 'in_progress', 'blocked')
             ORDER BY priority DESC, due_by ASC NULLS LAST
             LIMIT 8
        """, default=[])

    portfolio = _safe_fetch(cur, conn, """
        SELECT
          (SELECT COUNT(*) FROM documents) AS total_docs,
          (SELECT COUNT(*) FROM clients WHERE case_file IS NOT NULL AND case_file != '') AS clients,
          (SELECT COUNT(*) FROM matters WHERE status = 'active') AS active_matters,
          (SELECT COUNT(*) FROM v_gmail_relevant) AS spine_emails,
          (SELECT COUNT(*) FROM v_correspondence_triage) AS triage_backlog,
          (SELECT COUNT(*) FROM v_open_client_needs) AS open_needs,
          (SELECT COUNT(*) FROM v_obligations_at_risk WHERE risk_window = 'overdue') AS overdue_obl,
          (SELECT COUNT(*) FROM action_items WHERE status = 'Open') AS open_actions,
          (SELECT COUNT(*) FROM pending_inquiries
            WHERE status = 'open' AND expires_at > now()) AS open_inquiries,
          (SELECT COUNT(*) FROM unauth_attempts
            WHERE attempted_at > now() - interval '24 hours') AS unauth_24h
    """, default={}, one=True) or {}

    ops = _safe_fetch(cur, conn, """
        SELECT
          (SELECT COUNT(*) FROM documents
            WHERE COALESCE(timestamp, created_at) > now() - interval '24 hours') AS docs_24h,
          (SELECT COUNT(*) FROM documents_needing_classification) AS unclassified,
          (SELECT COUNT(*) FROM conversations
            WHERE timestamp > now() - interval '24 hours') AS conv_24h
    """, default={}, one=True) or {}

    leo = _safe_fetch(cur, conn, """
        SELECT
          COUNT(*) FILTER (WHERE timestamp > now() - interval '24 hours') AS int_24h,
          COUNT(*) FILTER (WHERE timestamp > now() - interval '24 hours'
                            AND sender_id LIKE '999000%') AS sim_24h,
          COUNT(*) FILTER (WHERE timestamp > now() - interval '24 hours'
                            AND sender_id NOT LIKE '999000%') AS real_24h,
          COUNT(*) FILTER (WHERE timestamp > now() - interval '7 days'
                            AND sender_id LIKE '999000%') AS sim_7d,
          COUNT(*) FILTER (WHERE timestamp > now() - interval '7 days'
                            AND sender_id NOT LIKE '999000%') AS real_7d,
          COUNT(*) FILTER (WHERE tokens_in IS NOT NULL) AS logged_tokens,
          COUNT(*) AS total_logged,
          COALESCE(SUM(est_cost_cents) FILTER (
            WHERE timestamp > now() - interval '7 days'), 0) AS cost_cents_7d,
          COALESCE(SUM(tokens_in) FILTER (
            WHERE timestamp > now() - interval '7 days'), 0) AS tok_in_7d,
          ROUND(AVG(rating) FILTER (
            WHERE rating IS NOT NULL AND timestamp > now() - interval '30 days'), 1) AS avg_rating
          FROM leo_interactions
    """, default={}, one=True) or {}

    qa = _safe_fetch(cur, conn, """
        SELECT
          COUNT(*) FILTER (WHERE posted_at > now() - interval '24 hours') AS runs_24h,
          COUNT(*) FILTER (WHERE posted_at > now() - interval '24 hours' AND passed) AS pass_24h,
          COUNT(*) FILTER (WHERE posted_at > now() - interval '1 hour') AS runs_1h,
          COUNT(*) FILTER (WHERE posted_at > now() - interval '1 hour' AND passed) AS pass_1h
          FROM leo_qa_sim_payloads
    """, default={}, one=True) or {}

    n8n_exec = _safe_fetch(cur, conn, """
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE status = 'error') AS err,
          COUNT(*) FILTER (WHERE status = 'success') AS ok
          FROM execution_entity
         WHERE "workflowId" = 'vSDQv1vfn6627bnA'
           AND "startedAt" > now() - interval '24 hours'
    """, default={}, one=True) or {}

    open_holes_row = _safe_fetch(cur, conn,
        "SELECT COUNT(*) AS n FROM holes_findings WHERE status = 'open'",
        default={"n": 0}, one=True)
    open_holes = open_holes_row["n"] if open_holes_row else 0

    sim_sess = _safe_fetch(cur, conn, """
        SELECT passed, failed, burst_size, completed_at
          FROM simulator_sessions WHERE status = 'done'
         ORDER BY started_at DESC LIMIT 1
    """, default=None, one=True)

    recent = _safe_fetch(cur, conn, """
        SELECT id, timestamp, sender_name, LEFT(question, 70) AS q,
               LEFT(reply_text, 90) AS reply,
               CASE WHEN sender_id LIKE '999000%' THEN 'sim' ELSE 'real' END AS kind,
               rating
          FROM leo_interactions
         ORDER BY timestamp DESC LIMIT 10
    """, default=[])

    events = _safe_fetch(cur, conn, """
        SELECT case_file, short_label, scheduled_for::date AS d, priority,
               readiness_pct, req_open
          FROM v_upcoming_events_30d
         ORDER BY scheduled_for ASC NULLS LAST
         LIMIT 6
    """, default=[])

    needs = _safe_fetch(cur, conn, """
        SELECT client_name, short_label, priority, need_kind
          FROM v_open_client_needs
         ORDER BY priority DESC, created_at DESC
         LIMIT 6
    """, default=[])

    cur.close()
    conn.close()

    wd = _watchdog_state()
    n8n_ok = _n8n_healthy()

    alerts = []
    if open_holes:
        alerts.append(f'<div class="alert alert-warn">{open_holes} open holes finding(s) — <a href="/ops/health">Health</a></div>')
    if not n8n_ok:
        alerts.append('<div class="alert alert-bad">n8n health check failed</div>')
    if portfolio.get("overdue_obl"):
        alerts.append(
            f'<div class="alert alert-warn">{portfolio["overdue_obl"]} overdue obligation(s)</div>'
        )
    if portfolio.get("triage_backlog", 0) > 500:
        alerts.append(
            f'<div class="alert alert-warn">{portfolio["triage_backlog"]} emails in correspondence triage backlog</div>'
        )
    for tr in _timer_rows():
        if tr["unit"] == "leo-rapid-fire.timer" and tr["enabled"] == "enabled":
            alerts.append('<div class="alert alert-bad">Rapid-fire timer is ENABLED — should be on-demand only</div>')

    if sim_sess:
        sim_line = f"{sim_sess['passed'] or 0}/{sim_sess['burst_size'] or 0} pass"
    else:
        sim_line = "no sessions"

    n8n_total = n8n_exec.get("total") or 0
    cost_logged = (leo.get("cost_cents_7d") or 0) / 100
    cost_est = round(n8n_total * 0.08, 2) if not cost_logged else cost_logged
    cost_sub = (
        f"${cost_logged:.2f} logged · {leo.get('tok_in_7d') or 0:,} tok in"
        if leo.get("logged_tokens")
        else f"~${cost_est:.0f}/day est · {leo.get('logged_tokens') or 0} rows w/ tokens"
    )

    dl_rows = "".join(
        f"<tr><td>{_esc(r['due_date'])}</td><td>{_esc(r['title'])}</td>"
        f"<td>{_esc(r.get('case_file') or '—')}</td>"
        f"<td><span class='badge badge-{'warn' if r['status']=='pending' else 'off'}'>{_esc(r['status'])}</span></td></tr>"
        for r in deadlines
    ) or '<tr><td colspan="4" class="empty">No upcoming deadlines</td></tr>'

    obl_parts = []
    for r in obligations:
        risk_badge = ""
        if r.get("risk_window") == "overdue":
            risk_badge = f' <span class="badge badge-bad">{_esc(r["risk_window"])}</span>'
        obl_parts.append(
            f"<tr><td>P{r['priority']}</td><td>{_esc(r['short_label'])}</td>"
            f"<td>{_esc(r.get('matter_code') or r.get('client_code') or '—')}</td>"
            f"<td>{_esc(str(r.get('due_by') or '—')[:10])}{risk_badge}</td></tr>"
        )
    obl_rows = "".join(obl_parts) or '<tr><td colspan="4" class="empty">None at risk</td></tr>'

    ev_rows = "".join(
        f"<tr><td>{r['d']}</td><td>{_esc(r.get('case_file') or '—')}</td>"
        f"<td>{_esc(r['short_label'])}</td><td>P{r['priority']}</td>"
        f"<td>{r.get('readiness_pct') or '—'}%</td><td>{r.get('req_open') or 0}</td></tr>"
        for r in events
    ) or '<tr><td colspan="6" class="empty">No events in next 30 days</td></tr>'

    need_rows = "".join(
        f"<tr><td>P{r['priority']}</td><td>{_esc(r.get('client_name') or '—')}</td>"
        f"<td>{_esc(r['short_label'])}</td><td>{_esc(r.get('need_kind') or '—')}</td></tr>"
        for r in needs
    ) or '<tr><td colspan="4" class="empty">None open</td></tr>'

    act_rows = "".join(
        f"<tr><td>{str(r['timestamp'])[:16]}</td>"
        f"<td><span class='badge {'badge-sim' if r['kind']=='sim' else 'badge-ok'}'>{r['kind']}</span></td>"
        f"<td>{_esc(r.get('sender_name') or '?')}</td>"
        f"<td>{_esc(r.get('q') or '—')}</td>"
        f"<td>{_esc(r.get('reply') or '—')}</td>"
        f"<td>{r['rating'] or '—'}</td></tr>"
        for r in recent
    ) or '<tr><td colspan="6" class="empty">No interactions yet</td></tr>'

    portfolio_cards = "".join([
        _stat_card("Total docs", portfolio.get("total_docs", "?")),
        _stat_card("Clients", portfolio.get("clients", "?")),
        _stat_card("Active matters", portfolio.get("active_matters", "?")),
        _stat_card("Spine emails", portfolio.get("spine_emails", "?"), "v_gmail_relevant"),
    ])

    ops_cards = "".join([
        _stat_card("Docs 24h", ops.get("docs_24h", "?"), f"{ops.get('conv_24h', 0)} conversations"),
        _stat_card("Unclassified", ops.get("unclassified", "?"), '<a href="/files/">open files</a>'),
        _stat_card("Email triage", portfolio.get("triage_backlog", "?"), "needs linkage"),
        _stat_card("Client needs", portfolio.get("open_needs", "?")),
        _stat_card("Open actions", portfolio.get("open_actions", "?")),
        _stat_card("Open inquiries", portfolio.get("open_inquiries", "?"),
                   f"{portfolio.get('unauth_24h', 0)} unauth 24h"),
    ])

    leo_cards = "".join([
        _stat_card("Watchdog", wd.upper()),
        _stat_card("n8n", "OK" if n8n_ok else "DOWN",
                   f"{_pct(n8n_exec.get('err', 0), n8n_total)} err · {n8n_total} exec 24h"),
        _stat_card("Leo 24h", f"{leo.get('real_24h', 0)} real",
                   f"{leo.get('sim_24h', 0)} sim · 7d: {leo.get('real_7d', 0)}r/{leo.get('sim_7d', 0)}s"),
        _stat_card("QA shadow 24h", _pct(qa.get("pass_24h", 0), qa.get("runs_24h", 0)),
                   f"{qa.get('pass_24h', 0)}/{qa.get('runs_24h', 0)} · 1h: {_pct(qa.get('pass_1h', 0), qa.get('runs_1h', 0))}"),
        _stat_card("Arch sim", sim_line, "latest burst"),
        _stat_card("Cost 7d", f"${cost_logged:.2f}" if cost_logged else f"~${cost_est:.0f}/d est", cost_sub),
        _stat_card("Avg rating 30d", leo.get("avg_rating") or "—", "from rated interactions"),
    ])

    body = f"""
<h1>Morning briefing</h1>
<p class="lead">Portfolio, Leo pulse, deadlines — live SQL, no LLM.</p>
{''.join(alerts) if alerts else '<div class="alert alert-ok">No critical alerts</div>'}
<form class="searchbar" action="/ops/search" method="get" style="margin-bottom:20px">
  <input name="q" placeholder="Search docs, notes, entities…" minlength="2" required>
  <button type="submit">Search</button>
</form>
<div class="section-title">Portfolio</div>
<div class="grid grid-4" style="margin-bottom:8px">{portfolio_cards}</div>
<div class="section-title">Operations</div>
<div class="grid grid-3" style="margin-bottom:8px">{ops_cards}</div>
<div class="section-title">Leo &amp; quality</div>
<div class="grid grid-3" style="margin-bottom:16px">{leo_cards}</div>
<div class="grid grid-2">
  <div class="card"><h2>Upcoming deadlines</h2>
    <table><tr><th>Due</th><th>Title</th><th>Case</th><th>Status</th></tr>{dl_rows}</table>
  </div>
  <div class="card"><h2>Obligations at risk</h2>
    <table><tr><th>P</th><th>Label</th><th>Client</th><th>Due</th></tr>{obl_rows}</table>
  </div>
</div>
<div class="grid grid-2" style="margin-top:16px">
  <div class="card"><h2>Events next 30d</h2>
    <table><tr><th>Date</th><th>Case</th><th>Event</th><th>P</th><th>Ready%</th><th>Open prep</th></tr>{ev_rows}</table>
  </div>
  <div class="card"><h2>Client needs</h2>
    <table><tr><th>P</th><th>Client</th><th>Need</th><th>Kind</th></tr>{need_rows}</table>
  </div>
</div>
<div class="card" style="margin-top:16px"><h2>Recent Leo activity</h2>
  <table><tr><th>When</th><th>Kind</th><th>Sender</th><th>Question</th><th>Reply</th><th>★</th></tr>{act_rows}</table>
</div>
"""
    return _layout("Home", body, active="home")


@bp.route("/clients")
def clients():
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    rows = _safe_fetch(cur, conn, """
        SELECT c.case_file, c.name, c.client_code, c.priority_level, c.status,
               (SELECT COUNT(*) FROM documents d WHERE d.case_file = c.case_file) AS doc_count,
               (SELECT MAX(COALESCE(d.timestamp, d.created_at)) FROM documents d
                 WHERE d.case_file = c.case_file) AS last_doc,
               (SELECT COUNT(*) FROM landtek_obligations o
                 WHERE o.case_file = c.case_file AND o.status IN ('open','in_progress','blocked')) AS open_obl,
               (SELECT COUNT(*) FROM matters m
                 WHERE m.case_file = c.case_file AND m.status = 'active') AS matter_count,
               (SELECT phase_label FROM v_current_phase_per_case p
                 WHERE p.case_file = c.case_file LIMIT 1) AS phase,
               (SELECT COUNT(*) FROM v_open_client_needs n
                 WHERE n.client_code = c.client_code) AS open_needs,
               (SELECT events_7d FROM v_client_history_summary h
                 WHERE h.client_code = c.client_code LIMIT 1) AS events_7d
          FROM clients c
         WHERE c.case_file IS NOT NULL AND c.case_file != ''
         ORDER BY c.name
    """, default=[])
    cur.close()
    conn.close()

    trs = []
    for r in rows:
        cf = r["case_file"]
        trs.append(
            f"<tr><td><a href=\"/ops/client/{_esc(cf)}\">{_esc(r['name'] or cf)}</a></td>"
            f"<td><code>{_esc(cf)}</code></td>"
            f"<td>{r['doc_count']}</td><td>{r['matter_count']}</td><td>{r['open_obl']}</td>"
            f"<td>{r.get('open_needs') or 0}</td>"
            f"<td>{_esc((r.get('phase') or '—')[:24])}</td>"
            f"<td>{r.get('events_7d') or 0}</td>"
            f"<td>{_esc((r['priority_level'] or '')[:8])}</td>"
            f"<td>{_esc(str(r['last_doc'])[:10] if r['last_doc'] else '—')}</td>"
            f"<td><a href=\"/files/?case={_esc(cf)}\">files</a></td></tr>"
        )
    body = f"""
<h1>Clients</h1>
<p class="lead">Portfolio drill-down — docs, matters, phase, spine activity.</p>
<div class="card">
<table>
  <tr><th>Client</th><th>Case file</th><th>Docs</th><th>Matters</th><th>Obl.</th><th>Needs</th>
      <th>Phase</th><th>Events 7d</th><th>Prio</th><th>Last doc</th><th></th></tr>
  {''.join(trs) if trs else '<tr><td colspan="11" class="empty">No clients</td></tr>'}
</table>
</div>
"""
    return _layout("Clients", body, active="clients")


@bp.route("/client/<case_file>")
def client_detail(case_file: str):
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM clients WHERE case_file = %s", (case_file,))
    client = cur.fetchone()
    if not client:
        cur.close()
        conn.close()
        abort(404)

    cur.execute("""
        SELECT matter_code, title, status, current_stage, next_deadline, next_event, matter_type
          FROM matters WHERE case_file = %s AND status = 'active'
         ORDER BY matter_code
    """, (case_file,))
    matters = cur.fetchall()

    cur.execute("""
        SELECT id, short_label, priority, status, matter_code, due_by
          FROM landtek_obligations
         WHERE case_file = %s AND status IN ('open','in_progress','blocked')
         ORDER BY priority DESC
    """, (case_file,))
    obligations = cur.fetchall()

    cur.close()
    conn.close()

    m_rows = "".join(
        f"<tr><td><a href=\"/ops/matter/{_esc(m['matter_code'])}\">{_esc(m['matter_code'])}</a></td>"
        f"<td>{_esc(m.get('current_stage') or '—')}</td>"
        f"<td>{_esc(m.get('next_deadline') or '—')}</td>"
        f"<td>{_esc((m.get('next_event') or '')[:80])}</td></tr>"
        for m in matters
    ) or '<tr><td colspan="4" class="empty">No active matters</td></tr>'

    o_rows = "".join(
        f"<tr><td>P{o['priority']}</td><td>{_esc(o['short_label'])}</td>"
        f"<td>{_esc(o.get('matter_code') or '—')}</td><td>{_esc(o['status'])}</td></tr>"
        for o in obligations
    ) or '<tr><td colspan="4" class="empty">None</td></tr>'

    body = f"""
<h1>{_esc(client.get('name') or case_file)}</h1>
<p class="lead"><code>{_esc(case_file)}</code> · <a href="/files/?case={_esc(case_file)}">Browse files</a>
  · <a href="/ops/mwk">MWK lanes</a> (if MWK)</p>
<div class="grid grid-2">
  <div class="card"><h2>Active matters</h2>
    <table><tr><th>Matter</th><th>Stage</th><th>Deadline</th><th>Next</th></tr>{m_rows}</table>
  </div>
  <div class="card"><h2>Open obligations</h2>
    <table><tr><th>P</th><th>Label</th><th>Matter</th><th>Status</th></tr>{o_rows}</table>
  </div>
</div>
"""
    return _layout(client.get("name") or case_file, body, active="clients")


@bp.route("/mwk")
def mwk_hub():
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    lanes_html = []
    for code, track, _default_stage in MWK_LANES:
        cur.execute("""
            SELECT m.matter_code, m.current_stage, m.next_deadline, m.next_event, m.docket_number,
                   (SELECT COUNT(*) FROM documents d WHERE d.matter_code = m.matter_code) AS doc_n,
                   (SELECT COUNT(*) FROM landtek_obligations o
                     WHERE o.matter_code = m.matter_code
                       AND o.status IN ('open','in_progress','blocked')) AS open_obl,
                   (SELECT COUNT(*) FROM gmail_messages g
                     WHERE %s = ANY(g.matter_codes)) AS email_n
              FROM matters m WHERE m.matter_code = %s
        """, (code, code))
        m = cur.fetchone()
        cls = "lane"
        if "CV" in code:
            cls += " civil"
        elif "OP" in code:
            cls += " op"
        else:
            cls += " arta"
        if not m:
            lanes_html.append(f'<div class="{cls}"><strong>{_esc(code)}</strong> — not in DB</div>')
            continue
        lanes_html.append(f"""
<div class="{cls}">
  <strong><a href="/ops/matter/{_esc(code)}">{_esc(code)}</a></strong>
  <span class="badge badge-off">{_esc(track)}</span>
  <span class="muted"> · {m.get('doc_n', 0)} docs · {m.get('open_obl', 0)} obl · {m.get('email_n', 0)} email</span><br>
  <span class="muted">Stage:</span> {_esc(m.get('current_stage') or '—')}<br>
  <span class="muted">Deadline:</span> {_esc(m.get('next_deadline') or '—')}<br>
  <span class="muted">Docket:</span> {_esc(m.get('docket_number') or '—')}<br>
  <div style="margin-top:6px;font-size:13px">{_esc((m.get('next_event') or '')[:200])}</div>
</div>
""")
    cur.close()
    conn.close()
    body = f"""
<h1>MWK — separate tracks</h1>
<p class="lead">ARTA admin, OP supervisory, and civil trial are <strong>not</strong> one combined matter.</p>
<div class="card">{''.join(lanes_html)}</div>
"""
    return _layout("MWK", body, active="mwk")


@bp.route("/matter/<matter_code>")
def matter_detail(matter_code: str):
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM matters WHERE matter_code = %s", (matter_code,))
    m = cur.fetchone()
    if not m:
        cur.close()
        conn.close()
        abort(404)

    cur.execute("""
        SELECT COUNT(*) AS n FROM documents WHERE matter_code = %s
    """, (matter_code,))
    doc_n = cur.fetchone()["n"]

    emails = []
    try:
        cur.execute("""
            SELECT id, sent_at::date AS d, from_name, LEFT(subject, 90) AS subj
              FROM gmail_messages WHERE %s = ANY(matter_codes)
             ORDER BY sent_at DESC NULLS LAST LIMIT 10
        """, (matter_code,))
        emails = cur.fetchall()
    except Exception:
        pass

    cur.execute("""
        SELECT id, title, due_date, status FROM case_deadlines
         WHERE title ILIKE %s AND status != 'completed'
         ORDER BY due_date
    """, (f"%{matter_code.split('-')[-1]}%",))
    deadlines = cur.fetchall()

    cur.close()
    conn.close()

    em_rows = "".join(
        f"<tr><td>gmail#{r['id']}</td><td>{r['d']}</td><td>{_esc(r.get('from_name') or '?')}</td>"
        f"<td>{_esc(r.get('subj') or '—')}</td></tr>"
        for r in emails
    ) or '<tr><td colspan="4" class="empty">No linked emails</td></tr>'

    dl_rows = "".join(
        f"<tr><td>{_esc(r['due_date'])}</td><td>{_esc(r['title'])}</td><td>{_esc(r['status'])}</td></tr>"
        for r in deadlines
    ) or '<tr><td colspan="3" class="empty">None</td></tr>'

    body = f"""
<h1>{_esc(matter_code)}</h1>
<p class="lead">{_esc(m.get('title') or '')} · <a href="/files/?case={_esc(m.get('case_file') or '')}">Files</a>
  · {doc_n} docs tagged</p>
<div class="grid grid-2">
  <div class="card">
    <h2>Matter row</h2>
    <table>
      <tr><td>Stage</td><td>{_esc(m.get('current_stage'))}</td></tr>
      <tr><td>Agency</td><td>{_esc(m.get('court_or_agency'))}</td></tr>
      <tr><td>Docket</td><td>{_esc(m.get('docket_number'))}</td></tr>
      <tr><td>Next deadline</td><td>{_esc(m.get('next_deadline'))}</td></tr>
      <tr><td>Status</td><td>{_esc(m.get('status'))}</td></tr>
    </table>
    <p style="margin-top:10px;font-size:13px">{_esc(m.get('next_event') or '')}</p>
  </div>
  <div class="card"><h2>Deadlines (title match)</h2>
    <table><tr><th>Due</th><th>Title</th><th>Status</th></tr>{dl_rows}</table>
  </div>
</div>
<div class="card" style="margin-top:16px"><h2>Recent email (spine / tagged)</h2>
  <table><tr><th>ID</th><th>Date</th><th>From</th><th>Subject</th></tr>{em_rows}</table>
</div>
"""
    return _layout(matter_code, body, active="mwk")


@bp.route("/health")
def health_page():
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    open_holes_row = _safe_fetch(cur, conn,
        "SELECT COUNT(*) AS n FROM holes_findings WHERE status = 'open'",
        default={"n": 0}, one=True)
    open_holes = open_holes_row["n"] if open_holes_row else 0

    holes = _safe_fetch(cur, conn, """
        SELECT routine_name, severity, LEFT(description, 100) AS desc, created_at
          FROM holes_findings WHERE status = 'open'
         ORDER BY created_at DESC LIMIT 10
    """, default=[])

    hole_sev = _safe_fetch(cur, conn, """
        SELECT severity, COUNT(*) AS n FROM holes_findings
         WHERE status = 'open' GROUP BY severity ORDER BY severity
    """, default=[])

    sessions = _safe_fetch(cur, conn, """
        SELECT id, passed, failed, burst_size, completed_at::date AS d
          FROM simulator_sessions WHERE status = 'done'
         ORDER BY started_at DESC LIMIT 5
    """, default=[])

    sim_24h = _safe_fetch(cur, conn, """
        SELECT id, pack, started_at::date AS d, burst_size, passed, failed, pass_pct
          FROM v_simulator_sessions_24h ORDER BY started_at DESC LIMIT 8
    """, default=[])

    probe_trend = _safe_fetch(cur, conn, """
        SELECT probe_name, passes, fails, sessions, last_fail::date AS last_fail
          FROM v_simulator_probe_trend
         WHERE fails > 0
         ORDER BY fails DESC, sessions DESC
         LIMIT 8
    """, default=[])

    qa = _safe_fetch(cur, conn, """
        SELECT
          COUNT(*) FILTER (WHERE active) AS active_probes,
          COUNT(*) FILTER (WHERE NOT active) AS retired_probes
          FROM leo_qa_probes WHERE rail = 'sim'
    """, default={}, one=True) or {}

    qa_payload = _safe_fetch(cur, conn, """
        SELECT COUNT(*) FILTER (WHERE posted_at > now() - interval '24 hours') AS runs,
               COUNT(*) FILTER (WHERE posted_at > now() - interval '24 hours' AND passed) AS passed
          FROM leo_qa_sim_payloads
    """, default={}, one=True) or {}

    holes_runs = _safe_fetch(cur, conn, """
        SELECT routine_name, status, findings_count, p0_count, run_at::date AS d
          FROM holes_runs ORDER BY run_at DESC LIMIT 6
    """, default=[])

    n8n_exec = _safe_fetch(cur, conn, """
        SELECT COUNT(*) FILTER (WHERE status='error') AS err,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE status='success') AS ok
          FROM execution_entity
         WHERE "workflowId" = 'vSDQv1vfn6627bnA'
           AND "startedAt" > now() - interval '24 hours'
    """, default={"err": 0, "total": 0, "ok": 0}, one=True)

    leaks = _safe_fetch(cur, conn, """
        SELECT COUNT(*) AS n FROM real_traffic_violations
         WHERE detected_at > now() - interval '7 days'
    """, default={"n": 0}, one=True)

    cur.close()
    conn.close()

    timer_rows = []
    for tr in _timer_rows():
        timer_rows.append(
            f"<tr><td>{_esc(tr['label'])}</td><td><code>{_esc(tr['unit'])}</code></td>"
            f"<td>{_badge_timer(tr)}</td><td>{_esc(tr.get('enabled'))}</td>"
            f"<td>{_esc(tr.get('next'))}</td></tr>"
        )

    hole_rows = "".join(
        f"<tr><td>{_esc(h['severity'])}</td><td>{_esc(h['routine_name'])}</td>"
        f"<td>{_esc(h['desc'])}</td></tr>"
        for h in holes
    ) or '<tr><td colspan="3" class="empty">None open</td></tr>'

    sev_rows = "".join(
        f"<tr><td>{_esc(s['severity'])}</td><td>{s['n']}</td></tr>"
        for s in hole_sev
    ) or '<tr><td colspan="2" class="empty">0 open</td></tr>'

    sess_rows = "".join(
        f"<tr><td>#{s['id']}</td><td>{s['d']}</td><td>{s['passed']}/{s['burst_size']}</td>"
        f"<td>{s['failed']} fail</td></tr>"
        for s in sessions
    ) or '<tr><td colspan="4" class="empty">—</td></tr>'

    sim24_rows = "".join(
        f"<tr><td>#{s['id']}</td><td>{_esc(s.get('pack') or '—')}</td><td>{s['d']}</td>"
        f"<td>{s['passed']}/{s['burst_size']}</td><td>{s.get('pass_pct') or '—'}%</td></tr>"
        for s in sim_24h
    ) or '<tr><td colspan="5" class="empty">No bursts in 24h</td></tr>'

    trend_rows = "".join(
        f"<tr><td><code>{_esc(p['probe_name'])}</code></td><td>{p['passes']}</td>"
        f"<td>{p['fails']}</td><td>{p['sessions']}</td><td>{p.get('last_fail') or '—'}</td></tr>"
        for p in probe_trend
    ) or '<tr><td colspan="5" class="empty">No failing probes</td></tr>'

    run_rows = "".join(
        f"<tr><td>{_esc(r['routine_name'])}</td><td>{_esc(r['status'])}</td>"
        f"<td>{r.get('findings_count') or 0}</td><td>{r.get('p0_count') or 0}</td>"
        f"<td>{r['d']}</td></tr>"
        for r in holes_runs
    ) or '<tr><td colspan="5" class="empty">No runs logged</td></tr>'

    err_pct = round(100 * (n8n_exec["err"] or 0) / max(n8n_exec["total"] or 1, 1), 1)
    qa_runs = qa_payload.get("runs") or 0
    qa_pass = qa_payload.get("passed") or 0

    body = f"""
<h1>Health & triggers</h1>
<p class="lead">Timers, simulators, holes, n8n — full ops telemetry.</p>
<div class="grid grid-4" style="margin-bottom:16px">
  {_stat_card("Open holes", open_holes)}
  {_stat_card("n8n errors 24h", f"{err_pct}%", f"{n8n_exec['err']}/{n8n_exec['total']} execs")}
  {_stat_card("Watchdog", _watchdog_state().upper())}
  {_stat_card("QA shadow 24h", _pct(qa_pass, qa_runs), f"{qa_pass}/{qa_runs} payloads")}
  {_stat_card("Probe library", qa.get("active_probes", "?"), f"{qa.get('retired_probes', 0)} retired")}
  {_stat_card("Leak incidents 7d", leaks.get("n", 0), "real_traffic_violations")}
  {_stat_card("n8n success 24h", n8n_exec.get("ok", 0), f"of {n8n_exec.get('total', 0)} total")}
  {_stat_card("Arch bursts 24h", len(sim_24h), "v_simulator_sessions_24h")}
</div>
<div class="card"><h2>Systemd timers</h2>
<table><tr><th>Label</th><th>Unit</th><th>Status</th><th>Enabled</th><th>Next</th></tr>
{''.join(timer_rows)}</table>
</div>
<div class="grid grid-2" style="margin-top:16px">
  <div class="card"><h2>Open hole details</h2>
    <table><tr><th>Sev</th><th>Routine</th><th>Description</th></tr>{hole_rows}</table>
  </div>
  <div class="card"><h2>Holes by severity</h2>
    <table><tr><th>Severity</th><th>Count</th></tr>{sev_rows}</table>
  </div>
</div>
<div class="grid grid-2" style="margin-top:16px">
  <div class="card"><h2>Architecture sim — 24h</h2>
    <table><tr><th>ID</th><th>Pack</th><th>Date</th><th>Pass</th><th>%</th></tr>{sim24_rows}</table>
  </div>
  <div class="card"><h2>Probe failures (trend)</h2>
    <table><tr><th>Probe</th><th>Pass</th><th>Fail</th><th>Sessions</th><th>Last fail</th></tr>{trend_rows}</table>
  </div>
</div>
<div class="grid grid-2" style="margin-top:16px">
  <div class="card"><h2>Simulator sessions (all)</h2>
    <table><tr><th>ID</th><th>Date</th><th>Pass</th><th>Fail</th></tr>{sess_rows}</table>
  </div>
  <div class="card"><h2>Holes routine runs</h2>
    <table><tr><th>Routine</th><th>Status</th><th>Findings</th><th>P0</th><th>Date</th></tr>{run_rows}</table>
  </div>
</div>
"""
    return _layout("Health", body, active="health")


@bp.route("/search")
def search_page():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return _layout("Search", '<p class="empty">Enter at least 2 characters.</p>', active="home")
    like = f"%{q}%"
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, case_file, original_filename, classification
          FROM documents
         WHERE original_filename ILIKE %s OR extracted_text ILIKE %s
         ORDER BY id DESC LIMIT 25
    """, (like, like))
    docs = cur.fetchall()
    cur.execute("""
        SELECT id, case_file, LEFT(content, 120) AS snippet
          FROM chat_notes WHERE content ILIKE %s
         ORDER BY id DESC LIMIT 15
    """, (like,))
    notes = cur.fetchall()
    cur.close()
    conn.close()

    d_rows = "".join(
        f"<tr><td>{r['id']}</td><td>{_esc(r['case_file'])}</td>"
        f"<td><a href=\"/files/{r['id']}\">{_esc(r['original_filename'])}</a></td></tr>"
        for r in docs
    ) or '<tr><td colspan="3" class="empty">No documents</td></tr>'

    n_rows = "".join(
        f"<tr><td>{r['id']}</td><td>{_esc(r['case_file'])}</td><td>{_esc(r['snippet'])}</td></tr>"
        for r in notes
    ) or '<tr><td colspan="3" class="empty">No notes</td></tr>'

    body = f"""
<h1>Search: {_esc(q)}</h1>
<p class="lead"><a href="/api/search?q={_esc(q)}">JSON API</a></p>
<div class="grid grid-2">
  <div class="card"><h2>Documents</h2>
    <table><tr><th>ID</th><th>Case</th><th>File</th></tr>{d_rows}</table>
  </div>
  <div class="card"><h2>Chat notes</h2>
    <table><tr><th>ID</th><th>Case</th><th>Snippet</th></tr>{n_rows}</table>
  </div>
</div>
"""
    return _layout("Search", body, active="home")