"""Slash-command Flask endpoints for Jonathan — deploy_093.

GET /api/digest         — render daily digest (returns + sends to Jonathan)
GET /api/status         — system + case + open-questions one-page summary
GET /api/report?case=X  — per-case intelligence brief from clients table

All three send the result to Jonathan's Telegram and ALSO return JSON,
so they can be called from the workflow slash router OR directly via curl.
"""
import os
import sys
import json
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify
import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek")
from build_digest import render_digest_messages, tg_send

PG_DSN = os.getenv("LEO_TOOLS_PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN_TG_ID = "6513067717"

bp = Blueprint("slash_endpoints", __name__)


def _db():
    return psycopg2.connect(PG_DSN)


@bp.route("/api/digest", methods=["POST", "GET"])
def api_digest():
    """Render + send the daily digest. POST { 'send': false } to render only."""
    payload = request.get_json(silent=True) or {}
    send = payload.get("send", True) if request.method == "POST" else (request.args.get("send", "1") != "0")
    msgs = render_digest_messages()
    if send:
        for m in msgs:
            tg_send(m)
    return jsonify({"messages_count": len(msgs), "sent": send, "messages": msgs})


@bp.route("/api/status", methods=["POST", "GET"])
def api_status():
    """Compact system + case + open-questions summary."""
    payload = request.get_json(silent=True) or {}
    send = payload.get("send", True) if request.method == "POST" else (request.args.get("send", "1") != "0")
    conn = _db(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
          (SELECT count(*) FROM documents) AS total_docs,
          (SELECT count(*) FROM documents WHERE timestamp > now() - interval '24 hours') AS docs_24h,
          (SELECT count(*) FROM conversations WHERE timestamp > now() - interval '24 hours') AS conv_24h,
          (SELECT count(*) FROM pending_inquiries WHERE status='open' AND expires_at > now()) AS open_inquiries,
          (SELECT count(*) FROM action_items WHERE status='Open') AS open_actions,
          (SELECT count(*) FROM unauth_attempts WHERE attempted_at > now() - interval '24 hours') AS unauth_24h;
    """)
    s = cur.fetchone()
    cur.execute("""
        SELECT case_file, name, priority_level,
               (SELECT count(*) FROM documents d WHERE d.case_file=c.case_file) AS doc_count
          FROM clients c WHERE case_file IS NOT NULL AND case_file != '' ORDER BY name;
    """)
    cases = cur.fetchall()
    cur.close(); conn.close()

    try:
        with open("/var/lib/landtek/watchdog_state.json") as f:
            wd = json.load(f)
        wd_state = wd.get("state", "?")
    except Exception:
        wd_state = "?"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"📊 <b>LandTek Status — {now}</b>",
        "",
        f"⚙️ Leo watchdog: <b>{wd_state.upper()}</b>",
        "",
        f"📥 Last 24h: {s['docs_24h']} new docs · {s['conv_24h']} client conversations",
        f"❓ Open inquiries: {s['open_inquiries']}",
        f"📋 Open action items: {s['open_actions']}",
        f"🚨 Unauthorized attempts (24h): {s['unauth_24h']}",
        "",
        f"🗂 <b>Cases</b>",
    ]
    for c in cases:
        prio = (c["priority_level"] or "")[:3].upper()
        lines.append(f"  • {c['case_file']} [{prio}] — {c['doc_count']} docs")

    text = "\n".join(lines)
    if send:
        tg_send(text)
    return jsonify({"text": text, "sent": send})


@bp.route("/api/pdf_report", methods=["POST", "GET"])
def api_pdf_report():
    """Generate + DM a PDF brief for a case."""
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        case = payload.get("case", "MWK-001").strip()
    else:
        case = request.args.get("case", "MWK-001").strip()
    import subprocess
    try:
        r = subprocess.run(
            ["python3", "/root/landtek/pdf_reports.py", "--case", case],
            capture_output=True, text=True, timeout=120,
        )
        ok = r.returncode == 0
        return jsonify({
            "case": case, "ok": ok,
            "stdout": r.stdout[-500:], "stderr": r.stderr[-200:] if r.stderr else "",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/report", methods=["POST", "GET"])
def api_report():
    """Per-case intelligence brief from clients table (populated by educate_leo)."""
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        case = payload.get("case", "").strip()
        send = payload.get("send", True)
    else:
        case = request.args.get("case", "").strip()
        send = request.args.get("send", "1") != "0"
    if not case:
        return jsonify({"error": "case param required"}), 400

    conn = _db(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT name, case_file, priority_level, project_status,
               current_goals, next_milestone, key_risks,
               open_strategic_gaps, client_intelligence_summary,
               intelligence_updated_at,
               (SELECT count(*) FROM documents d WHERE d.case_file=c.case_file) AS doc_count
          FROM clients c WHERE case_file = %s LIMIT 1;
    """, (case,))
    r = cur.fetchone()
    cur.close(); conn.close()

    if not r:
        return jsonify({"error": f"no client found for case_file={case}"}), 404

    if not r["client_intelligence_summary"]:
        text = (
            f"📊 <b>Report: {r['name']} ({case})</b>\n\n"
            f"⚠️ No intelligence summary yet — educate_leo.py hasn't run for this case "
            f"(or didn't commit). Run it: <code>python3 /root/landtek/educate_leo.py "
            f"--case {case} --commit-clients-update</code>"
        )
    else:
        upd = r["intelligence_updated_at"]
        text = "\n\n".join([
            f"📊 <b>Report: {r['name']} ({case})</b>",
            f"<i>Updated {upd.strftime('%Y-%m-%d %H:%M UTC') if upd else '(never)'} · {r['doc_count']} docs · priority {r['priority_level'] or '?'}</i>",
            f"<b>Status</b>: {r['project_status'] or '(none)'}",
            f"<b>Next milestone</b>: {r['next_milestone'] or '(none)'}",
            f"<b>Summary</b>:\n{r['client_intelligence_summary'][:1500]}",
            f"<b>Goals</b>:\n{(r['current_goals'] or '(none)')[:1000]}",
            f"<b>Risks</b>:\n{(r['key_risks'] or '(none)')[:1000]}",
            f"<b>Gaps</b>:\n{(r['open_strategic_gaps'] or '(none)')[:1000]}",
        ])

    # Telegram message size cap — chunk if needed
    msgs = []
    while text:
        msgs.append(text[:4000])
        text = text[4000:]
    if send:
        for m in msgs:
            tg_send(m)
    return jsonify({"text": "\n".join(msgs), "messages_count": len(msgs), "sent": send})
