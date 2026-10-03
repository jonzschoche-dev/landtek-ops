"""LandTek Console — the ONE place to test the product and the stack.

Built 2026-10-03 after the surface audit found ~60 working-but-disconnected pages and
no single view that MEASURES the product (MASTER_PLAN §0.9) or lets the operator TEST it.
Three panels, all live SQL, no new framework (reuses the /ops cockpit chrome):

  1. STACK   — the §0 scorecard (fronts dated, overdue, goals dated, drip clocks, stuck
               orders, the next 14 days) + machine health (failed units, disk, truth tests).
  2. PRODUCT — each client as they would see it (the same render the token portal serves),
               with that client's numbers and how many live client links exist.
  3. BRAIN   — ask Leo a question for a client and see the reply + how it was produced.
               Runs leo_service.generate_reply(dry_run=True) inside a transaction that is
               ALWAYS rolled back (the Improvement Lab pattern): zero persistent effect.

Internal only: mounted under /ops/ (nginx basic-auth). Read-only except the rolled-back ask.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import date

import psycopg2
import psycopg2.extras
from flask import Blueprint, request

from ops_dashboard import PG_DSN, _esc, _layout, _safe_fetch, _stat_card

bp = Blueprint("ops_console", __name__, url_prefix="/ops/console")

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")

# Active = a real matter that is not closed (AUTO- triage stubs excluded) — same
# definition the §0 survey and the client portal use.
_ACTIVE = ("matter_code NOT LIKE 'AUTO-%%' AND COALESCE(status,'') NOT IN ('closed','archived')")

SUGGESTED = [
    ("MWK-001", "When is the next hearing in the Balane case?"),
    ("MWK-001", "Who holds TCT 079-2021002126?"),
    ("MWK-001", "What is the status of the ARTA 1378 case?"),
    ("Paracale-001", "What permits are pending for AVI?"),
]


def _db():
    return psycopg2.connect(PG_DSN)


def _run(cmd, timeout=10):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception as e:  # degrade, never crash the page
        return f"(unavailable: {type(e).__name__})"


# ───────────────────────────── 1. STACK ─────────────────────────────

def _scorecard(cur, conn) -> str:
    today = date.today()
    tot = _safe_fetch(cur, conn, f"SELECT count(*) AS n FROM matters WHERE {_ACTIVE}", one=True) or {}
    fut = _safe_fetch(cur, conn, f"SELECT count(*) AS n FROM matters WHERE {_ACTIVE} "
                      "AND next_deadline >= CURRENT_DATE", one=True) or {}
    overdue = _safe_fetch(cur, conn, f"""
        SELECT matter_code, client_code, next_deadline, left(COALESCE(next_event,''),110) AS ev
          FROM matters WHERE {_ACTIVE} AND next_deadline < CURRENT_DATE
         ORDER BY next_deadline""", default=[])
    upcoming = _safe_fetch(cur, conn, f"""
        SELECT matter_code, client_code, next_deadline, left(COALESCE(next_event,''),110) AS ev
          FROM matters WHERE {_ACTIVE}
           AND next_deadline BETWEEN CURRENT_DATE AND CURRENT_DATE + 14
         ORDER BY next_deadline""", default=[])
    goals = _safe_fetch(cur, conn, """
        SELECT count(*) AS n, count(*) FILTER (WHERE target_date IS NOT NULL) AS dated
          FROM client_goals WHERE COALESCE(status,'active') NOT IN ('achieved','cancelled','dropped')""",
                        one=True) or {}
    drip = _safe_fetch(cur, conn, """
        SELECT count(*) AS n,
               count(*) FILTER (WHERE served_at IS NOT NULL) AS served,
               count(*) FILTER (WHERE served_at IS NOT NULL AND due_at >= now()) AS running,
               string_agg(DISTINCT state, ', ') AS states
          FROM office_obligation""", one=True) or {}
    wo = _safe_fetch(cur, conn, """
        SELECT count(*) FILTER (WHERE status NOT IN ('done','cancelled')) AS open,
               count(*) FILTER (WHERE status NOT IN ('done','cancelled')
                                AND updated_at < now() - interval '72 hours') AS stuck,
               count(*) FILTER (WHERE status = 'done') AS done
          FROM work_orders""", one=True) or {}

    n_tot, n_fut = tot.get("n") or 0, fut.get("n") or 0
    pct = f"{round(100 * n_fut / n_tot)}%" if n_tot else "—"
    cards = "".join([
        _stat_card("Fronts with a dated next move", f"{n_fut} / {n_tot}", f"{pct} · target 100%"),
        _stat_card("Overdue — date passed, still open", len(overdue), "each needs a re-date or outcome"),
        _stat_card("Client goals dated", f"{goals.get('dated') or 0} / {goals.get('n') or 0}",
                   "§0: an undated goal does not exist"),
        _stat_card("Drip clocks running", drip.get("running") or 0,
                   f"{drip.get('served') or 0} of {drip.get('n') or 0} served · {_esc(drip.get('states') or '')}"),
        _stat_card("Work orders stuck > 72h", wo.get("stuck") or 0,
                   f"{wo.get('open') or 0} open · {wo.get('done') or 0} done"),
    ])

    def _rows(rows, empty):
        if not rows:
            return f'<p class="empty">{empty}</p>'
        body = "".join(
            f"<tr><td style='white-space:nowrap'>{_esc(r['next_deadline'])}</td>"
            f"<td><a href='/ops/matter/{_esc(r['matter_code'])}'>{_esc(r['matter_code'])}</a></td>"
            f"<td class='muted'>{_esc(r['client_code'])}</td><td>{_esc(r['ev'])}</td></tr>"
            for r in rows)
        return f"<table><tr><th>Date</th><th>Matter</th><th>Client</th><th>Next event</th></tr>{body}</table>"

    return (f'<div class="grid-4">{cards}</div>'
            f'<div class="section-title">Next 14 days</div><div class="card">'
            f'{_rows(upcoming, "Nothing dated in the next 14 days.")}</div>'
            f'<div class="section-title">Overdue — date passed, still open '
            f'<span class="muted">({len(overdue)})</span></div><div class="card">'
            f'{_rows(overdue, "Nothing overdue.")}</div>')


def _health() -> str:
    failed = _run(["systemctl", "--failed", "--no-legend", "--plain"])
    failed_units = [ln.split()[0] for ln in failed.splitlines() if ln.strip() and not ln.startswith("(")]
    du = shutil.disk_usage("/")
    disk_pct = round(100 * du.used / du.total)
    tt = _run(["systemctl", "show", "landtek-truth-tests.service",
               "-p", "Result", "-p", "ExecMainExitTimestamp", "--value"]).splitlines()
    tt_result = tt[0] if tt else "?"
    tt_when = tt[1] if len(tt) > 1 else ""
    leo = _run(["systemctl", "is-active", "leo-tools.service"])
    cards = "".join([
        _stat_card("Failed units", len(failed_units), ", ".join(failed_units) or "none — target 0"),
        _stat_card("Disk used", f"{disk_pct}%", "target under 85%"),
        _stat_card("Truth tests (nightly)", "passing" if tt_result == "success" else tt_result,
                   _esc(tt_when)),
        _stat_card("leo-tools service", leo, "serves /ops, /client, the APIs"),
    ])
    return f'<div class="grid-4">{cards}</div>'


# ───────────────────────────── 2. PRODUCT ─────────────────────────────

def _product(cur, conn) -> str:
    clients = _safe_fetch(cur, conn, """
        SELECT c.client_code, c.name,
               (SELECT count(*) FROM matters m WHERE m.client_code = c.client_code
                  AND m.matter_code NOT LIKE 'AUTO-%%'
                  AND COALESCE(m.status,'') NOT IN ('closed','archived')) AS active,
               (SELECT count(*) FROM matters m WHERE m.client_code = c.client_code
                  AND m.matter_code NOT LIKE 'AUTO-%%'
                  AND COALESCE(m.status,'') NOT IN ('closed','archived')
                  AND m.next_deadline >= CURRENT_DATE) AS dated,
               (SELECT min(next_deadline) FROM matters m WHERE m.client_code = c.client_code
                  AND m.next_deadline >= CURRENT_DATE) AS next_date,
               (SELECT score FROM client_dependability d WHERE d.client_code = c.client_code
                 ORDER BY run_at DESC LIMIT 1) AS dep_score,
               (SELECT count(*) FROM client_access_tokens t WHERE t.client_code = c.client_code
                  AND t.revoked_at IS NULL) AS live_links
          FROM clients c
         WHERE c.client_code IS NOT NULL AND c.client_code <> ''
           AND c.client_code NOT IN ('Archive','PENDING_TRIAGE')
           AND EXISTS (SELECT 1 FROM matters m WHERE m.client_code = c.client_code
                         AND m.matter_code NOT LIKE 'AUTO-%%'
                         AND COALESCE(m.status,'') NOT IN ('closed','archived'))
         ORDER BY c.client_code""", default=[])
    if not clients:
        return '<p class="empty">No clients found.</p>'
    rows = []
    for c in clients:
        cc = _esc(c["client_code"])
        links = c["live_links"] or 0
        link_badge = (f"<span class='badge badge-warn'>{links} live client link(s)</span>"
                      if links else "<span class='badge badge-off'>no live links</span>")
        dep = "—" if c["dep_score"] is None else f"{float(c['dep_score']):.1f}"
        rows.append(
            f"<tr><td><strong>{_esc(c['name'] or c['client_code'])}</strong>"
            f"<div class='muted'>{cc}</div></td>"
            f"<td>{c['dated']} / {c['active']}</td>"
            f"<td>{_esc(c['next_date'] or '—')}</td>"
            f"<td>{dep}</td><td>{link_badge}</td>"
            f"<td style='white-space:nowrap'>"
            f"<a class='badge badge-ok' href='/ops/portal/{cc}/portfolio'>Home as client sees it</a> "
            f"<a class='badge badge-ok' href='/ops/portal/{cc}'>Cases view</a></td></tr>")
    return ("<p class='muted'>The client views below are the same render the client's private link "
            "serves (verified identical by the 2026-10-03 audit). §0: nothing is shown to a client "
            "until you say <strong>ready</strong> — live links are flagged.</p>"
            "<div class='card'><table><tr><th>Client</th><th>Matters dated</th><th>Next date</th>"
            "<th>Dependability</th><th>Client links</th><th>Open</th></tr>"
            f"{''.join(rows)}</table></div>")


# ───────────────────────────── 3. BRAIN ─────────────────────────────

def _ask(client_code: str, question: str) -> dict:
    """Run Leo's real reply path for `client_code` with dry_run=True, in a transaction that
    is ALWAYS rolled back. Zero persistent effect (the Improvement Lab pattern)."""
    if _SCRIPTS not in sys.path:
        sys.path.insert(0, _SCRIPTS)
    t0 = time.time()
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        import leo_service as L
        out = L.generate_reply(cur, "ops_console", None, question, client_code, dry_run=True)
    except Exception as e:
        out = {"text": None, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    finally:
        conn.rollback()
        cur.close()
        conn.close()
    out["ms"] = int((time.time() - t0) * 1000)
    return out


def _brain(clients, asked=None) -> str:
    opts = "".join(
        f"<option value='{_esc(c)}'{' selected' if asked and asked['client'] == c else ''}>{_esc(c)}</option>"
        for c in clients)
    q = _esc(asked["q"]) if asked else ""
    sugg = "".join(
        f"<form method='post' style='display:inline'><input type='hidden' name='client' value='{_esc(c)}'>"
        f"<input type='hidden' name='q' value='{_esc(s)}'>"
        f"<button class='badge badge-off' type='submit'>{_esc(s)}</button></form> "
        for c, s in SUGGESTED)
    result = ""
    if asked:
        r = asked["result"]
        if r.get("text"):
            v = r.get("verdict") or ""
            source = {"stack": "answered from the corpus",
                      "stack_closed": "refused — not in the corpus",
                      "pass": "free model, passed the answer gate",
                      "fail": "free model, FAILED the answer gate (rewritten)"}.get(v, v or "n/a")
            how = _esc(r.get("via") or "")
            result = (f"<div class='card'><div class='section-title'>Leo's reply "
                      f"<span class='badge badge-off'>{_esc(source)}</span> "
                      f"<span class='muted'>via {how} · {r['ms']} ms"
                      f"{' · remediated by gate' if r.get('remediated') else ''}</span></div>"
                      f"<div style='white-space:pre-wrap'>{_esc(r['text'])}</div>"
                      f"<p class='muted'>Judge it: does this actually answer the question, correctly? "
                      f"A source label is not a correctness check.</p></div>")
        else:
            result = (f"<div class='card alert-warn'><strong>No reply.</strong> "
                      f"{_esc(r.get('error') or 'unknown')} <span class='muted'>({r['ms']} ms)</span></div>")
    return (
        "<p class='muted'>Runs Leo's real reply path (the same one Telegram/Messenger use) in "
        "<strong>dry-run</strong>; the database transaction is rolled back, so testing leaves no trace "
        "and nothing is sent to anyone. Factual questions must be answered from the corpus "
        "(<em>stack</em>) or honestly refused (<em>stack_closed</em>).</p>"
        "<form method='post' class='card'>"
        f"<select name='client'>{opts}</select> "
        f"<input name='q' value='{q}' placeholder='Ask Leo something a client would ask…' "
        "style='width:60%' required> <button type='submit'>Ask</button></form>"
        f"<div style='margin:8px 0'>{sugg}</div>{result}")


# ───────────────────────────── page ─────────────────────────────

@bp.route("/", methods=["GET", "POST"])
def console():
    conn = _db()
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        stack = _scorecard(cur, conn)
        product = _product(cur, conn)
        client_codes = [r["client_code"] for r in (_safe_fetch(cur, conn, """
            SELECT DISTINCT client_code FROM matters
             WHERE client_code IS NOT NULL AND client_code <> ''
               AND client_code NOT IN ('Archive','PENDING_TRIAGE')
               AND matter_code NOT LIKE 'AUTO-%%'
               AND COALESCE(status,'') NOT IN ('closed','archived') ORDER BY 1""", default=[]) or [])]
    finally:
        cur.close()
        conn.close()

    asked = None
    if request.method == "POST":
        cc = (request.form.get("client") or "").strip()
        q = (request.form.get("q") or "").strip()[:500]
        if cc in client_codes and q:
            asked = {"client": cc, "q": q, "result": _ask(cc, q)}

    body = (
        "<h1>Console</h1><p class='muted'>The one place to test LandTek — the product as clients see "
        "it, Leo's answers, and whether the machine is honest. Every number is live (MASTER_PLAN §0).</p>"
        "<div class='section-title'>1 · Stack — the §0 scorecard</div>" + stack +
        "<div class='section-title'>Machine health</div>" + _health() +
        "<div class='section-title'>2 · Product — each client as they see it</div>" + product +
        "<div class='section-title'>3 · Brain — ask Leo</div>" + _brain(client_codes, asked)
    )
    return _layout("Console", body, active="console")
