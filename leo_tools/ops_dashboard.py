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

# Legal clients only — exclude Owner (Jonathan's bucket), Archive, triage stubs.
LEGAL_CLIENT_WHERE = """
  c.status = 'Active'
  AND c.case_file IS NOT NULL AND c.case_file != ''
  AND c.case_file NOT IN ('Owner', 'Archive')
  AND COALESCE(c.client_code, '') NOT IN ('Owner', 'Archive', 'PENDING_TRIAGE')
"""

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
        ("cases", "/cases", "Cases"),
        ("clients", "/clients", "Clients"),
        ("participants", "/participants", "People"),
        ("mwk", "/mwk", "MWK"),
        ("email", "/email", "Email"),
        ("events", "/events", "Events"),
        ("work", "/work", "Work"),
        ("ingestion", "/ingestion", "Ingestion"),
        ("history", "/history", "History"),
        ("health", "/health", "Health"),
        ("trajectory", "/trajectory", "Trajectory"),
        ("awareness", "/awareness", "Awareness"),
        ("dependability", "/dependability", "Dependability"),
        ("parcels", "/parcels", "Parcels"),
        ("readiness", "/readiness", "Titles"),
        ("spend", "/spend", "Spend"),
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


def _svc_state(unit: str):
    """(active, enabled) for a systemd unit, best-effort."""
    def _run(args):
        try:
            return (subprocess.run(args, capture_output=True, text=True, timeout=5).stdout or "").strip()
        except Exception:
            return "?"
    return _run(["systemctl", "is-active", unit]), _run(["systemctl", "is-enabled", unit])


# Loops that burn the shared Anthropic balance — should read inactive/disabled until
# the spend bridge is on AND credits are topped (otherwise they re-drain, like the outage).
_SPEND_LOOPS = [
    ("leo-simulator", "Leo simulator (n8n burn)"),
    ("landtek-truth-loop", "Truth QA loop"),
    ("landtek-fullstack-loop", "Fullstack SRE loop"),
]
# Core services that must stay active for real Leo to work.
_CORE_UNITS = [
    ("landtek-tg-router", "Telegram router (real Leo)"),
    ("landtek-tg-inbox", "Telegram inbox"),
    ("landtek-corpus-backfill", "Corpus backfill"),
]


@bp.route("/spend")
def spend_panel():
    """System & Spend cockpit: real LLM burn by source vs the daily cap, which
    loops are on/off, and a credit warning — the screen that makes a silent credit
    drain (the kind that took Leo down) impossible to miss."""
    import sys as _s
    _s.path.insert(0, "/root/landtek/scripts")
    try:
        import cost_governor as cg
        by_src = cg.today_spend_by_source()
        cap = float(cg.DAILY_CAP)
    except Exception:
        by_src, cap = {}, 8.0
    total = round(sum(by_src.values()), 4)

    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    n8n_exec = _safe_fetch(cur, conn, """
        SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE status = 'error') AS err
          FROM execution_entity
         WHERE "startedAt" > now() - interval '24 hours'
    """, default={}, one=True) or {}
    cur.close()
    conn.close()

    bridge_active, bridge_enabled = _svc_state("landtek-spend-bridge.timer")

    alerts = []
    if total >= cap:
        alerts.append(f'<div class="alert alert-bad">LLM spend today ${total:.2f} has hit the ${cap:.0f} cap — synthetic loops are now blocked by can_afford()</div>')
    elif total >= cap * 0.75:
        alerts.append(f'<div class="alert alert-warn">LLM spend today ${total:.2f} is near the ${cap:.0f} cap</div>')
    if bridge_active != "active" and bridge_enabled != "enabled":
        alerts.append('<div class="alert alert-warn">Spend bridge is OFF — n8n / simulator spend is NOT being recorded, so cost is partially blind. The activation runbook enables it FIRST.</div>')

    if by_src:
        spend_cards = "".join(_stat_card(src, f"${amt:.2f}", "today") for src, amt in by_src.items())
    else:
        spend_cards = _stat_card("LLM spend today", "$0.00", "nothing recorded yet")
    spend_cards += _stat_card("Total vs cap", f"${total:.2f} / ${cap:.0f}",
                              "synthetic stops at cap · client work to 3×")

    def _svc_card(unit, label, want_off=False):
        a, e = _svc_state(unit)
        ok = (a == "active")
        good = (not ok) if want_off else ok
        badge = "badge-ok" if good else ("badge-off" if want_off else "badge-bad")
        return (f'<div class="card"><h2>{_esc(label)}</h2>'
                f'<div><span class="badge {badge}">{_esc(a)}</span> '
                f'<span class="badge badge-off">{_esc(e)}</span></div>'
                f'<div class="stat-sub">{_esc(unit)}</div></div>')

    loop_cards = "".join(_svc_card(u, l, want_off=True) for u, l in _SPEND_LOOPS)
    core_cards = "".join(_svc_card(u, l) for u, l in _CORE_UNITS)
    n8n_total = n8n_exec.get("total") or 0

    body = f"""
<h1>System &amp; Spend</h1>
<p class="lead">Real LLM burn by source vs the daily cap, and what's turned on — the screen that makes a silent credit drain impossible.</p>
{''.join(alerts) or '<div class="alert alert-ok">Spend within cap.</div>'}
<div class="section-title">LLM spend today (real — from llm_spend, incl. n8n via the bridge)</div>
<div class="grid grid-4">{spend_cards}</div>
<div class="section-title">Synthetic loops — should read inactive/disabled until metering + credits</div>
<div class="grid grid-3">{loop_cards}</div>
<div class="section-title">Core services (must stay active for real Leo)</div>
<div class="grid grid-3">{core_cards}</div>
<div class="section-title">n8n + cost bridge</div>
<div class="grid grid-4">
  {_stat_card("n8n execs 24h", n8n_total, f"{n8n_exec.get('err', 0)} errored")}
  {_stat_card("Spend bridge", bridge_active, f"enabled={bridge_enabled}")}
</div>
<p class="muted" style="margin-top:16px">Spend recorded by <code>scripts/anthropic_spend_bridge.py</code> (n8n) + the Leo handler (python); cap = <code>LANDTEK_DAILY_LLM_CAP</code>.</p>
"""
    return _layout("Spend", body, active="spend")


# ── Trajectory / mission-control config (single source = MASTER_PLAN §4A; update as pillars advance) ──
_REQUIREMENTS = [
    ("Grounded", "ok", "truth_negotiator + _safe views + provenance grading"),
    ("Durable", "ok", "verified rows survive (claim verdicts, P-1617 title row)"),
    ("Complete corpus", "warn", None),   # % filled live below
    ("Proactive", "warn", "daily_digest + sentinels exist; QA loops paused for cost"),
    ("Affordable", "ok", "cost bridge + daily cap + /ops/spend (the $40/day leak sealed)"),
]
# pillar: (n, name, status, progress%, next-step)
_PILLARS = [
    (1, "Evidence &amp; Knowledge", "built", 85, "citations + immutable assertions live"),
    (2, "Legal Case Mgmt", "active", 80, "chain-of-title + Balane spine + geospatial (engine/parcels/vision/map); next: georeference + per-lot segmentation"),
    (3, "Finance &amp; Accounting", "early", 30, "ledger + P&amp;L/ROI views live; bill-extraction next"),
    (4, "Property Mgmt", "planned", 0, "v2.0 — tenants/rent/leases"),
    (5, "Proactive Intelligence", "partial", 40, "agentic calendar next"),
    (6, "Forensic &amp; Compliance", "early", 45, "hashing + dup detection live; signature-val next"),
    (7, "Platform &amp; Access", "partial", 55, "email channel feed built; RBAC formalization + WhatsApp/Messenger next"),
]
_COLD_INFRA = [
    ("Cost-metering bridge", True), ("/ops/spend cockpit", True),
    ("leo_qa_runner finish", True), ("activate_stack.sh runbook", True),
    ("Survey-geometry engine", True), ("Trajectory dashboard", True),
    ("Forensic hashing", True), ("Finance schema", True),
    ("Parcels + map endpoint", True), ("Survey vision-extract (Gemini)", True),
    ("Model-routing ladder", True), ("Email channel feed", True),
]
_SHIP_GATES = [
    ("Anthropic credit top-up", "blocked", "unlocks Leo + vision-extract + classify + routing + bill-extract"),
    ("Corpus drain (938 pending)", "open", "operational + classify is LLM-gated"),
    ("Geospatial vision-extract", "open", "Gemini free-tier; feeds the parcel parser"),
    ("Auto-rollback sentinel", "open", "low priority — truth_tests gate + manual revert cover it"),
]
_STATUS_BADGE = {"built": "badge-ok", "active": "badge-ok", "ok": "badge-ok",
                 "partial": "badge-warn", "early": "badge-warn", "warn": "badge-warn", "open": "badge-warn",
                 "planned": "badge-off", "blocked": "badge-bad"}


def _bar(pct: int) -> str:
    color = "#059669" if pct >= 80 else ("#2563eb" if pct >= 40 else "#d97706")
    return (f'<div style="background:#e5e7eb;border-radius:6px;height:8px;margin-top:6px;overflow:hidden">'
            f'<div style="background:{color};height:8px;width:{max(0,min(100,pct))}%"></div></div>')


@bp.route("/trajectory")
def trajectory():
    """Mission control: every pillar's status, the cold-infra build progress, the gates
    between here and a flawless ship, and live health — one screen for 'where are we?'"""
    import sys as _s
    _s.path.insert(0, "/root/landtek/scripts")
    try:
        import cost_governor as cg
        spend_today = round(sum(cg.today_spend_by_source().values()), 2)
        cap = float(cg.DAILY_CAP)
    except Exception:
        spend_today, cap = 0.0, 8.0

    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    corpus = _safe_fetch(cur, conn, """
        SELECT count(*) AS total,
               count(*) FILTER (WHERE ingest_status='classified') AS classified,
               count(*) FILTER (WHERE ingest_status='pending_classification') AS pending,
               count(*) FILTER (WHERE master_form='digital' AND coalesce(ingest_status,'') NOT IN
                     ('quarantined_dup','quarantined_ghost','quarantined_nobytes')) AS canonical
          FROM documents
    """, default={}, one=True) or {}
    cur.close(); conn.close()

    try:
        deploy = subprocess.run(["git", "-C", "/root/landtek", "log", "-1", "--pretty=%s"],
                                capture_output=True, text=True, timeout=5).stdout.strip()
        deploy_tag = (deploy.split(":")[0] if deploy.startswith("deploy_") else "—")
    except Exception:
        deploy_tag = "—"

    try:
        days_to_ship = (datetime(2026, 8, 12, tzinfo=timezone.utc) - datetime.now(timezone.utc)).days
    except Exception:
        days_to_ship = "—"

    overall = round(sum(p[3] for p in _PILLARS) / len(_PILLARS))
    corpus_pct = _pct(corpus.get("canonical", 0), corpus.get("total", 1))

    # requirements row (fill the corpus % live)
    req_cards = ""
    for name, status, note in _REQUIREMENTS:
        if name == "Complete corpus":
            note = f"{corpus.get('canonical',0)}/{corpus.get('total',0)} canonical · {corpus.get('pending',0)} pending"
        req_cards += (f'<div class="card"><h2>{name}</h2>'
                      f'<span class="badge {_STATUS_BADGE.get(status,"badge-off")}">{status}</span>'
                      f'<div class="stat-sub" style="margin-top:6px">{_esc(note or "")}</div></div>')

    pillar_cards = ""
    for n, name, status, pct, nxt in _PILLARS:
        pillar_cards += (f'<div class="card"><h2>Pillar {n} — {name}</h2>'
                         f'<span class="badge {_STATUS_BADGE.get(status,"badge-off")}">{status}</span>'
                         f'<span class="stat-sub" style="float:right">{pct}%</span>{_bar(pct)}'
                         f'<div class="stat-sub" style="margin-top:8px">next: {_esc(nxt)}</div></div>')

    done = sum(1 for _, ok in _COLD_INFRA if ok)
    infra_chips = " ".join(
        f'<span class="badge {"badge-ok" if ok else "badge-off"}">{"✓" if ok else "○"} {_esc(label)}</span>'
        for label, ok in _COLD_INFRA)

    gate_rows = "".join(
        f'<tr><td><span class="badge {_STATUS_BADGE.get(st,"badge-off")}">{st}</span></td>'
        f'<td>{_esc(name)}</td><td class="muted">{_esc(note)}</td></tr>'
        for name, st, note in _SHIP_GATES)

    body = f"""
<h1>Trajectory to Ship</h1>
<p class="lead">North star: <b>Aug 12, 2026</b> — Jonathan testifies (Civil Case 26-360). Build is architecture-first; the intelligence layer lights up on credit top-up.</p>
<div class="grid grid-4">
  {_stat_card("Overall readiness", f"{overall}%", "weighted across 7 pillars")}
  {_stat_card("Days to north star", days_to_ship, "Aug 12, 2026")}
  {_stat_card("Cold infra", f"{done}/{len(_COLD_INFRA)}", "scaffolding built")}
  {_stat_card("Latest deploy", deploy_tag, "git HEAD")}
</div>

<div class="section-title">5 Readiness Requirements</div>
<div class="grid grid-3">{req_cards}</div>

<div class="section-title">7 Capability Pillars</div>
<div class="grid grid-2">{pillar_cards}</div>

<div class="section-title">Cold-infra build sequence ({done}/{len(_COLD_INFRA)} done)</div>
<div class="card">{infra_chips}</div>

<div class="section-title">Gates between here and a flawless ship</div>
<div class="card"><table><tr><th>Status</th><th>Gate</th><th>Why it matters</th></tr>{gate_rows}</table></div>

<div class="section-title">Live signals</div>
<div class="grid grid-4">
  {_stat_card("Spend today", f"${spend_today:.2f} / ${cap:.0f}", "cap enforced via cost bridge")}
  {_stat_card("Corpus", f"{corpus_pct}", f"{corpus.get('canonical',0)} canonical · {corpus.get('pending',0)} pending")}
  {_stat_card("Proof clients", "2", "MWK-001 · Paracale-001")}
  {_stat_card("Cost target", "$6–15/day", ">85% inference margin")}
</div>
<p class="muted" style="margin-top:14px">Pillar status is curated from MASTER_PLAN §4A; live signals are real-time. See also <a href="/ops/spend">Spend</a> · <a href="/ops/health">Health</a>.</p>
"""
    return _layout("Trajectory", body, active="trajectory")


def _polygon_svg(pts, size=480, pad=24):
    if len(pts) < 3:
        return "<p class='empty'>No geometry.</p>"
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    w = (maxx - minx) or 1.0; h = (maxy - miny) or 1.0
    sc = (size - 2 * pad) / max(w, h)
    tx = lambda x: pad + (x - minx) * sc
    ty = lambda y: size - pad - (y - miny) * sc   # north up
    poly = " ".join(f"{tx(x):.1f},{ty(y):.1f}" for x, y in pts)
    return (f'<svg viewBox="0 0 {size} {size}" width="100%" '
            f'style="max-width:520px;background:#fff;border:1px solid var(--line);border-radius:8px">'
            f'<polygon points="{poly}" fill="#2563eb22" stroke="#2563eb" stroke-width="2"/></svg>')


def _axis_badge(grade: str) -> str:
    g = (grade or "unknown").lower()
    cls = {"solid": "badge-ok", "partial": "badge-warn", "thin": "badge-bad",
           "unknown": "badge-off"}.get(g, "badge-off")
    return f'<span class="badge {cls}">{_esc(g)}</span>'


def _score_bar(score) -> str:
    try:
        s = float(score or 0)
    except (TypeError, ValueError):
        s = 0.0
    pct = max(0, min(100, int(round(s * 100))))
    color = "#059669" if pct >= 70 else ("#d97706" if pct >= 40 else "#dc2626")
    return (f'<div style="display:flex;align-items:center;gap:8px;min-width:120px">'
            f'<div style="flex:1;height:8px;background:#e5e7eb;border-radius:4px;overflow:hidden">'
            f'<div style="width:{pct}%;height:100%;background:{color}"></div></div>'
            f'<span style="font-size:12px;font-weight:600;width:36px">{pct}%</span></div>')


@bp.route("/readiness")
def readiness_board():
    """Visual: status of each title across the six prep axes."""
    client = (request.args.get("client") or "").strip() or None
    weakest = (request.args.get("weakest") or "").strip() or None
    q = (request.args.get("q") or "").strip() or None
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT count(*) n, round(avg(readiness_score)::numeric,3) avg FROM property_readiness")
        summary = cur.fetchone() or {}
        cur.execute("SELECT weakest_axis, count(*) n FROM property_readiness GROUP BY 1 ORDER BY 2 DESC")
        by_weak = cur.fetchall()
        cur.execute("""SELECT finished_at, assets_seen, moves_open, note
                         FROM profitability_prep_cycles ORDER BY id DESC LIMIT 1""")
        last_cycle = cur.fetchone()
        sql = """
            SELECT r.*, a.label, a.title_ref, a.title_status, a.possession, a.tier, a.origin
              FROM property_readiness r
              JOIN property_assets a ON a.asset_code = r.asset_code
             WHERE 1=1
        """
        params = []
        if client:
            sql += " AND r.client_code = %s"; params.append(client)
        if weakest:
            sql += " AND r.weakest_axis = %s"; params.append(weakest)
        if q:
            sql += """ AND (a.asset_code ILIKE %s OR coalesce(a.title_ref,'') ILIKE %s
                            OR coalesce(a.label,'') ILIKE %s)"""
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
        sql += " ORDER BY r.readiness_score ASC NULLS FIRST, a.asset_code LIMIT 200"
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.execute("SELECT DISTINCT client_code FROM property_readiness WHERE client_code IS NOT NULL ORDER BY 1")
        clients = [r["client_code"] for r in cur.fetchall()]
    except Exception as e:
        cur.close(); conn.close()
        body = (f"<h1>Title readiness</h1><p class='alert alert-bad'>Readiness data unavailable: "
                f"{_esc(str(e)[:200])}. Run <code>profitability_prep_cycle.py</code> first.</p>")
        return _layout("Titles", body, active="readiness")
    cur.close(); conn.close()

    cards = (
        f"<div class='card'><div class='muted'>Titles scored</div>"
        f"<div class='stat'>{summary.get('n') or 0}</div></div>"
        f"<div class='card'><div class='muted'>Avg readiness</div>"
        f"<div class='stat'>{int(round(float(summary.get('avg') or 0)*100))}%</div></div>"
    )
    for w in by_weak[:4]:
        cards += (f"<div class='card'><div class='muted'>Weakest: {_esc(w['weakest_axis'])}</div>"
                  f"<div class='stat'>{w['n']}</div></div>")

    cycle_note = ""
    if last_cycle:
        cycle_note = (f"<p class='muted'>Last prep cycle: {_esc(str(last_cycle.get('finished_at') or '')[:19])} · "
                      f"open moves={last_cycle.get('moves_open')} · {_esc((last_cycle.get('note') or '')[:120])}</p>")

    filt = (
        f"<form class='searchbar' method='get' action='/ops/readiness' style='margin-bottom:16px;display:flex;gap:8px;flex-wrap:wrap'>"
        f"<input name='q' placeholder='Title / asset…' value='{_esc(q or '')}'>"
        f"<select name='client'><option value=''>All clients</option>"
        + "".join(f"<option value='{_esc(c)}'{' selected' if c==client else ''}>{_esc(c)}</option>" for c in clients)
        + f"</select><select name='weakest'><option value=''>Any weakest axis</option>"
        + "".join(f"<option value='{a}'{' selected' if a==weakest else ''}>{a}</option>"
                  for a in ("documents","status","occupants","ownership","title_issues","mapping"))
        + "</select><button type='submit'>Filter</button></form>"
    )

    if rows:
        trs = []
        for r in rows:
            title = r.get("title_ref") or r["asset_code"]
            trs.append(
                f"<tr>"
                f"<td><a href='/ops/readiness/{_esc(r['asset_code'])}'><strong>{_esc(title)}</strong></a>"
                f"<div class='muted' style='font-size:11px'>{_esc(r['asset_code'])} · {_esc(r.get('client_code') or '')}</div></td>"
                f"<td>{_score_bar(r.get('readiness_score'))}</td>"
                f"<td>{_axis_badge(r.get('documents'))}</td>"
                f"<td>{_axis_badge(r.get('status_axis'))}</td>"
                f"<td>{_axis_badge(r.get('occupants'))}</td>"
                f"<td>{_axis_badge(r.get('ownership'))}</td>"
                f"<td>{_axis_badge(r.get('title_issues'))}</td>"
                f"<td>{_axis_badge(r.get('mapping'))}</td>"
                f"<td class='muted' style='font-size:12px'>{_esc(r.get('weakest_axis') or '—')}</td>"
                f"</tr>"
            )
        table = (
            "<table><thead><tr>"
            "<th>Title</th><th>Score</th><th>Docs</th><th>Status</th><th>Occupants</th>"
            "<th>Ownership</th><th>Title issues</th><th>Map</th><th>Focus</th>"
            f"</tr></thead><tbody>{''.join(trs)}</tbody></table>"
        )
    else:
        table = "<p class='empty'>No readiness rows — run the prep cycle.</p>"

    body = (
        "<h1>Title readiness</h1>"
        "<p class='lead'>Continuous prep status per title — documents, status, occupants, "
        "ownership, title issues, mapping. Updated by the profitability prep cycle (every 4h).</p>"
        f"{cycle_note}"
        f"<div class='grid grid-4' style='margin-bottom:16px'>{cards}</div>"
        f"{filt}"
        f"<div class='card' style='overflow-x:auto'>{table}</div>"
        "<p class='muted' style='margin-top:12px'>solid=understood · partial=some signal · "
        "thin=weak · unknown=not yet assessed. Click a title for the prep worklist.</p>"
    )
    return _layout("Titles", body, active="readiness")


@bp.route("/readiness/<asset_code>")
def readiness_detail(asset_code: str):
    """Single title: six-axis status + open prep moves."""
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT r.*, a.label, a.title_ref, a.title_status, a.possession, a.tier, a.origin,
                   a.case_file, a.has_authority, a.location, a.modes, a.note
              FROM property_readiness r
              JOIN property_assets a ON a.asset_code = r.asset_code
             WHERE r.asset_code = %s""", (asset_code,))
        r = cur.fetchone()
        if not r:
            cur.execute("SELECT * FROM property_assets WHERE asset_code=%s", (asset_code,))
            a = cur.fetchone()
            cur.close(); conn.close()
            if not a:
                abort(404)
            body = (f"<h1>{_esc(asset_code)}</h1><p class='alert alert-warn'>No readiness score yet. "
                    f"Run <code>python3 scripts/profitability_prep_cycle.py --asset {_esc(asset_code)}</code>.</p>")
            return _layout(asset_code, body, active="readiness")
        cur.execute("""
            SELECT priority, axis, action, why, recheck_condition, last_seen_at
              FROM profitability_prep_moves
             WHERE asset_code=%s AND status='open'
             ORDER BY priority ASC, last_seen_at DESC LIMIT 40""", (asset_code,))
        moves = cur.fetchall()
    except Exception as e:
        cur.close(); conn.close()
        body = f"<h1>Error</h1><p class='alert alert-bad'>{_esc(str(e)[:200])}</p>"
        return _layout("Error", body, active="readiness")
    cur.close(); conn.close()

    title = r.get("title_ref") or asset_code
    axes = [
        ("Documents", "documents", r.get("documents"), r.get("documents_note")),
        ("Status", "status", r.get("status_axis"), r.get("status_note")),
        ("Occupants", "occupants", r.get("occupants"), r.get("occupants_note")),
        ("Ownership", "ownership", r.get("ownership"), r.get("ownership_note")),
        ("Title issues", "title_issues", r.get("title_issues"), r.get("title_issues_note")),
        ("Mapping", "mapping", r.get("mapping"), r.get("mapping_note")),
    ]
    axis_cards = "".join(
        f"<div class='card'><h2>{_esc(label)}</h2>{_axis_badge(grade)}"
        f"<p class='muted' style='margin:8px 0 0;font-size:12px'>{_esc(note or '—')}</p></div>"
        for label, _k, grade, note in axes
    )
    move_rows = "".join(
        f"<tr><td>p{m['priority']}</td><td>{_esc(m.get('axis') or '—')}</td>"
        f"<td><strong>{_esc(m['action'])}</strong>"
        f"<div class='muted' style='font-size:12px'>{_esc((m.get('why') or '')[:140])}</div></td>"
        f"<td class='muted' style='font-size:11px'>{_esc(str(m.get('last_seen_at') or '')[:16])}</td></tr>"
        for m in moves
    ) or "<tr><td colspan='4' class='empty'>No open prep moves — axes solid or cycle not run.</td></tr>"

    body = (
        f"<p class='muted'><a href='/ops/readiness'>← All titles</a></p>"
        f"<h1>{_esc(title)}</h1>"
        f"<p class='lead'>{_esc(r.get('label') or '')} · {_esc(r.get('client_code') or '')} · "
        f"status={_esc(r.get('title_status') or '—')} · possession={_esc(r.get('possession') or '—')}</p>"
        f"<div class='card' style='margin-bottom:16px'>"
        f"<div class='muted'>Readiness</div>{_score_bar(r.get('readiness_score'))}"
        f"<p style='margin:8px 0 0'>Weakest axis: <strong>{_esc(r.get('weakest_axis') or '—')}</strong></p>"
        f"<p class='muted' style='font-size:13px'>{_esc(r.get('next_prep_action') or '')}</p></div>"
        f"<div class='grid grid-3' style='margin-bottom:20px'>{axis_cards}</div>"
        f"<h2 class='section-title'>Open prep work</h2>"
        f"<div class='card'><table><tr><th>Pri</th><th>Axis</th><th>Action</th><th>Seen</th></tr>"
        f"{move_rows}</table></div>"
        f"<p class='muted' style='margin-top:12px'>Asset <code>{_esc(asset_code)}</code> · "
        f"case_file={_esc(r.get('case_file') or '—')} · tier={_esc(r.get('tier') or '—')} · "
        f"origin={_esc(r.get('origin') or '—')}</p>"
    )
    return _layout(title, body, active="readiness")


@bp.route("/parcels")
def parcels_list():
    import sys as _s; _s.path.insert(0, "/root/landtek/scripts")
    try:
        import parcels as P
        rows = P.list_parcels()
    except Exception:
        rows = []
    if rows:
        trs = "".join(
            f"<tr><td><a href='/ops/parcel/{r['id']}'>#{r['id']}</a></td>"
            f"<td>{_esc(r.get('title_no') or '—')}</td><td>{_esc(r.get('matter_code') or '—')}</td>"
            f"<td>{r.get('area_ha') or '—'}</td><td>{r.get('stated_ha') or '—'}</td>"
            f"<td>{'✓' if r.get('area_matches') else ('✗' if r.get('stated_ha') else '—')}</td>"
            f"<td>{r.get('closure_error_m') or '—'} m</td></tr>" for r in rows)
        table = ("<table><tr><th>Parcel</th><th>Title</th><th>Matter</th><th>Computed ha</th>"
                 f"<th>Stated ha</th><th>Match</th><th>Closure</th></tr>{trs}</table>")
    else:
        table = ("<p class='empty'>No parcels ingested yet — feed metes-and-bounds via "
                 "<code>parcels.upsert_parcel</code> (survey_vision_extract → survey_geometry).</p>")
    body = ("<h1>Parcels</h1><p class='lead'>Boundaries derived from survey metes-and-bounds "
            "(creditless engine); computed area cross-checked vs the title's stated hectares.</p>"
            f"<div class='card'>{table}</div>")
    return _layout("Parcels", body, active="parcels")


@bp.route("/parcel/<int:pid>")
def parcel_detail(pid):
    import sys as _s; _s.path.insert(0, "/root/landtek/scripts")
    import parcels as P
    rows = [r for r in P.list_parcels() if r["id"] == pid]
    if not rows:
        abort(404)
    r = rows[0]
    c = P._conn(); cur = c.cursor()
    cur.execute("SELECT geom_wkt FROM parcels WHERE id=%s", (pid,))
    wkt = (cur.fetchone() or [""])[0]; cur.close(); c.close()
    svg = _polygon_svg(P.wkt_points(wkt))
    match = "✓" if r.get("area_matches") else ("✗" if r.get("stated_ha") else "—")
    body = (f"<h1>Parcel #{pid}</h1><p class='lead'>{_esc(r.get('title_no') or '')} · "
            f"{_esc(r.get('matter_code') or '')}</p>"
            f"<div class='grid grid-4'>"
            f"{_stat_card('Computed area', str(r.get('area_ha'))+' ha')}"
            f"{_stat_card('Stated area', (str(r.get('stated_ha'))+' ha') if r.get('stated_ha') else '—')}"
            f"{_stat_card('Area match', match)}"
            f"{_stat_card('Closure error', str(r.get('closure_error_m'))+' m')}</div>"
            "<div class='section-title'>Boundary (local meters — shape; absolute georeferencing "
            f"pending a tie point)</div><div class='card'>{svg}</div>")
    return _layout(f"Parcel {pid}", body, active="parcels")


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


GLOBAL_STAFF_ROLES = {"owner", "filing_assistant", "operator"}


def _clearance_chips(row: dict) -> str:
    chips = []
    role = row.get("role") or row.get("approved_role") or "unknown"
    chips.append(f'<span class="badge badge-off">{_esc(role)}</span>')
    if row.get("can_admin"):
        chips.append('<span class="badge badge-warn">admin</span>')
    if row.get("can_verify"):
        chips.append('<span class="badge badge-ok">verify</span>')
    if row.get("can_transcribe"):
        chips.append('<span class="badge badge-off">transcribe</span>')
    if row.get("db_scope"):
        chips.append(f'<span class="badge badge-sim">{_esc(row["db_scope"])}</span>')
    if row.get("onboarding_state") == "awaiting_jonathan_approval":
        chips.append('<span class="badge badge-warn">pending</span>')
    elif row.get("authorized") is False:
        chips.append('<span class="badge badge-bad">blocked</span>')
    elif row.get("authorized") is True:
        chips.append('<span class="badge badge-ok">authorized</span>')
    return " ".join(chips)


def _participant_scope_label(row: dict) -> str:
    if row.get("scope") == "all_clients":
        return "All clients"
    parts = [p for p in (row.get("case_file"), row.get("client_code")) if p]
    return " · ".join(dict.fromkeys(parts)) or "—"


def _fetch_participants(cur, conn, client_code: str | None = None, case_file: str | None = None) -> list[dict]:
    """Merge authorized_users, channel_users, and client registry into one roster."""
    by_tg: dict[str, dict] = {}

    def _merge(row: dict):
        tg = str(row.get("telegram_user_id") or "").strip()
        if not tg or tg.startswith("999"):
            return
        prev = by_tg.get(tg)
        if prev:
            for k, v in row.items():
                if v is not None and v != "" and (prev.get(k) in (None, "", False)):
                    prev[k] = v
            return
        by_tg[tg] = row

    auth_rows = _safe_fetch(cur, conn, """
        SELECT au.name, au.role, au.telegram_user_id,
               au.can_transcribe, au.can_verify, au.can_admin,
               true AS authorized, 'authorized_users' AS source,
               c.case_file, c.client_code
          FROM authorized_users au
          LEFT JOIN clients c ON c.telegram_id = au.telegram_user_id
         WHERE au.active AND au.role <> 'sim_driver'
    """, default=[])
    for r in auth_rows:
        scope = "all_clients" if r["role"] in GLOBAL_STAFF_ROLES else "client"
        db_scope = "full" if r.get("can_admin") else ("verify" if r.get("can_verify") else "chat+files")
        _merge({**r, "scope": scope, "db_scope": db_scope})

    reg_rows = _safe_fetch(cur, conn, """
        SELECT c.name, COALESCE(c.role, 'contact') AS role, c.telegram_id AS telegram_user_id,
               c.authorized, c.case_file, c.client_code, 'clients' AS source
          FROM clients c
         WHERE c.telegram_id IS NOT NULL AND c.telegram_id <> ''
    """, default=[])
    for r in reg_rows:
        _merge({**r, "scope": "client", "db_scope": "client portal"})

    ch_rows = _safe_fetch(cur, conn, """
        SELECT cu.display_name AS name,
               COALESCE(cu.approved_role, cu.role, 'unknown') AS role,
               cu.channel_user_id AS telegram_user_id,
               cu.authorized, cu.onboarding_state,
               cu.approved_scope_case AS case_file,
               cu.mapped_client_code AS client_code,
               'channel_users' AS source,
               ch.name AS channel
          FROM channel_users cu
          JOIN channels ch ON ch.id = cu.channel_id
    """, default=[])
    for r in ch_rows:
        scope = "all_clients" if r["role"] in GLOBAL_STAFF_ROLES else "client"
        _merge({**r, "scope": scope, "db_scope": "telegram channel"})

    rows = list(by_tg.values())
    rows = _filter_participants(rows, client_code, case_file)
    rows.sort(key=lambda r: (0 if r.get("scope") == "all_clients" else 1, r.get("name") or ""))
    return rows


def _filter_participants(rows: list[dict], client_code: str | None = None, case_file: str | None = None) -> list[dict]:
    if not client_code and not case_file:
        return rows
    scoped = []
    for r in rows:
        if r.get("scope") == "all_clients":
            scoped.append(r)
            continue
        if client_code and r.get("client_code") == client_code:
            scoped.append(r)
            continue
        if case_file and r.get("case_file") == case_file:
            scoped.append(r)
    return scoped


def _participants_table(rows: list[dict], show_scope: bool = True) -> str:
    if not rows:
        return '<tr><td colspan="5" class="empty">No participants</td></tr>'
    out = []
    scope_col = "<th>Scope</th>" if show_scope else ""
    for r in rows:
        scope_td = f"<td>{_esc(_participant_scope_label(r))}</td>" if show_scope else ""
        tg = r.get("telegram_user_id") or "—"
        out.append(
            f"<tr><td>{_esc(r.get('name') or '—')}</td>"
            f"<td><code>{_esc(tg)}</code></td>"
            f"<td>{_esc(r.get('source') or '—')}</td>"
            f"<td>{_clearance_chips(r)}</td>{scope_td}</tr>"
        )
    hdr = f"<tr><th>Name</th><th>Telegram</th><th>Source</th><th>Clearance</th>{scope_col}</tr>"
    return hdr + "".join(out)


def _badge_relevance(status: str | None) -> str:
    s = (status or "unknown").lower()
    cls = "badge-off"
    if s in ("goal_linked", "assessed", "matter_linked"):
        cls = "badge-ok"
    elif s in ("unlinked", "client_only"):
        cls = "badge-warn"
    return f'<span class="badge {cls}">{_esc(status or "—")}</span>'


def _badge_risk(risk: str | None) -> str:
    m = {"overdue": "badge-bad", "imminent": "badge-bad", "approaching": "badge-warn"}
    return f'<span class="badge {m.get(risk or "", "badge-off")}">{_esc(risk or "—")}</span>'


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


@bp.route("/cases")
def cases():
    """Fluid case builder: each grievance → candidate forums + live corpus support."""
    conn = _db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT issue_no, title, detail, value_amount, status, maps_to_matters FROM client_issues ORDER BY issue_no")
        issues = cur.fetchall()
    except Exception:
        conn.rollback()
        return _layout("Case builder", '<h1>Case builder</h1><p class="empty">issue spine not loaded yet — run load_issue_spine.py / forum_router.py</p>', "cases")
    routes = {}
    try:
        cur.execute("""SELECT cf.issue_no, cf.forum_code, coalesce(am.name, cf.forum_code), cf.remedy, cf.status
                       FROM case_forums cf LEFT JOIN agency_mandates am ON am.code=cf.forum_code
                       ORDER BY cf.issue_no, cf.forum_code""")
        for ino, fc, name, remedy, st in cur.fetchall():
            routes.setdefault(ino, []).append((fc, name, remedy, st))
    except Exception:
        conn.rollback()
    cards = []
    for ino, title, detail, value, status, matters in issues:
        matters = matters or []
        vf = docs = filings = 0
        if matters:
            cur.execute("SELECT count(*) FROM matter_facts WHERE matter_code=ANY(%s) AND provenance_level='verified'", (matters,))
            vf = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM documents WHERE matter_code=ANY(%s)", (matters,))
            docs = cur.fetchone()[0]
            try:
                cur.execute("SELECT count(*) FROM filing_alerts WHERE matter_code=ANY(%s)", (matters,))
                filings = cur.fetchone()[0]
            except Exception:
                conn.rollback()
        val = f"₱{int(value):,}" if value else ""
        fhtml = ""
        for fc, name, remedy, st in routes.get(ino, []):
            b = "badge-ok" if st in ("chosen", "filed") else "badge-off"
            fhtml += (f'<div style="margin:4px 0"><span class="badge {b}" title="{_esc(name)}">{_esc(fc)}</span> '
                      f'<span class="muted">{_esc(remedy)}</span></div>')
        if not fhtml:
            fhtml = '<span class="empty">no forum routed</span>'
        mlist = ", ".join(matters[:4]) + ("…" if len(matters) > 4 else "")
        cards.append(f"""<div class="card">
          <div style="display:flex;justify-content:space-between;gap:8px">
            <strong>#{ino} {_esc(title)}</strong><span class="muted">{_esc(val)}</span></div>
          <div class="muted" style="font-size:12px;margin:4px 0 8px">{_esc((detail or '')[:170])}</div>
          <div style="font-size:12px;margin-bottom:8px">
            <span class="badge badge-ok">{vf} verified</span>
            <span class="badge badge-off">{docs} docs</span>
            <span class="badge badge-off">{filings} filings</span>
            <span class="muted" style="margin-left:6px">{_esc(mlist)}</span></div>
          <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:2px">Candidate forums</div>
          {fhtml}</div>""")
    body = (f'<h1>Case builder</h1>'
            f'<p class="lead">Each grievance → its candidate forums (from the oversight-mandate DB) with live corpus support. '
            f'Grows fluidly as the worker verifies facts, filing_monitor catches filings, and docs link in.</p>'
            f'<div class="grid grid-2">{"".join(cards)}</div>')
    conn.close()
    return _layout("Case builder", body, "cases")


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

    portfolio = _safe_fetch(cur, conn, f"""
        SELECT
          (SELECT COUNT(*) FROM documents) AS total_docs,
          (SELECT COUNT(*) FROM clients c WHERE {LEGAL_CLIENT_WHERE}) AS clients,
          (SELECT COUNT(*) FROM clients c
            WHERE c.case_file IS NOT NULL AND c.case_file != ''
              AND (c.case_file IN ('Owner', 'Archive')
                   OR c.client_code IN ('Owner', 'Archive', 'PENDING_TRIAGE')
                   OR c.status = 'Archived')) AS system_rows,
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

    pending_participants = _safe_fetch(cur, conn, """
        SELECT COUNT(*) AS n FROM channel_users
         WHERE onboarding_state = 'awaiting_jonathan_approval'
    """, default={"n": 0}, one=True)

    hist_summary = _safe_fetch(cur, conn, """
        SELECT client_code, events_7d, events_30d,
               most_recent_event::date AS last_event
          FROM v_client_history_summary
         ORDER BY events_7d DESC NULLS LAST
         LIMIT 4
    """, default=[])

    spine_recent = _safe_fetch(cur, conn, """
        SELECT id, mail_at::date AS d, client_code, direction,
               LEFT(subject, 80) AS subj
          FROM v_gmail_relevant
         ORDER BY mail_at DESC NULLS LAST
         LIMIT 5
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
    if pending_participants and pending_participants.get("n"):
        alerts.append(
            f'<div class="alert alert-warn">{pending_participants["n"]} participant(s) awaiting approval — '
            f'<a href="/ops/participants">Participants</a></div>'
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
        _stat_card("Clients", portfolio.get("clients", "?"),
                   f"{portfolio.get('system_rows', 0)} system rows hidden"),
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
        _stat_card("Pending access", pending_participants.get("n", 0) if pending_participants else 0,
                   '<a href="/ops/participants">participants</a>'),
    ])

    hist_rows = "".join(
        f"<tr><td>{_esc(h['client_code'])}</td><td>{h.get('events_7d') or 0}</td>"
        f"<td>{h.get('events_30d') or 0}</td><td>{h.get('last_event') or '—'}</td></tr>"
        for h in hist_summary
    ) or '<tr><td colspan="4" class="empty">No spine events</td></tr>'

    spine_rows = "".join(
        f"<tr><td>{r['d']}</td><td>{_esc(r.get('client_code') or '—')}</td>"
        f"<td>{_esc(r.get('direction') or '—')}</td>"
        f"<td>{_esc(r.get('subj') or '—')}</td></tr>"
        for r in spine_recent
    ) or '<tr><td colspan="4" class="empty">No spine emails</td></tr>'

    quick_nav = """
<div class="grid grid-4" style="margin-bottom:16px">
  <div class="card"><h2>Email</h2><p class="muted" style="margin:0 0 8px">Spine vs triage backlog</p>
    <a href="/ops/email">Open email hub →</a></div>
  <div class="card"><h2>Events</h2><p class="muted" style="margin:0 0 8px">30d calendar + prep %</p>
    <a href="/ops/events">Open events →</a></div>
  <div class="card"><h2>Work queue</h2><p class="muted" style="margin:0 0 8px">Obligations, needs, actions</p>
    <a href="/ops/work">Open work →</a></div>
  <div class="card"><h2>History</h2><p class="muted" style="margin:0 0 8px">Verified client_history spine</p>
    <a href="/ops/history">Open timeline →</a></div>
</div>
"""

    body = f"""
<h1>Morning briefing</h1>
<p class="lead">Portfolio, Leo pulse, deadlines — live SQL, no LLM.</p>
{''.join(alerts) if alerts else '<div class="alert alert-ok">No critical alerts</div>'}
<form class="searchbar" action="/ops/search" method="get" style="margin-bottom:20px">
  <input name="q" placeholder="Search docs, emails, notes, matters…" minlength="2" required>
  <button type="submit">Search</button>
</form>
{quick_nav}
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
<div class="grid grid-2" style="margin-top:16px">
  <div class="card"><h2>Spine activity (7d / 30d)</h2>
    <table><tr><th>Client</th><th>7d</th><th>30d</th><th>Last event</th></tr>{hist_rows}</table>
    <p style="margin:10px 0 0"><a href="/ops/history">Full timeline →</a></p>
  </div>
  <div class="card"><h2>Latest spine emails</h2>
    <table><tr><th>Date</th><th>Client</th><th>Dir</th><th>Subject</th></tr>{spine_rows}</table>
    <p style="margin:10px 0 0"><a href="/ops/email">Email hub →</a></p>
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
    rows = _safe_fetch(cur, conn, f"""
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
         WHERE {LEGAL_CLIENT_WHERE}
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
<p class="lead">Active legal clients only (MWK, Paracale) — Owner/Archive/triage excluded.</p>
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

    participants = _fetch_participants(
        cur, conn,
        client_code=client.get("client_code"),
        case_file=case_file,
    )

    phase = _safe_fetch(cur, conn, """
        SELECT phase_label, current_focus, success_criteria
          FROM v_current_phase_per_case WHERE case_file = %s LIMIT 1
    """, (case_file,), default=None, one=True)

    needs = _safe_fetch(cur, conn, """
        SELECT short_label, priority, need_kind FROM v_open_client_needs
         WHERE client_code = %s ORDER BY priority DESC LIMIT 8
    """, (client.get("client_code"),), default=[])

    history = _safe_fetch(cur, conn, """
        SELECT event_date, event_kind_canonical, LEFT(what_short, 100) AS what_short, citation_ref
          FROM v_client_recent_history
         WHERE client_code = %s
         ORDER BY COALESCE(event_datetime, event_date::timestamptz) DESC NULLS LAST
         LIMIT 12
    """, (client.get("client_code"),), default=[])

    hist_sum = _safe_fetch(cur, conn, """
        SELECT events_7d, events_30d, total_events_lifetime, most_recent_event::date AS last_event
          FROM v_client_history_summary WHERE client_code = %s LIMIT 1
    """, (client.get("client_code"),), default=None, one=True)

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

    n_rows = "".join(
        f"<tr><td>P{n['priority']}</td><td>{_esc(n['short_label'])}</td>"
        f"<td>{_esc(n.get('need_kind') or '—')}</td></tr>"
        for n in needs
    ) or '<tr><td colspan="3" class="empty">None</td></tr>'

    h_rows = "".join(
        f"<tr><td>{r.get('event_date') or '—'}</td>"
        f"<td>{_esc(r.get('event_kind_canonical') or '—')}</td>"
        f"<td>{_esc(r.get('what_short') or '—')}</td>"
        f"<td><code>{_esc(r.get('citation_ref') or '—')}</code></td></tr>"
        for r in history
    ) or '<tr><td colspan="4" class="empty">No spine events in last 30d</td></tr>'

    phase_block = ""
    if phase:
        phase_block = f"""
<div class="card" style="margin-bottom:16px"><h2>Current phase</h2>
  <p><strong>{_esc(phase.get('phase_label') or '—')}</strong></p>
  <p class="muted" style="margin:4px 0">{_esc(phase.get('current_focus') or '')}</p>
  <p class="muted" style="margin:0;font-size:12px">Success: {_esc((phase.get('success_criteria') or '')[:200])}</p>
</div>
"""

    hist_stats = ""
    if hist_sum:
        hist_stats = (
            f"{hist_sum.get('events_7d') or 0} events 7d · "
            f"{hist_sum.get('events_30d') or 0} 30d · "
            f"{hist_sum.get('total_events_lifetime') or 0} lifetime"
        )

    body = f"""
<h1>{_esc(client.get('name') or case_file)}</h1>
<p class="lead"><code>{_esc(case_file)}</code> · <code>{_esc(client.get('client_code') or '—')}</code>
  · <a href="/files/?case={_esc(case_file)}">Browse files</a>
  · <a href="/ops/mwk">MWK lanes</a> · <a href="/ops/history?client={_esc(client.get('client_code') or '')}">History</a></p>
<div class="grid grid-4" style="margin-bottom:16px">
  {_stat_card("Spine events 7d", hist_sum.get('events_7d', '—') if hist_sum else '—', hist_stats or 'client_history')}
  {_stat_card("Open obligations", len(obligations))}
  {_stat_card("Active matters", len(matters))}
  {_stat_card("Open needs", len(needs))}
</div>
{phase_block}
<div class="grid grid-2">
  <div class="card"><h2>Active matters</h2>
    <table><tr><th>Matter</th><th>Stage</th><th>Deadline</th><th>Next</th></tr>{m_rows}</table>
  </div>
  <div class="card"><h2>Open obligations</h2>
    <table><tr><th>P</th><th>Label</th><th>Matter</th><th>Status</th></tr>{o_rows}</table>
  </div>
</div>
<div class="grid grid-2" style="margin-top:16px">
  <div class="card"><h2>Client needs</h2>
    <table><tr><th>P</th><th>Need</th><th>Kind</th></tr>{n_rows}</table>
  </div>
  <div class="card"><h2>Spine timeline (30d)</h2>
    <table><tr><th>Date</th><th>Kind</th><th>What</th><th>Citation</th></tr>{h_rows}</table>
  </div>
</div>
<div class="card" style="margin-top:16px"><h2>Participants &amp; clearances</h2>
  <p class="muted" style="margin:0 0 10px;font-size:13px">
    Staff with global access shown for every client. Client-scoped users see only their matter/files.
  </p>
  <table>{_participants_table(participants, show_scope=True)}</table>
</div>
"""
    return _layout(client.get("name") or case_file, body, active="clients")


@bp.route("/participants")
def participants_hub():
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    client_rows = _safe_fetch(cur, conn, f"""
        SELECT case_file, name, client_code
          FROM clients c
         WHERE {LEGAL_CLIENT_WHERE}
         ORDER BY name
    """, default=[])

    pending = _safe_fetch(cur, conn, """
        SELECT display_name, channel_user_id, onboarding_state,
               COALESCE(onboarding_responses->>'inferred_name', '') AS inferred,
               COALESCE(onboarding_responses->>'matter_description', '') AS matter_desc
          FROM channel_users
         WHERE onboarding_state = 'awaiting_jonathan_approval'
         ORDER BY last_seen_at DESC NULLS LAST
    """, default=[])

    all_participants = _fetch_participants(cur, conn)
    cur.close()
    conn.close()

    staff = [p for p in all_participants if p.get("scope") == "all_clients"]
    sections = []
    for cl in client_rows:
        scoped = _filter_participants(
            all_participants,
            client_code=cl["client_code"],
            case_file=cl["case_file"],
        )
        sections.append(f"""
<div class="card" style="margin-bottom:16px">
  <h2><a href="/ops/client/{_esc(cl['case_file'])}">{_esc(cl['name'])}</a>
    <span class="muted">({_esc(cl['case_file'])})</span></h2>
  <table>{_participants_table(scoped, show_scope=False)}</table>
</div>
""")

    staff_block = f"""
<div class="card" style="margin-bottom:16px">
  <h2>LandTek staff — all-client access</h2>
  <table>{_participants_table(staff, show_scope=False)}</table>
</div>
""" if staff else ""

    pending_rows = "".join(
        f"<tr><td>{_esc(p.get('display_name') or p.get('inferred') or '?')}</td>"
        f"<td><code>{_esc(p.get('channel_user_id'))}</code></td>"
        f"<td>{_esc((p.get('matter_desc') or '')[:120])}</td></tr>"
        for p in pending
    ) or '<tr><td colspan="3" class="empty">None awaiting approval</td></tr>'

    body = f"""
<h1>Participants</h1>
<p class="lead">Each client can have many people — roles, Telegram IDs, and DB/file scope.
  Sources: <code>authorized_users</code>, <code>channel_users</code>, <code>clients</code>.</p>
<div class="grid grid-3" style="margin-bottom:16px">
  {_stat_card("Legal clients", len(client_rows))}
  {_stat_card("Distinct people", len(all_participants))}
  {_stat_card("Pending approval", len(pending))}
</div>
{staff_block}
{''.join(sections)}
<div class="card"><h2>Awaiting Jonathan approval</h2>
  <table><tr><th>Name</th><th>Telegram</th><th>What they asked for</th></tr>{pending_rows}</table>
</div>
"""
    return _layout("Participants", body, active="participants")


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

    arta = _safe_fetch(cur, conn, """
        SELECT ctn_no, status, last_activity, forum, respondents, subject_summary,
               email_count, attachment_count, next_deadline, next_action
          FROM arta_cases WHERE matter_code = %s
    """, (matter_code,), default=None, one=True)

    resolutions = _safe_fetch(cur, conn, """
        SELECT resolution_date, forum, disposition, source_doc_id,
               LEFT(COALESCE(disposition_summary, ''), 90) AS summary
          FROM resolutions WHERE %s = ANY(affected_matter_codes)
         ORDER BY resolution_date DESC NULLS LAST LIMIT 8
    """, (matter_code,), default=[])

    obligations = _safe_fetch(cur, conn, """
        SELECT short_label, priority, status, due_by
          FROM landtek_obligations
         WHERE matter_code = %s AND status IN ('open','in_progress','blocked')
         ORDER BY priority DESC
    """, (matter_code,), default=[])

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

    obl_rows = "".join(
        f"<tr><td>P{o['priority']}</td><td>{_esc(o['short_label'])}</td>"
        f"<td>{_esc(str(o.get('due_by') or '—')[:10])}</td>"
        f"<td>{_esc(o['status'])}</td></tr>"
        for o in obligations
    ) or '<tr><td colspan="4" class="empty">None</td></tr>'

    res_rows = "".join(
        f"<tr><td>{r.get('resolution_date') or '—'}</td><td>{_esc(r.get('forum') or '—')}</td>"
        f"<td><code>{_esc(r.get('disposition') or '—')}</code></td>"
        f"<td>{'doc#' + str(r['source_doc_id']) if r.get('source_doc_id') else '—'}</td>"
        f"<td>{_esc(r.get('summary') or '—')}</td></tr>"
        for r in resolutions
    ) or '<tr><td colspan="5" class="empty">No resolutions logged</td></tr>'

    arta_block = ""
    if arta:
        respondents = arta.get("respondents") or []
        resp = ", ".join(respondents) if respondents else "—"
        arta_block = f"""
<div class="card" style="margin-bottom:16px"><h2>ARTA case meta</h2>
  <table>
    <tr><td>CTN</td><td><code>{_esc(arta.get('ctn_no'))}</code></td></tr>
    <tr><td>Status</td><td>{_esc(arta.get('status'))}</td></tr>
    <tr><td>Forum</td><td>{_esc(arta.get('forum') or '—')}</td></tr>
    <tr><td>Respondents</td><td>{_esc(resp[:120])}</td></tr>
    <tr><td>Last activity</td><td>{_esc(arta.get('last_activity') or '—')}</td></tr>
    <tr><td>Email / attachments</td><td>{arta.get('email_count') or 0} / {arta.get('attachment_count') or 0}</td></tr>
    <tr><td>Next deadline</td><td>{_esc(arta.get('next_deadline') or '—')} — {_esc(arta.get('next_action') or '')}</td></tr>
  </table>
</div>
"""

    body = f"""
<h1>{_esc(matter_code)}</h1>
<p class="lead">{_esc(m.get('title') or '')} · <a href="/files/?case={_esc(m.get('case_file') or '')}">Files</a>
  · <a href="/ops/events">Events</a> · {doc_n} docs tagged</p>
{arta_block}
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
  <div class="card"><h2>Open obligations</h2>
    <table><tr><th>P</th><th>Label</th><th>Due</th><th>Status</th></tr>{obl_rows}</table>
  </div>
</div>
<div class="grid grid-2" style="margin-top:16px">
  <div class="card"><h2>Deadlines (title match)</h2>
    <table><tr><th>Due</th><th>Title</th><th>Status</th></tr>{dl_rows}</table>
  </div>
  <div class="card"><h2>Resolutions</h2>
    <table><tr><th>Date</th><th>Forum</th><th>Disposition</th><th>Doc</th><th>Summary</th></tr>{res_rows}</table>
  </div>
</div>
<div class="card" style="margin-top:16px"><h2>Recent email (spine / tagged)</h2>
  <table><tr><th>ID</th><th>Date</th><th>From</th><th>Subject</th></tr>{em_rows}</table>
  <p style="margin:10px 0 0"><a href="/ops/email?matter={_esc(matter_code)}">All email for this matter →</a></p>
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


@bp.route("/email")
def email_hub():
    client_filter = request.args.get("client", "").strip()
    matter_filter = request.args.get("matter", "").strip()
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    stats = _safe_fetch(cur, conn, """
        SELECT
          (SELECT COUNT(*) FROM v_gmail_relevant) AS spine_total,
          (SELECT COUNT(*) FROM v_correspondence_triage) AS triage_total,
          (SELECT COUNT(*) FROM v_gmail_relevant
            WHERE mail_at > now() - interval '7 days') AS spine_7d,
          (SELECT COUNT(*) FROM v_correspondence_triage
            WHERE COALESCE(received_at, sent_at) > now() - interval '7 days') AS triage_7d,
          (SELECT COUNT(*) FROM v_correspondence_triage
            WHERE relevance_status = 'unlinked') AS unlinked,
          (SELECT COUNT(*) FROM v_correspondence_triage
            WHERE relevance_status = 'client_only') AS client_only,
          (SELECT COUNT(*) FROM gmail_messages
            WHERE relevance_status IN ('goal_linked','assessed')) AS goal_linked
    """, default={}, one=True) or {}

    spine_params = []
    spine_where = ""
    if client_filter:
        spine_where = "WHERE client_code = %s"
        spine_params.append(client_filter)
    elif matter_filter:
        spine_where = "WHERE %s = ANY(matter_codes)"
        spine_params.append(matter_filter)

    spine = _safe_fetch(cur, conn, f"""
        SELECT id, mail_at::date AS d, client_code, direction,
               LEFT(subject, 100) AS subj, relevance_status, citation
          FROM v_gmail_relevant {spine_where}
         ORDER BY mail_at DESC NULLS LAST LIMIT 20
    """, tuple(spine_params), default=[])

    triage_params = []
    triage_where = ""
    if client_filter:
        triage_where = "WHERE client_code = %s"
        triage_params.append(client_filter)
    elif matter_filter:
        triage_where = "WHERE %s = ANY(matter_codes)"
        triage_params.append(matter_filter)

    triage = _safe_fetch(cur, conn, f"""
        SELECT gmail_id, sent_at::date AS d, client_code, relevance_status,
               link_count, LEFT(subject_short, 100) AS subj, from_addr
          FROM v_correspondence_triage {triage_where}
         ORDER BY COALESCE(received_at, sent_at) DESC NULLS LAST LIMIT 25
    """, tuple(triage_params), default=[])

    by_client = _safe_fetch(cur, conn, """
        SELECT client_code, COUNT(*) AS n
          FROM v_correspondence_triage
         WHERE client_code IS NOT NULL
         GROUP BY client_code ORDER BY n DESC LIMIT 8
    """, default=[])

    cur.close()
    conn.close()

    filter_note = ""
    if client_filter:
        filter_note = f' · filtered: client <code>{_esc(client_filter)}</code>'
    elif matter_filter:
        filter_note = f' · filtered: matter <code>{_esc(matter_filter)}</code>'

    spine_rows = "".join(
        f"<tr><td><code>{_esc(r.get('citation') or r['id'])}</code></td>"
        f"<td>{r['d']}</td><td>{_esc(r.get('client_code') or '—')}</td>"
        f"<td>{_esc(r.get('direction') or '—')}</td>"
        f"<td>{_esc(r.get('subj') or '—')}</td>"
        f"<td>{_badge_relevance(r.get('relevance_status'))}</td></tr>"
        for r in spine
    ) or '<tr><td colspan="6" class="empty">No spine emails</td></tr>'

    triage_rows = "".join(
        f"<tr><td>gmail#{r['gmail_id']}</td><td>{r['d']}</td>"
        f"<td>{_esc(r.get('client_code') or '—')}</td>"
        f"<td>{_esc((r.get('from_addr') or '')[:40])}</td>"
        f"<td>{_esc(r.get('subj') or '—')}</td>"
        f"<td>{_badge_relevance(r.get('relevance_status'))}</td>"
        f"<td>{r.get('link_count') or 0}</td></tr>"
        for r in triage
    ) or '<tr><td colspan="7" class="empty">Triage queue empty</td></tr>'

    client_rows = "".join(
        f"<tr><td>{_esc(c['client_code'])}</td><td>{c['n']}</td>"
        f"<td><a href=\"/ops/email?client={_esc(c['client_code'])}\">filter</a></td></tr>"
        for c in by_client
    ) or '<tr><td colspan="3" class="empty">—</td></tr>'

    body = f"""
<h1>Email</h1>
<p class="lead">Spine = verified legal events in <code>client_history</code>.
  Triage = correspondence needing client/matter/goal linkage{filter_note}</p>
<div class="grid grid-4" style="margin-bottom:16px">
  {_stat_card("Spine (total)", stats.get("spine_total", "?"), f"{stats.get('spine_7d', 0)} in 7d")}
  {_stat_card("Triage backlog", stats.get("triage_total", "?"), f"{stats.get('triage_7d', 0)} in 7d")}
  {_stat_card("Unlinked", stats.get("unlinked", "?"), "needs client")}
  {_stat_card("Goal-linked", stats.get("goal_linked", "?"), "assessed mail")}
</div>
<div class="grid grid-2">
  <div class="card"><h2>Spine — recent legal events</h2>
    <table><tr><th>Citation</th><th>Date</th><th>Client</th><th>Dir</th><th>Subject</th><th>Status</th></tr>
    {spine_rows}</table>
  </div>
  <div class="card"><h2>Triage — needs linkage</h2>
    <table><tr><th>ID</th><th>Date</th><th>Client</th><th>From</th><th>Subject</th><th>Status</th><th>Links</th></tr>
    {triage_rows}</table>
  </div>
</div>
<div class="card" style="margin-top:16px"><h2>Triage by client</h2>
  <table><tr><th>Client</th><th>Backlog</th><th></th></tr>{client_rows}</table>
</div>
"""
    return _layout("Email", body, active="email")


@bp.route("/events")
def events_hub():
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    events = _safe_fetch(cur, conn, """
        SELECT id, case_file, short_label, scheduled_for::date AS d, priority,
               readiness_pct, req_open, req_blocked, req_done, req_total,
               LEFT(expected_outcome, 80) AS outcome
          FROM v_upcoming_events_30d
         ORDER BY scheduled_for ASC NULLS LAST
    """, default=[])

    signals = _safe_fetch(cur, conn, """
        SELECT occurred_at::date AS d, signal_kind, short_text,
               acknowledged_at IS NULL AS unacked
          FROM v_active_priority_signals_7d
         ORDER BY occurred_at DESC LIMIT 10
    """, default=[])

    deadlines = _safe_fetch(cur, conn, """
        SELECT due_date, title, status, case_file
          FROM case_deadlines
         WHERE status != 'completed' AND due_date >= CURRENT_DATE - interval '3 days'
         ORDER BY due_date ASC LIMIT 12
    """, default=[])

    cur.close()
    conn.close()

    ev_rows = []
    for e in events:
        ready = e.get("readiness_pct") or 0
        ready_cls = "badge-ok" if ready >= 80 else ("badge-warn" if ready >= 50 else "badge-bad")
        ev_rows.append(
            f"<tr><td>{e['d']}</td><td>{_esc(e.get('case_file') or '—')}</td>"
            f"<td>{_esc(e.get('short_label') or '—')}</td><td>P{e['priority']}</td>"
            f"<td><span class='badge {ready_cls}'>{ready}%</span></td>"
            f"<td>{e.get('req_open') or 0} open · {e.get('req_blocked') or 0} blocked</td>"
            f"<td class='muted'>{_esc(e.get('outcome') or '')}</td></tr>"
        )
    ev_html = "".join(ev_rows) or '<tr><td colspan="7" class="empty">No events in next 30 days</td></tr>'

    sig_parts = []
    for s in signals:
        ack = (
            '<span class="badge badge-warn">unacked</span>'
            if s.get("unacked")
            else '<span class="badge badge-ok">acked</span>'
        )
        sig_parts.append(
            f"<tr><td>{s['d']}</td><td>{_esc(s.get('signal_kind') or '—')}</td>"
            f"<td>{_esc(s.get('short_text') or '—')}</td><td>{ack}</td></tr>"
        )
    sig_rows = "".join(sig_parts) or '<tr><td colspan="4" class="empty">No signals</td></tr>'

    dl_rows = "".join(
        f"<tr><td>{_esc(r['due_date'])}</td><td>{_esc(r.get('case_file') or '—')}</td>"
        f"<td>{_esc(r['title'])}</td><td>{_esc(r['status'])}</td></tr>"
        for r in deadlines
    ) or '<tr><td colspan="4" class="empty">None</td></tr>'

    blocked = sum(e.get("req_blocked") or 0 for e in events)
    low_ready = sum(1 for e in events if (e.get("readiness_pct") or 0) < 50)

    body = f"""
<h1>Events &amp; prep</h1>
<p class="lead">Next 30 days — readiness from <code>prep_requirements</code>.</p>
<div class="grid grid-4" style="margin-bottom:16px">
  {_stat_card("Events 30d", len(events))}
  {_stat_card("Blocked prep", blocked)}
  {_stat_card("Low readiness", low_ready, "&lt;50% ready")}
  {_stat_card("Priority signals 7d", len(signals))}
</div>
<div class="card"><h2>Upcoming events</h2>
  <table><tr><th>Date</th><th>Case</th><th>Event</th><th>P</th><th>Ready</th><th>Prep</th><th>Outcome</th></tr>
  {ev_html}</table>
</div>
<div class="grid grid-2" style="margin-top:16px">
  <div class="card"><h2>Priority signals (7d)</h2>
    <table><tr><th>Date</th><th>Kind</th><th>Text</th><th>Ack</th></tr>{sig_rows}</table>
  </div>
  <div class="card"><h2>Case deadlines</h2>
    <table><tr><th>Due</th><th>Case</th><th>Title</th><th>Status</th></tr>{dl_rows}</table>
  </div>
</div>
"""
    return _layout("Events", body, active="events")


@bp.route("/work")
def work_hub():
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    obligations = _safe_fetch(cur, conn, """
        SELECT id, short_label, client_code, priority, due_by, status, risk_window
          FROM v_obligations_at_risk
         ORDER BY priority DESC, due_by ASC NULLS LAST
         LIMIT 30
    """, default=[])

    by_client = _safe_fetch(cur, conn, """
        SELECT client_code, client_name, total_open, blocked, imminent, overdue
          FROM v_open_obligations_by_client
    """, default=[])

    needs = _safe_fetch(cur, conn, """
        SELECT client_name, short_label, priority, need_kind, created_at::date AS d
          FROM v_open_client_needs ORDER BY priority DESC LIMIT 20
    """, default=[])

    actions = _safe_fetch(cur, conn, """
        SELECT id, case_file, description, due_date, priority, status
          FROM action_items WHERE status = 'Open'
         ORDER BY
           CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END,
           due_date ASC NULLS LAST
         LIMIT 25
    """, default=[])

    cur.close()
    conn.close()

    obl_rows = "".join(
        f"<tr><td>P{r['priority']}</td><td>{_esc(r.get('client_code') or '—')}</td>"
        f"<td>{_esc(r['short_label'])}</td>"
        f"<td>{_esc(str(r.get('due_by') or '—')[:10])}</td>"
        f"<td>{_badge_risk(r.get('risk_window'))}</td>"
        f"<td>{_esc(r.get('status') or '—')}</td></tr>"
        for r in obligations
    ) or '<tr><td colspan="6" class="empty">None at risk</td></tr>'

    client_rows = "".join(
        f"<tr><td>{_esc(r.get('client_name') or r['client_code'])}</td>"
        f"<td>{r['total_open']}</td><td>{r.get('blocked') or 0}</td>"
        f"<td>{r.get('imminent') or 0}</td><td>{r.get('overdue') or 0}</td></tr>"
        for r in by_client
    ) or '<tr><td colspan="5" class="empty">—</td></tr>'

    need_rows = "".join(
        f"<tr><td>P{n['priority']}</td><td>{_esc(n.get('client_name') or '—')}</td>"
        f"<td>{_esc(n['short_label'])}</td><td>{_esc(n.get('need_kind') or '—')}</td>"
        f"<td>{n.get('d') or '—'}</td></tr>"
        for n in needs
    ) or '<tr><td colspan="5" class="empty">None</td></tr>'

    act_rows = "".join(
        f"<tr><td>P{_esc(str(a.get('priority') or '—'))}</td>"
        f"<td>{_esc(a.get('case_file') or '—')}</td>"
        f"<td>{_esc((a.get('description') or '')[:120])}</td>"
        f"<td>{_esc(str(a.get('due_date') or '—')[:10])}</td></tr>"
        for a in actions
    ) or '<tr><td colspan="4" class="empty">No open actions</td></tr>'

    overdue = sum(r.get("overdue") or 0 for r in by_client)

    body = f"""
<h1>Work queue</h1>
<p class="lead">What LandTek owes clients — obligations, needs, and Leo action items.</p>
<div class="grid grid-4" style="margin-bottom:16px">
  {_stat_card("At risk", len(obligations))}
  {_stat_card("Overdue (all)", overdue)}
  {_stat_card("Client needs", len(needs))}
  {_stat_card("Open actions", len(actions))}
</div>
<div class="card"><h2>Obligations at risk (14d window)</h2>
  <table><tr><th>P</th><th>Client</th><th>Label</th><th>Due</th><th>Risk</th><th>Status</th></tr>
  {obl_rows}</table>
</div>
<div class="grid grid-2" style="margin-top:16px">
  <div class="card"><h2>By client</h2>
    <table><tr><th>Client</th><th>Open</th><th>Blocked</th><th>14d</th><th>Overdue</th></tr>
    {client_rows}</table>
  </div>
  <div class="card"><h2>Client needs</h2>
    <table><tr><th>P</th><th>Client</th><th>Need</th><th>Kind</th><th>Since</th></tr>
    {need_rows}</table>
  </div>
</div>
<div class="card" style="margin-top:16px"><h2>Open action items</h2>
  <table><tr><th>P</th><th>Case</th><th>Description</th><th>Due</th></tr>{act_rows}</table>
</div>
"""
    return _layout("Work", body, active="work")


@bp.route("/ingestion")
def ingestion_hub():
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    stats = _safe_fetch(cur, conn, """
        SELECT
          (SELECT COUNT(*) FROM documents) AS total,
          (SELECT COUNT(*) FROM documents_needing_classification) AS unclassified,
          (SELECT COUNT(*) FROM documents
            WHERE COALESCE(timestamp, created_at) > now() - interval '24 hours') AS docs_24h,
          (SELECT COUNT(*) FROM documents
            WHERE COALESCE(timestamp, created_at) > now() - interval '7 days') AS docs_7d,
          (SELECT COUNT(*) FROM document_matter_links) AS matter_links,
          (SELECT COUNT(DISTINCT doc_id) FROM document_matter_links) AS linked_docs
    """, default={}, one=True) or {}

    unclassified = _safe_fetch(cur, conn, """
        SELECT id, case_file, original_filename, created_at::date AS d, ingest_source,
               LEFT(preview, 80) AS preview
          FROM documents_needing_classification
         ORDER BY created_at DESC LIMIT 25
    """, default=[])

    recent = _safe_fetch(cur, conn, """
        SELECT id, case_file, matter_code, original_filename,
               COALESCE(timestamp, created_at)::date AS d, ingest_source
          FROM documents
         ORDER BY COALESCE(timestamp, created_at) DESC NULLS LAST LIMIT 20
    """, default=[])

    by_case = _safe_fetch(cur, conn, f"""
        SELECT c.case_file, c.name,
               (SELECT COUNT(*) FROM documents d WHERE d.case_file = c.case_file) AS docs,
               (SELECT COUNT(*) FROM documents_needing_classification dnc
                 WHERE dnc.case_file = c.case_file) AS unclass
          FROM clients c
         WHERE {LEGAL_CLIENT_WHERE}
         ORDER BY unclass DESC, docs DESC
    """, default=[])

    cur.close()
    conn.close()

    unclass_rows = "".join(
        f"<tr><td>{r['id']}</td><td>{_esc(r.get('case_file') or '—')}</td>"
        f"<td><a href=\"/files/{r['id']}\">{_esc((r.get('original_filename') or '')[:60])}</a></td>"
        f"<td>{r['d']}</td><td>{_esc(r.get('ingest_source') or '—')}</td>"
        f"<td class='muted'>{_esc(r.get('preview') or '')}</td></tr>"
        for r in unclassified
    ) or '<tr><td colspan="6" class="empty">All docs classified</td></tr>'

    recent_rows = "".join(
        f"<tr><td>{r['d']}</td><td>{r['id']}</td><td>{_esc(r.get('case_file') or '—')}</td>"
        f"<td>{_esc(r.get('matter_code') or '—')}</td>"
        f"<td>{_esc((r.get('original_filename') or '')[:50])}</td>"
        f"<td>{_esc(r.get('ingest_source') or '—')}</td></tr>"
        for r in recent
    ) or '<tr><td colspan="6" class="empty">—</td></tr>'

    case_rows = "".join(
        f"<tr><td><a href=\"/ops/client/{_esc(r['case_file'])}\">{_esc(r['name'])}</a></td>"
        f"<td>{r['docs']}</td><td>{r['unclass']}</td>"
        f"<td><a href=\"/files/?case={_esc(r['case_file'])}\">files</a></td></tr>"
        for r in by_case
    ) or '<tr><td colspan="4" class="empty">—</td></tr>'

    link_pct = _pct(stats.get("linked_docs", 0), stats.get("total", 0))

    body = f"""
<h1>Ingestion</h1>
<p class="lead">Document pipeline — uploads, matter links, classification gaps.</p>
<div class="grid grid-4" style="margin-bottom:16px">
  {_stat_card("Total docs", stats.get("total", "?"))}
  {_stat_card("Unclassified", stats.get("unclassified", "?"), "no matter links")}
  {_stat_card("Ingested 24h", stats.get("docs_24h", "?"), f"{stats.get('docs_7d', 0)} in 7d")}
  {_stat_card("Matter-linked", link_pct, f"{stats.get('linked_docs', 0)} / {stats.get('total', 0)} docs")}
</div>
<div class="card"><h2>Needs classification</h2>
  <table><tr><th>ID</th><th>Case</th><th>File</th><th>Date</th><th>Source</th><th>Preview</th></tr>
  {unclass_rows}</table>
</div>
<div class="grid grid-2" style="margin-top:16px">
  <div class="card"><h2>Recent ingest</h2>
    <table><tr><th>Date</th><th>ID</th><th>Case</th><th>Matter</th><th>File</th><th>Source</th></tr>
    {recent_rows}</table>
  </div>
  <div class="card"><h2>By client</h2>
    <table><tr><th>Client</th><th>Docs</th><th>Unclassified</th><th></th></tr>{case_rows}</table>
  </div>
</div>
"""
    return _layout("Ingestion", body, active="ingestion")


@bp.route("/history")
def history_hub():
    client_filter = request.args.get("client", "").strip()
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    summaries = _safe_fetch(cur, conn, """
        SELECT client_code, total_events_lifetime, events_30d, events_7d,
               most_recent_event::date AS last_event
          FROM v_client_history_summary
         ORDER BY events_7d DESC NULLS LAST
    """, default=[])

    params = []
    hist_where = ""
    if client_filter:
        hist_where = "WHERE client_code = %s"
        params.append(client_filter)

    events = _safe_fetch(cur, conn, f"""
        SELECT client_code, event_date, event_kind_canonical, who_from,
               LEFT(what_short, 120) AS what_short, citation_ref, source_table
          FROM v_client_recent_history {hist_where}
         ORDER BY COALESCE(event_datetime, event_date::timestamptz) DESC NULLS LAST
         LIMIT 50
    """, tuple(params), default=[])

    by_kind = _safe_fetch(cur, conn, """
        SELECT event_kind_canonical, COUNT(*) AS n
          FROM v_client_recent_history
         WHERE event_kind_canonical IS NOT NULL
         GROUP BY event_kind_canonical ORDER BY n DESC LIMIT 12
    """, default=[])

    cur.close()
    conn.close()

    sum_rows = "".join(
        f"<tr><td><a href=\"/ops/history?client={_esc(s['client_code'])}\">{_esc(s['client_code'])}</a></td>"
        f"<td>{s.get('events_7d') or 0}</td><td>{s.get('events_30d') or 0}</td>"
        f"<td>{s.get('total_events_lifetime') or 0}</td>"
        f"<td>{s.get('last_event') or '—'}</td></tr>"
        for s in summaries
    ) or '<tr><td colspan="5" class="empty">No history</td></tr>'

    ev_rows = "".join(
        f"<tr><td>{r.get('event_date') or '—'}</td><td>{_esc(r.get('client_code') or '—')}</td>"
        f"<td>{_esc(r.get('event_kind_canonical') or '—')}</td>"
        f"<td>{_esc(r.get('who_from') or '—')}</td>"
        f"<td>{_esc(r.get('what_short') or '—')}</td>"
        f"<td><code>{_esc(r.get('citation_ref') or '—')}</code></td>"
        f"<td class='muted'>{_esc(r.get('source_table') or '')}</td></tr>"
        for r in events
    ) or '<tr><td colspan="7" class="empty">No events in last 30d</td></tr>'

    kind_rows = "".join(
        f"<tr><td>{_esc(k['event_kind_canonical'])}</td><td>{k['n']}</td></tr>"
        for k in by_kind
    ) or '<tr><td colspan="2" class="empty">—</td></tr>'

    filter_note = f' — <code>{_esc(client_filter)}</code>' if client_filter else ""

    body = f"""
<h1>Client history spine</h1>
<p class="lead">Verified legal events only — promos excluded. Last 30 days{filter_note}.
  {('<a href="/ops/history">Show all clients</a>' if client_filter else '')}</p>
<div class="grid grid-2">
  <div class="card"><h2>Per-client summary</h2>
    <table><tr><th>Client</th><th>7d</th><th>30d</th><th>Lifetime</th><th>Last</th></tr>{sum_rows}</table>
  </div>
  <div class="card"><h2>Event kinds (30d)</h2>
    <table><tr><th>Kind</th><th>Count</th></tr>{kind_rows}</table>
  </div>
</div>
<div class="card" style="margin-top:16px"><h2>Timeline</h2>
  <table><tr><th>Date</th><th>Client</th><th>Kind</th><th>Who</th><th>What</th><th>Citation</th><th>Source</th></tr>
  {ev_rows}</table>
</div>
"""
    return _layout("History", body, active="history")


@bp.route("/search")
def search_page():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return _layout("Search", '<p class="empty">Enter at least 2 characters.</p>', active="home")
    like = f"%{q}%"
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    docs = _safe_fetch(cur, conn, """
        SELECT id, case_file, original_filename, classification
          FROM documents
         WHERE original_filename ILIKE %s OR extracted_text ILIKE %s
         ORDER BY id DESC LIMIT 25
    """, (like, like), default=[])

    notes = _safe_fetch(cur, conn, """
        SELECT id, case_file, LEFT(content, 120) AS snippet
          FROM chat_notes WHERE content ILIKE %s
         ORDER BY id DESC LIMIT 15
    """, (like,), default=[])

    emails = _safe_fetch(cur, conn, """
        SELECT id, mail_at::date AS d, client_code, LEFT(subject, 90) AS subj, citation
          FROM v_gmail_relevant
         WHERE subject ILIKE %s OR body_plain ILIKE %s OR from_addr ILIKE %s
         ORDER BY mail_at DESC NULLS LAST LIMIT 15
    """, (like, like, like), default=[])

    matters = _safe_fetch(cur, conn, """
        SELECT matter_code, case_file, current_stage, status
          FROM matters
         WHERE matter_code ILIKE %s OR title ILIKE %s OR current_stage ILIKE %s
         ORDER BY matter_code LIMIT 15
    """, (like, like, like), default=[])

    obligations = _safe_fetch(cur, conn, """
        SELECT id, client_code, short_label, status, due_by::date AS due
          FROM landtek_obligations
         WHERE short_label ILIKE %s OR description ILIKE %s
         ORDER BY priority DESC LIMIT 15
    """, (like, like), default=[])

    history = _safe_fetch(cur, conn, """
        SELECT client_code, event_date, event_kind_canonical,
               LEFT(what_short, 100) AS what_short, citation_ref
          FROM v_client_recent_history
         WHERE what_short ILIKE %s OR who_from ILIKE %s
         ORDER BY COALESCE(event_datetime, event_date::timestamptz) DESC NULLS LAST
         LIMIT 15
    """, (like, like), default=[])

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

    e_rows = "".join(
        f"<tr><td><code>{_esc(r.get('citation') or r['id'])}</code></td><td>{r['d']}</td>"
        f"<td>{_esc(r.get('client_code') or '—')}</td>"
        f"<td>{_esc(r.get('subj') or '—')}</td></tr>"
        for r in emails
    ) or '<tr><td colspan="4" class="empty">No spine emails</td></tr>'

    m_rows = "".join(
        f"<tr><td><a href=\"/ops/matter/{_esc(r['matter_code'])}\">{_esc(r['matter_code'])}</a></td>"
        f"<td>{_esc(r.get('case_file') or '—')}</td>"
        f"<td>{_esc(r.get('current_stage') or '—')}</td>"
        f"<td>{_esc(r.get('status') or '—')}</td></tr>"
        for r in matters
    ) or '<tr><td colspan="4" class="empty">No matters</td></tr>'

    o_rows = "".join(
        f"<tr><td>{_esc(r.get('client_code') or '—')}</td>"
        f"<td>{_esc(r['short_label'])}</td><td>{r.get('due') or '—'}</td>"
        f"<td>{_esc(r.get('status') or '—')}</td></tr>"
        for r in obligations
    ) or '<tr><td colspan="4" class="empty">No obligations</td></tr>'

    h_rows = "".join(
        f"<tr><td>{r.get('event_date') or '—'}</td><td>{_esc(r.get('client_code') or '—')}</td>"
        f"<td>{_esc(r.get('event_kind_canonical') or '—')}</td>"
        f"<td>{_esc(r.get('what_short') or '—')}</td>"
        f"<td><code>{_esc(r.get('citation_ref') or '—')}</code></td></tr>"
        for r in history
    ) or '<tr><td colspan="5" class="empty">No history events</td></tr>'

    total = len(docs) + len(notes) + len(emails) + len(matters) + len(obligations) + len(history)

    body = f"""
<h1>Search: {_esc(q)}</h1>
<p class="lead">{total} results · <a href="/api/search?q={_esc(q)}">JSON API</a></p>
<div class="grid grid-2">
  <div class="card"><h2>Documents ({len(docs)})</h2>
    <table><tr><th>ID</th><th>Case</th><th>File</th></tr>{d_rows}</table>
  </div>
  <div class="card"><h2>Spine emails ({len(emails)})</h2>
    <table><tr><th>Citation</th><th>Date</th><th>Client</th><th>Subject</th></tr>{e_rows}</table>
  </div>
</div>
<div class="grid grid-2" style="margin-top:16px">
  <div class="card"><h2>Matters ({len(matters)})</h2>
    <table><tr><th>Matter</th><th>Case</th><th>Stage</th><th>Status</th></tr>{m_rows}</table>
  </div>
  <div class="card"><h2>Obligations ({len(obligations)})</h2>
    <table><tr><th>Client</th><th>Label</th><th>Due</th><th>Status</th></tr>{o_rows}</table>
  </div>
</div>
<div class="grid grid-2" style="margin-top:16px">
  <div class="card"><h2>History spine ({len(history)})</h2>
    <table><tr><th>Date</th><th>Client</th><th>Kind</th><th>What</th><th>Citation</th></tr>{h_rows}</table>
  </div>
  <div class="card"><h2>Chat notes ({len(notes)})</h2>
    <table><tr><th>ID</th><th>Case</th><th>Snippet</th></tr>{n_rows}</table>
  </div>
</div>
"""
    return _layout("Search", body, active="home")


@bp.route("/awareness")
def awareness():
    """Reliability cockpit: deadline coverage + awareness-score trend + verified-fact coverage."""
    import re as _re

    def _cn(label, val, cls=""):
        return (f'<div class="card"><div class="muted">{_esc(label)}</div>'
                f'<div style="font-size:26px;font-weight:700" class="{cls}">{_esc(val)}</div></div>')

    conn = _db(); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cards = dl_rows = trend = cov = ""
    try:
        cur.execute("SELECT max(as_of) m FROM surfaced_deadlines")
        row = cur.fetchone(); asof = row["m"] if row else None
        if asof:
            cur.execute("SELECT bucket, count(*) n FROM surfaced_deadlines WHERE as_of=%s GROUP BY bucket", (asof,))
            bc = {r["bucket"]: r["n"] for r in cur.fetchall()}
            cur.execute("""SELECT due_date, matter_code, label, bucket, days_out FROM surfaced_deadlines
                            WHERE as_of=%s AND bucket IN ('OVERDUE','THIS WEEK','THIS MONTH','UPCOMING')
                            ORDER BY due_date""", (asof,))
            for r in cur.fetchall():
                cls = "bad" if r["bucket"] == "OVERDUE" else "warn"
                when = f"{-r['days_out']}d ago" if (r["days_out"] or 0) < 0 else f"in {r['days_out']}d"
                dl_rows += (f"<tr><td>{_esc(r['due_date'])}</td><td>{_esc(r['matter_code'])}</td>"
                            f"<td class='{cls}'>{_esc(when)}</td><td>{_esc((r['label'] or '')[:64])}</td></tr>")
            cards += _cn("Overdue", bc.get("OVERDUE", 0), "bad")
            cards += _cn("This month", bc.get("THIS WEEK", 0) + bc.get("THIS MONTH", 0), "warn")
            cards += _cn("Upcoming", bc.get("UPCOMING", 0), "ok")
    except Exception as e:
        dl_rows = f"<tr><td colspan='4'>deadlines unavailable: {_esc(str(e)[:80])}</td></tr>"
    try:
        wr = _re.compile(r"observation_only|advisory|tracking|no_immediate_deadline|"
                         r"asset_development|declared_unrelated|under_review", _re.I)
        cur.execute("""SELECT matter_code, coalesce(current_stage,status) st FROM matters
                        WHERE next_deadline IS NULL AND (status IS NULL OR status NOT IN ('closed','archived'))""")
        needs = sum(1 for r in cur.fetchall()
                    if not r["matter_code"].startswith("AUTO-") and not wr.search(r["st"] or ""))
        cards += _cn("Need a date", needs, "warn")
    except Exception:
        pass
    try:
        cur.execute("SELECT ts, score, n_facts FROM awareness_log ORDER BY ts DESC LIMIT 14")
        rows = cur.fetchall()[::-1]
        if rows:
            cards += _cn("Awareness", f"{rows[-1]['score']}%", "ok")
            trend = "".join(f"<tr><td>{_esc(str(r['ts'])[:16])}</td><td>{_esc(r['score'])}%</td>"
                            f"<td>{_esc(r['n_facts'])}</td></tr>" for r in rows)
    except Exception as e:
        trend = f"<tr><td colspan='3'>trend unavailable: {_esc(str(e)[:80])}</td></tr>"
    try:
        cur.execute("""SELECT matter_code, count(*) FILTER (WHERE provenance_level='verified') v,
                              count(*) FILTER (WHERE provenance_level<>'verified') i
                         FROM matter_facts GROUP BY matter_code ORDER BY v DESC, i DESC LIMIT 12""")
        for r in cur.fetchall():
            cov += (f"<tr><td>{_esc(r['matter_code'])}</td><td class='ok'>{r['v']}</td>"
                    f"<td class='muted'>{r['i']}</td></tr>")
    except Exception:
        cov = "<tr><td colspan='3'>coverage unavailable</td></tr>"
    conn.close()
    body = f"""
<h1>Awareness</h1>
<div class="grid grid-2">{cards}</div>
<div class="grid grid-2" style="margin-top:16px">
  <div class="card"><h2>Due dates (latest surface)</h2>
    <table><tr><th>Date</th><th>Matter</th><th>When</th><th>What</th></tr>
    {dl_rows or "<tr><td colspan='4' class='muted'>none surfaced</td></tr>"}</table></div>
  <div class="card"><h2>Awareness score trend</h2>
    <table><tr><th>When</th><th>Score</th><th>Facts</th></tr>
    {trend or "<tr><td colspan='3' class='muted'>no log yet</td></tr>"}</table></div>
</div>
<div class="card" style="margin-top:16px"><h2>Verified-fact coverage (top matters)</h2>
  <table><tr><th>Matter</th><th>Verified</th><th>Inferred</th></tr>{cov}</table></div>
"""
    return _layout("Awareness", body, active="awareness")


@bp.route("/dependability")
def dependability():
    """The DEPENDABILITY gate — per-proof-client score (0-100), ship verdict, and the ranked gap
    list, read from the latest client_dependability run (scripts/client_dependability.py --write).

    This is the internal gate that decides whether a client should be handed their link. It is
    HONEST by construction: it renders whatever the harness measured, however low — a green here
    means the harness found zero correctness failures AND score >= threshold, nothing softer.
    If no run exists yet, it says so plainly rather than implying dependability."""
    conn = _db(); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    proof = ["MWK-001", "Paracale-001"]
    blocks = []
    top_cards = ""
    ran_any = False
    for cc in proof:
        row = _safe_fetch(cur, conn, """
            SELECT client_code, score, ship, sub_correct, sub_complete, sub_stable,
                   n_fail, n_warn, detail, run_at
              FROM client_dependability WHERE client_code=%s
             ORDER BY run_at DESC LIMIT 1
        """, (cc,), default=None, one=True)
        if not row:
            blocks.append(f'<div class="card"><h2>{_esc(cc)}</h2>'
                          f'<p class="empty">No dependability run yet — run '
                          f'<code>python3 scripts/client_dependability.py --write</code>.</p></div>')
            continue
        ran_any = True
        detail = row["detail"] or {}
        if isinstance(detail, str):
            try:
                detail = json.loads(detail)
            except Exception:
                detail = {}
        score = row["score"] or 0
        ship = row["ship"]
        thresh = detail.get("ship_threshold", 90)
        verdict_badge = ('<span class="badge badge-ok">READY TO SHIP</span>' if ship
                         else '<span class="badge badge-bad">NOT HANDOFF-READY</span>')
        score_cls = "ok" if ship else ("warn" if score >= 60 else "bad")
        top_cards += (f'<div class="card"><h2>{_esc(cc)}</h2>'
                      f'<div class="stat {score_cls}">{score:.0f}<span style="font-size:14px">/100</span></div>'
                      f'<div class="stat-sub">{verdict_badge} · {row["n_fail"]} fail · {row["n_warn"]} warn</div></div>')

        comp = detail.get("complete", {}) or {}
        stab = detail.get("stable", {}) or {}
        sub_rows = (
            f"<tr><th>Correct</th><td>{row['sub_correct']:.0f}</td>"
            f"<td>{row['n_fail']} fabricated/leak fails · {row['n_warn']} warns</td></tr>"
            f"<tr><th>Complete</th><td>{row['sub_complete']:.0f}</td>"
            f"<td>action-dated {comp.get('action_dated','?')}/{comp.get('action_matters','?')} · "
            f"docs {comp.get('docs_readable','?')}/{comp.get('docs_total','?')} readable · "
            f"verified {comp.get('facts_verified','?')}/{comp.get('facts','?')}</td></tr>"
            f"<tr><th>Stable</th><td>{row['sub_stable']:.0f}</td>"
            f"<td>portal {'ok' if stab.get('reach_ok') else 'BROKEN'} · "
            f"matters {stab.get('matters_rendered_ok','?')}/{stab.get('matters_total','?')} render · "
            f"fresh {stab.get('freshness_days','?')}d · "
            f"daemon {'ok' if stab.get('daemon_ok') else 'OFF'} · "
            f"failed units {stab.get('systemctl_failed','?')}</td></tr>"
        )
        gap_rows = ""
        for g in (detail.get("gaps") or [])[:20]:
            cls = "bad" if "/FAIL]" in g else ("warn" if "/WARN]" in g else "muted")
            gap_rows += f"<tr><td class='{cls}'>{_esc(g)}</td></tr>"
        if not gap_rows:
            gap_rows = "<tr><td class='ok'>No open gaps.</td></tr>"
        blocks.append(
            f'<div class="card" style="margin-bottom:16px">'
            f'<h2>{_esc(cc)} — {verdict_badge}</h2>'
            f'<p class="muted" style="font-size:12px">score {score:.1f}/100 (ship at &ge; {thresh} '
            f'& zero correctness fails) · measured {_esc(str(row["run_at"])[:16])} '
            f'· deadline surface {_esc(detail.get("as_of","?"))}</p>'
            f'<table>{sub_rows}</table>'
            f'<div class="section-title" style="margin-top:12px">Ranked gap list '
            f'<span class="muted">(fix top-down)</span></div>'
            f'<table>{gap_rows}</table></div>'
        )
    conn.close()
    intro = ('This gate decides whether a proof client can be handed their link. It is honest by '
             'construction — a green verdict requires ZERO correctness failures and score &ge; the '
             'threshold; anything softer stays red.')
    if not ran_any:
        intro += ' <strong>No run recorded yet.</strong>'
    body = f"""
<h1>Dependability gate</h1>
<p class="lead">{intro}</p>
<div class="grid grid-2" style="margin-bottom:16px">{top_cards}</div>
{''.join(blocks)}
<p class="muted" style="margin-top:16px;font-size:12px">
  Correct = per-fact grounding / no phantom date / no stale surface / no internal-fragment or
  draft leak / client-matter separation, audited on the LIVE rendered client view. One correctness
  failure tanks the score and blocks the gate. Refresh: <code>client_dependability.py --write</code>.</p>
"""
    return _layout("Dependability", body, active="dependability")