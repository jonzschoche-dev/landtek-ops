"""now_board.py — the ONE simple page: the state of everything, and each officer's own page.

Product interview 2026-11-03 (case_work/PRODUCT_INTERVIEW_2026-11/INTERVIEW_LOG.md), Jonathan:
"I should be able to see a very simple dashboard that shows me the state of everything,
kristyle should have her own dashboard."

  /ops/now                 Jonathan: what needs him, office clocks, fronts, Kristyle, the machine.
  /ops/staff/<assignee>    an officer's own page (Jonathan previews it here, behind /ops basic auth).

SQL-only, read-only, no LLM. Every row is a database row; a front with no date or a past date is shown
as such, never filled in. Mounted on leo_tools (port 8765) under the existing /ops nginx basic auth.
"""
from __future__ import annotations

import glob
import html
import os
import shutil
import subprocess
import time
from datetime import date, datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
from flask import Blueprint, abort

PG_DSN = os.getenv("LEO_TOOLS_PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
MANILA = timezone(timedelta(hours=8))
LIVE_CLOCK = ("served_running", "replied_not_performed", "partial", "lapsed", "consequence_staged")

bp = Blueprint("now_board", __name__, url_prefix="/ops")

CSS = """
:root{--bg:#fafaf8;--fg:#1d1d1b;--mut:#6b6b66;--line:#e4e3de;--red:#b42318;--amb:#a15c07;--grn:#1f7a3a;--card:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#eceae4;--mut:#9a988f;--line:#2c2b28;--red:#f0786c;--amb:#e0a650;--grn:#6cc58a;--card:#1c1b19}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 -apple-system,system-ui,sans-serif}
main{max-width:860px;margin:0 auto;padding:16px}h1{font-size:20px;margin:4px 0 2px}.sub{color:var(--mut);font-size:13px;margin-bottom:14px}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:12px 0}
h2{font-size:15px;margin:0 0 8px;display:flex;justify-content:space-between}h2 span{color:var(--mut);font-weight:400}
.row{display:flex;gap:10px;padding:7px 0;border-top:1px solid var(--line)}.row:first-of-type{border-top:0}
.d{min-width:84px;font-variant-numeric:tabular-nums;color:var(--mut);font-size:13px}.t{flex:1}.m{color:var(--mut);font-size:13px}
.red{color:var(--red)}.amb{color:var(--amb)}.grn{color:var(--grn)}.tag{font-size:12px;border:1px solid var(--line);border-radius:6px;padding:0 6px;margin-left:6px;color:var(--mut)}
.big{font-size:26px;font-weight:600}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}.kpi .m{display:block}
.empty{color:var(--mut);font-style:italic}
a.row{color:inherit;text-decoration:none}a.row:hover{background:var(--bg)}a.row .t:after{content:" ›";color:var(--mut)}
pre{white-space:pre-wrap;font:13px/1.5 ui-monospace,Menlo,monospace;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px;overflow-x:auto}
.kv{display:grid;grid-template-columns:140px 1fr;gap:4px 12px;font-size:14px}.kv div:nth-child(odd){color:var(--mut)}
.back{font-size:14px}
"""


def _q(cur, sql, args=()):
    cur.execute(sql, args)
    return cur.fetchall()


def _e(x):
    return html.escape(str(x if x is not None else ""))


def _today():
    return datetime.now(MANILA).date()


def _d(x):
    return x.strftime("%a %d %b") if x else "no date"


def _rel(due):
    """Days from today, colored: past = red, within 7 days = amber."""
    if not due:
        return '<span class="red">no date</span>'
    n = (due - _today()).days
    cls = "red" if n < 0 else ("amb" if n <= 7 else "")
    txt = f"{-n}d overdue" if n < 0 else ("today" if n == 0 else f"in {n}d")
    return f'<span class="{cls}">{_e(_d(due))} · {txt}</span>'


def _page(title, sub, body):
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{_e(title)}</title>'
            f'<style>{CSS}</style></head><body><main><h1>{_e(title)}</h1><div class="sub">{sub}</div>{body}'
            f'</main></body></html>')


def _section(title, count, rows_html, empty):
    inner = rows_html or f'<div class="empty">{_e(empty)}</div>'
    return f'<section><h2>{_e(title)} <span>{count}</span></h2>{inner}</section>'


def _row(left, text, meta="", href=None):
    tag, attr = ("a", f' href="{_e(href)}"') if href else ("div", "")
    return (f'<{tag} class="row"{attr}><div class="d">{left}</div><div class="t">{text}'
            f'{f"<div class=m>{meta}</div>" if meta else ""}</div></{tag}>')


# ── data ───────────────────────────────────────────────────────────────────────────────────────────────

def _needs_jonathan(cur):
    rows = []
    for a in _q(cur, "SELECT id, kind, prompt, state, created_at FROM approval_asks WHERE state IN ('asked','queued') ORDER BY id"):
        rows.append(_row("approve", _e(a["prompt"]), f"{_e(a['state'])} on Messenger", f"/ops/now/ask/{a['id']}"))
    for i in _q(cur, """SELECT i.id, i.status, s.ladder, s.addressee, i.updated_at FROM drip_instrument i
                         LEFT JOIN step_plan s ON s.id=i.step_plan_id
                        WHERE i.status IN ('awaiting_comment','checked','corrected','draft') AND NOT i.is_test
                        ORDER BY i.updated_at"""):
        age = (_today() - i["updated_at"].astimezone(MANILA).date()).days
        rows.append(_row("letter", f"Your comment on letter #{i['id']} to {_e(i['addressee'] or '?')}",
                         f"{_e(i['ladder'])} · waiting {age}d", f"/ops/now/letter/{i['id']}"))
    try:   # officer questions the bot could not answer from the record (staff_question, deploy_1323)
        for sq in _q(cur, """SELECT q.id, q.assignee, q.question, q.outcome, q.created_at, q.task_id
                               FROM staff_question q WHERE q.outcome <> 'answered'
                                AND q.created_at > now() - interval '7 days' ORDER BY q.id DESC LIMIT 10"""):
            relay = sq["outcome"] == "relay"
            rows.append(_row("check" if relay else "question",
                             f"{_e(sq['assignee'].capitalize())} {'asks you to check' if relay else 'asked'}: \u201c{_e(sq['question'])}\u201d",
                             ("relayed to you · " if relay else f"not in the record ({_e(sq['outcome'].replace('_', ' '))}) · ") +
                             f"{_e(sq['created_at'].astimezone(MANILA).strftime('%a %d %b %H:%M'))}",
                             f"/ops/now/stask/{sq['task_id']}" if sq["task_id"] else None))
    except Exception:
        cur.connection.rollback()
    for o in _q(cur, """SELECT id, matter_code, office, state, updated_at FROM office_obligation
                         WHERE state IN ('draft_held','held_counsel_route') ORDER BY updated_at"""):
        rows.append(_row("held", f"{_e(o['office'])}", f"{_e(o['matter_code'])} · {_e(o['state'])}",
                         f"/ops/now/clock/{o['id']}"))
    return rows


def _clocks(cur):
    rows = []
    for o in _q(cur, """SELECT id, matter_code, office, state, served_at, due_at, ladder FROM office_obligation
                         WHERE state = ANY(%s) ORDER BY due_at NULLS LAST""", (list(LIVE_CLOCK),)):
        tag = "" if o["state"] == "served_running" else f'<span class="tag">{_e(o["state"].replace("_", " "))}</span>'
        rows.append(_row(_e(o["matter_code"]), f"{_e(o['office'])}{tag}",
                         f"reply due {_rel(o['due_at'])} · served {_e(_d(o['served_at']))}", f"/ops/now/clock/{o['id']}"))
    return rows


def _fronts(cur):
    rows = []
    for m in _q(cur, """SELECT matter_code, client_code, next_event, next_deadline, next_event_owner FROM matters
                         WHERE status ILIKE 'active' ORDER BY (next_deadline IS NULL), next_deadline"""):
        ev = (m["next_event"] or "").strip()
        nxt = _e(ev if len(ev) <= 140 else ev[:137].rsplit(" ", 1)[0] + "…") if ev else \
            '<span class="red">no next move recorded</span>'
        rows.append(_row(_e(m["client_code"]), f"<b>{_e(m['matter_code'])}</b> · {nxt}",
                         f"next date {_rel(m['next_deadline'])}" + (f" · {_e(m['next_event_owner'])}" if m["next_event_owner"] else ""),
                         f"/ops/matter/{m['matter_code']}"))
    return rows


def _machine(cur):
    out = []
    dumps = glob.glob("/root/backups/landtek_backup_*.sql.gz")
    if dumps:
        newest = max(dumps, key=os.path.getmtime)
        h = (time.time() - os.path.getmtime(newest)) / 3600
        out.append(("Backup", f"{h:.0f}h old", "grn" if h <= 26 else "red"))
    else:
        out.append(("Backup", "none found", "red"))
    rec = "/root/backups/cloud_receipts.log"
    if os.path.exists(rec):
        h = (time.time() - os.path.getmtime(rec)) / 3600
        out.append(("Private Drive copy", f"{h:.0f}h old", "grn" if h <= 30 else "red"))
    du = shutil.disk_usage("/")
    pct = du.used * 100 // du.total
    out.append(("Server disk", f"{pct}% full", "red" if pct >= 90 else ("amb" if pct >= 85 else "grn")))
    try:
        failed = subprocess.run(["systemctl", "--failed", "--no-legend", "--plain"], capture_output=True,
                                text=True, timeout=5).stdout.strip().splitlines()
        out.append(("Failed services", str(len(failed)), "grn" if not failed else "red"))
    except Exception:
        out.append(("Failed services", "unknown", "amb"))
    return out


def _staff_rows(cur, assignee):
    return _q(cur, """SELECT t.*, s.ladder, s.addressee, s.matter_code FROM drip_service_task t
                        JOIN drip_instrument i ON i.id=t.instrument_id LEFT JOIN step_plan s ON s.id=i.step_plan_id
                       WHERE t.assignee=%s ORDER BY (t.state='proof_ingested'), t.due_date NULLS LAST, t.id""", (assignee,))


def _errand_rows(cur, assignee):
    return _q(cur, """SELECT * FROM staff_task WHERE assignee=%s
                       ORDER BY (state IN ('done','cancelled')), due_date NULLS LAST, seq, id""", (assignee,))


# ── pages ──────────────────────────────────────────────────────────────────────────────────────────────

@bp.route("/now")
def now():
    conn = psycopg2.connect(PG_DSN)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        needs = _needs_jonathan(cur)
        clocks = _clocks(cur)
        fronts = _fronts(cur)
        machine = _machine(cur)
        overdue = sum(1 for o in _q(cur, "SELECT due_at FROM office_obligation WHERE state = ANY(%s)", (list(LIVE_CLOCK),))
                      if o["due_at"] and o["due_at"] < _today())
        stale = sum(1 for m in _q(cur, "SELECT next_deadline FROM matters WHERE status ILIKE 'active'")
                    if not m["next_deadline"] or m["next_deadline"] < _today())
        members = _q(cur, "SELECT name, assignee_key, active, voice FROM staff_desk_members ORDER BY name")
        staff_html = ""
        for m in members:
            ts = [t for t in _staff_rows(cur, m["assignee_key"]) if t["state"] != "proof_ingested"] + \
                 [e for e in _errand_rows(cur, m["assignee_key"]) if e["state"] in ("open", "done_awaiting_check")]
            state = "ON" if m["active"] else "OFF (waiting for your go)"
            staff_html += _row(_e(m["name"]), f'{len(ts)} open task(s) · bot {state}', "her page",
                               f'/ops/staff/{m["assignee_key"]}')
    finally:
        conn.close()
    kpis = (f'<div class="kpis">'
            f'<div class="kpi"><span class="big {"red" if needs else "grn"}">{len(needs)}</span><span class="m">need you</span></div>'
            f'<div class="kpi"><span class="big">{len(clocks)}</span><span class="m">office clocks running</span></div>'
            f'<div class="kpi"><span class="big {"red" if overdue else "grn"}">{overdue}</span><span class="m">offices overdue</span></div>'
            f'<div class="kpi"><span class="big {"red" if stale else "grn"}">{stale}/{len(fronts)}</span><span class="m">fronts with no current date</span></div>'
            f'</div>')
    mach = "".join(_row(_e(k), f'<span class="{c}">{_e(v)}</span>', "", "/ops/health") for k, v, c in machine)
    body = (kpis
            + _section("Needs you", len(needs), "".join(needs), "Nothing is waiting on you.")
            + _section("Office clocks (the drip)", len(clocks), "".join(clocks), "No clocks running.")
            + _section("Fronts", len(fronts), "".join(fronts), "No active matters.")
            + _section("Field officers", len(members), staff_html, "No field officers set up.")
            + _section("Machine", "", mach, ""))
    stamp = datetime.now(MANILA).strftime("%a %d %b %Y, %H:%M Manila")
    return _page("LandTek now", f"As of {stamp}. Straight from the database; refresh for the latest.", body)


@bp.route("/staff/<assignee>")
def staff(assignee):
    conn = psycopg2.connect(PG_DSN)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        ms = _q(cur, "SELECT name, active FROM staff_desk_members WHERE assignee_key=%s", (assignee,))
        if not ms:
            abort(404)
        ts = _staff_rows(cur, assignee)
        es = _errand_rows(cur, assignee)
    finally:
        conn.close()
    word = {"open": "To do", "served_awaiting_proof": "Served, send the stamped copy photo",
            "proof_ingested": "Done, clock running", "failed": "Could not serve"}
    todo = [t for t in ts if t["state"] in ("open", "served_awaiting_proof")]
    done = [t for t in ts if t["state"] not in ("open", "served_awaiting_proof")]

    def rows(lst):
        return "".join(_row(f"Task {t['id']}", f"{_e(t['method']).replace('_', ' ').capitalize()}: letter to "
                            f"{_e(t['addressee'] or 'the office')}, {_e(t['address'])}",
                            f"{_e(word.get(t['state'], t['state']))} · due {_rel(t['due_date'])}",
                            f"/ops/now/task/{t['id']}") for t in lst)
    eword = {"open": "To do", "done_awaiting_check": "Done, Jonathan is checking", "done": "Done",
             "cancelled": "Cancelled"}
    etodo = [e for e in es if e["state"] in ("open", "done_awaiting_check")]
    edone = [e for e in es if e["state"] in ("done", "cancelled")]

    def erows(lst):
        return "".join(_row(f"Task {e['id']}", _e(e["title"]),
                            f"{_e(eword.get(e['state'], e['state']))} · due {_rel(e['due_date'])}",
                            f"/ops/now/stask/{e['id']}") for e in lst)
    todo_html = erows(etodo) + rows(todo)
    done_html = erows(edone) + rows(done)
    body = (_section("Your tasks", len(todo) + len(etodo), todo_html,
                     "No open tasks. Leo will message you on Messenger when there's one.")
            + _section("Done", len(done) + len(edone), done_html, "Nothing finished yet."))
    name = ms[0]["name"]
    return _page(f"{name}'s tasks", "Send proof photos to Leo on Messenger. This page updates from the same record.", body)


# ── detail pages (every board row opens one) ───────────────────────────────────────────────────────────

def _kv(pairs):
    return '<div class="kv">' + "".join(f"<div>{_e(k)}</div><div>{v}</div>" for k, v in pairs) + "</div>"


def _detail(title, sub, sections):
    back = '<a class="back" href="/ops/now">‹ LandTek now</a>'
    return _page(title, f"{back} · {sub}", "".join(f"<section><h2>{_e(h)}</h2>{b}</section>" for h, b in sections))


def _one(cur, sql, args):
    rows = _q(cur, sql, args)
    if not rows:
        abort(404)
    return rows[0]


def _events(cur, obligation_id=None, ladder=None):
    rows = _q(cur, """SELECT created_at, kind, detail FROM drip_event
                       WHERE (detail->>'obligation_id')::text = %s OR detail->>'ladder' = %s
                       ORDER BY created_at DESC LIMIT 25""", (str(obligation_id or ""), ladder or ""))
    return "".join(_row(_e(r["created_at"].astimezone(MANILA).strftime("%d %b %H:%M")), _e(r["kind"]),
                        _e(", ".join(f"{k}: {v}" for k, v in (r["detail"] or {}).items())[:300])) for r in rows) \
        or '<div class="empty">No events recorded.</div>'


@bp.route("/now/letter/<int:iid>")
def letter(iid):
    conn = psycopg2.connect(PG_DSN)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        i = _one(cur, """SELECT i.*, s.ladder, s.addressee, s.matter_code, s.the_ask, s.if_answered, s.if_silent
                           FROM drip_instrument i LEFT JOIN step_plan s ON s.id=i.step_plan_id WHERE i.id=%s""", (iid,))
        ev = _events(cur, ladder=i["ladder"])
    finally:
        conn.close()
    facts = _kv([("Status", _e(i["status"])), ("To", _e(i["addressee"] or i["to_address"] or "?")),
                 ("Matter", f'<a href="/ops/matter/{_e(i["matter_code"])}">{_e(i["matter_code"])}</a>'),
                 ("Ladder", _e(i["ladder"])), ("Sends via", _e(i["send_account"] or "?")),
                 ("The ask", _e(i["the_ask"])), ("If answered", _e(i["if_answered"])),
                 ("If silent", _e(i["if_silent"])), ("File", _e(i["file_path"])),
                 ("Updated", _e(i["updated_at"].astimezone(MANILA).strftime("%a %d %b %Y %H:%M")))])
    return _detail(f"Letter #{iid}", _e(i["ladder"]),
                   [("Summary", facts), ("Text", f"<pre>{_e(i['body_md'] or '(no text stored)')}</pre>"),
                    ("History", ev)])


@bp.route("/now/clock/<int:oid>")
def clock(oid):
    conn = psycopg2.connect(PG_DSN)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        o = _one(cur, "SELECT * FROM office_obligation WHERE id=%s", (oid,))
        ev = _events(cur, obligation_id=oid, ladder=o["ladder"])
    finally:
        conn.close()
    proof = (f'<a href="/ops/now/doc/{o["service_proof_doc_id"]}">doc {o["service_proof_doc_id"]}</a> · {_e(o["service_proof"])}'
             if o["service_proof_doc_id"] else '<span class="red">no proof in the corpus</span>')
    facts = _kv([("Office", _e(o["office"])), ("Officer", _e(o["officer"])), ("State", _e(o["state"])),
                 ("Matter", f'<a href="/ops/matter/{_e(o["matter_code"])}">{_e(o["matter_code"])}</a>'),
                 ("Obligation", _e(o["obligation"])), ("Served", _e(_d(o["served_at"]))), ("Proof", proof),
                 ("Reply due", _rel(o["due_at"])), ("Rule", _e(o["clock_rule"])), ("Day math", _e(o["day_math"])),
                 ("If lapsed", _e(o["consequence_ref"])), ("Ladder", _e(o["ladder"])), ("Notes", _e(o["notes"]))])
    return _detail(f"Clock: {o['office']}", _e(o["matter_code"]), [("Summary", facts), ("History", ev)])


@bp.route("/now/ask/<int:aid>")
def ask(aid):
    conn = psycopg2.connect(PG_DSN)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        a = _one(cur, "SELECT * FROM approval_asks WHERE id=%s", (aid,))
        rec = _q(cur, "SELECT * FROM v_autonomy_record WHERE pattern_key=%s", (a["pattern_key"],))
    finally:
        conn.close()
    r = rec[0] if rec else {}
    facts = _kv([("Question", _e(a["prompt"])), ("State", _e(a["state"])), ("Kind", _e(a["kind"])),
                 ("Asked", _e(a["asked_at"] or "not yet")), ("Your answer", _e(a["decision_text"] or "")),
                 ("Track record", f"{r.get('yes', 0)} yes · {r.get('no', 0)} no · clean streak {r.get('clean_streak', 0)}"
                                  f" ({_e(a['pattern_key'])})")])
    return _detail(f"Approval #{aid}", "Answer it on Messenger with yes or no.", [("Summary", facts)])


@bp.route("/now/task/<int:tid>")
def task(tid):
    conn = psycopg2.connect(PG_DSN)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        t = _one(cur, """SELECT t.*, s.ladder, s.addressee, s.matter_code FROM drip_service_task t
                           JOIN drip_instrument i ON i.id=t.instrument_id LEFT JOIN step_plan s ON s.id=i.step_plan_id
                          WHERE t.id=%s""", (tid,))
    finally:
        conn.close()
    proof = f'<a href="/ops/now/doc/{t["proof_doc_id"]}">doc {t["proof_doc_id"]}</a>' if t["proof_doc_id"] else "not yet"
    facts = _kv([("Who", _e(t["assignee"])), ("Do", _e(t["method"])), ("To", _e(t["addressee"])),
                 ("Where", _e(t["address"])), ("Due", _rel(t["due_date"])), ("State", _e(t["state"])),
                 ("Proof", proof), ("Letter", f'<a href="/ops/now/letter/{t["instrument_id"]}">#{t["instrument_id"]}</a>'),
                 ("Ladder", _e(t["ladder"]))])
    return _detail(f"Task {tid}", _e(t["matter_code"]), [("Summary", facts)])


@bp.route("/now/doc/<int:did>")
def doc(did):
    conn = psycopg2.connect(PG_DSN)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        d = _one(cur, """SELECT id, coalesce(document_title, original_filename) t, case_file, matter_code, mime_type,
                                drive_file_id, created_at, left(extracted_text, 4000) txt FROM documents WHERE id=%s""", (did,))
    finally:
        conn.close()
    drive = (f'<a href="https://drive.google.com/file/d/{_e(d["drive_file_id"])}/view">open in Drive</a>'
             if d["drive_file_id"] else "not on Drive yet")
    facts = _kv([("Title", _e(d["t"])), ("Client", _e(d["case_file"])), ("Matter", _e(d["matter_code"])),
                 ("Type", _e(d["mime_type"])), ("Original", drive), ("Added", _e(d["created_at"]))])
    return _detail(f"Document {did}", _e(d["t"]),
                   [("Summary", facts), ("Text", f"<pre>{_e(d['txt'] or '(no text yet: OCR pending)')}</pre>")])


@bp.route("/now/stask/<int:sid>")
def stask(sid):
    conn = psycopg2.connect(PG_DSN)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        e = _one(cur, "SELECT * FROM staff_task WHERE id=%s", (sid,))
    finally:
        conn.close()
    proof = f'<a href="/ops/now/doc/{e["proof_doc_id"]}">doc {e["proof_doc_id"]}</a>' if e["proof_doc_id"] else "not yet"
    facts = _kv([("Who", _e(e["assignee"])), ("What", _e(e["title"])), ("How", _e(e["how"])),
                 ("Send back", _e(e["proof_needed"])), ("Due", _rel(e["due_date"])),
                 ("Date basis", _e(e["due_basis"])), ("State", _e(e["state"])), ("Proof", proof),
                 ("Matter", f'<a href="/ops/matter/{_e(e["matter_code"])}">{_e(e["matter_code"])}</a>'),
                 ("Source", _e(e["source_ref"]))])
    return _detail(f"Task {sid}", _e(e["matter_code"]), [("Summary", facts)])
