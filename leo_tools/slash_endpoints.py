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
from psycopg2.extras import RealDictCursor
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


def _send_tg(text):
    from build_digest import tg_send
    tg_send(text)


@bp.route("/api/goals", methods=["POST", "GET"])
def api_goals():
    case = (request.args.get("case") or (request.get_json(silent=True) or {}).get("case", "MWK-001")).strip()
    send = request.args.get("send", "1") != "0"
    conn = _db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, priority, status, goal_category, progress_pct, target_date,
               LEFT(goal_text, 250) AS goal_text
          FROM client_goals
         WHERE case_file = %s
         ORDER BY CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
                  status, id
    """, (case,))
    rows = cur.fetchall(); cur.close(); conn.close()

    lines = [f"🎯 <b>{case} goals ({len(rows)})</b>", ""]
    for r in rows:
        prio = (r["priority"] or "?")[:4].upper()
        status_emoji = {"active": "▶", "at_risk": "⚠", "blocked": "🔒",
                        "achieved": "✓", "abandoned": "✗"}.get(r["status"], "?")
        lines.append(f"  {status_emoji} #{r['id']} [{prio}] ({r['goal_category']}, {r['progress_pct']}%): {r['goal_text']}")

    text = "\n".join(lines)
    if send: _send_tg(text)
    return jsonify({"case": case, "count": len(rows), "text": text})


@bp.route("/api/duties", methods=["POST", "GET"])
def api_duties():
    case = (request.args.get("case") or (request.get_json(silent=True) or {}).get("case", "MWK-001")).strip()
    send = request.args.get("send", "1") != "0"
    conn = _db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT d.id, d.duty_type, d.status, d.assigned_to, d.deadline,
               LEFT(d.duty_text, 250) AS duty_text, g.priority AS goal_priority
          FROM landtek_duties d
          LEFT JOIN client_goals g ON g.id = d.goal_id
         WHERE d.case_file = %s
         ORDER BY CASE d.status WHEN 'pending' THEN 1 WHEN 'in_progress' THEN 2
                                WHEN 'blocked' THEN 3 WHEN 'fulfilled' THEN 4 ELSE 5 END,
                  d.deadline ASC NULLS LAST, d.id
    """, (case,))
    rows = cur.fetchall(); cur.close(); conn.close()
    lines = [f"⚖️ <b>{case} duties ({len(rows)})</b>", ""]
    for r in rows:
        status_emoji = {"pending": "○", "in_progress": "▶", "blocked": "🔒",
                        "fulfilled": "✓", "dropped": "✗"}.get(r["status"], "?")
        deadline = r["deadline"].strftime("%Y-%m-%d") if r["deadline"] else "—"
        lines.append(f"  {status_emoji} #{r['id']} [{r['duty_type']}, due {deadline}] -> {r['assigned_to']}: {r['duty_text']}")
    text = "\n".join(lines)
    if send: _send_tg(text)
    return jsonify({"case": case, "count": len(rows), "text": text})


@bp.route("/api/bottlenecks", methods=["POST", "GET"])
def api_bottlenecks():
    case = (request.args.get("case") or (request.get_json(silent=True) or {}).get("case", "MWK-001")).strip()
    send = request.args.get("send", "1") != "0"
    conn = _db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, blocker_type, severity, owner, status, created_at,
               LEFT(description, 250) AS description
          FROM bottlenecks
         WHERE case_file = %s AND status IN ('open', 'attempting')
         ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                                WHEN 'medium' THEN 3 ELSE 4 END,
                  created_at ASC
         LIMIT 25
    """, (case,))
    rows = cur.fetchall(); cur.close(); conn.close()
    lines = [f"🧱 <b>{case} bottlenecks ({len(rows)} open)</b>", ""]
    sev_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}
    for r in rows:
        em = sev_emoji.get(r["severity"], "?")
        age_days = (datetime.now(timezone.utc) - r["created_at"]).days if r.get("created_at") else 0
        lines.append(f"  {em} #{r['id']} [{r['blocker_type']}, owner={r['owner']}, age={age_days}d]: {r['description']}")
    text = "\n".join(lines)
    if send: _send_tg(text)
    return jsonify({"case": case, "count": len(rows), "text": text})


@bp.route("/api/verify", methods=["POST", "GET"])
def api_verify():
    """Run truth_negotiator on a claim. ?claim=...&case=MWK-001"""
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        claim = (payload.get("claim") or "").strip()
        case = (payload.get("case") or "").strip() or None
        send = payload.get("send", True)
    else:
        claim = (request.args.get("claim") or "").strip()
        case = (request.args.get("case") or "").strip() or None
        send = request.args.get("send", "1") != "0"
    if not claim:
        return jsonify({"error": "claim param required"}), 400
    sys.path.insert(0, "/root/landtek")
    from truth_negotiator import negotiate
    r = negotiate(claim, case_file=case, asked_by="slash:verify")
    verdict_emoji = {
        "verified":        "✅",
        "uncertain":       "⚠️",
        "refuted":         "❌",
        "unsourced":       "🚫",
        "uncitable_draft": "📝",
    }
    em = verdict_emoji.get(r["verdict"], "?")
    lines = [
        f"{em} <b>Truth Negotiation #{r['id']}</b>",
        f"<i>{claim[:300]}</i>",
        "",
        f"Verdict: <b>{r['verdict'].upper()}</b>",
    ]
    if r["citation_tag"]:
        lines.append(f"Citation: <code>{r['citation_tag']}</code>")
    lines.append(f"Evidence: {r['evidence_count']} docs · "
                 f"fact-backers: {len(r['fact_backers'])} · "
                 f"comm-backers: {len(r['comm_backers'])} · "
                 f"drafts: {len(r['drafts'])}")
    if r["challenger_disagrees"]:
        lines.append(f"⚠️ Challenger: {r['challenger_reason']}")
    lines.append(f"<i>{r['duration_ms']}ms</i>")
    text = "\n".join(lines)
    if send: _send_tg(text)
    return jsonify({"text": text, **r})


@bp.route("/api/stage", methods=["POST", "GET"])
def api_stage():
    """Return current procedural stage for a matter or case_file."""
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        scope = (payload.get("scope") or "").strip() or "MWK-CV26360"
        send = payload.get("send", True)
    else:
        scope = (request.args.get("scope") or "").strip() or "MWK-CV26360"
        send = request.args.get("send", "1") != "0"
    conn = _db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT matter_code, case_file, title, current_stage, next_event,
               next_deadline, next_event_owner, stage_updated_at, stage_notes,
               docket_number, court_or_agency
          FROM matters
         WHERE matter_code = %s OR case_file = %s
         ORDER BY (matter_code = %s) DESC
    """, (scope, scope, scope))
    matters = cur.fetchall()
    if not matters:
        cur.close(); conn.close()
        return jsonify({"error": f"no matter found for {scope}"}), 404
    lines = []
    for m in matters:
        lines.append(f"⚖️ <b>{m['matter_code']}</b> — {m['title']}")
        if m["docket_number"]:
            lines.append(f"<i>{m['court_or_agency'] or '—'} · {m['docket_number']}</i>")
        if m["current_stage"]:
            lines.append(f"Stage: <b>{m['current_stage']}</b>")
            if m["next_event"]:
                lines.append(f"Next: {m['next_event']}")
            if m["next_deadline"]:
                days = (m["next_deadline"] - datetime.now(timezone.utc).date()).days
                lines.append(f"Deadline: {m['next_deadline']} ({'T-' + str(days) + 'd' if days >= 0 else 'OVERDUE by ' + str(-days) + 'd'})")
            if m["stage_notes"]:
                lines.append(f"<i>Detected via: {m['stage_notes'][:200]}</i>")
        else:
            lines.append("<i>No stage detected yet — run classify_case_stage.py</i>")
        # Latest 3 transitions
        cur.execute("""
            SELECT from_stage, to_stage, transitioned_at, transition_doc_id
              FROM case_stage_transitions
             WHERE matter_code = %s
             ORDER BY transitioned_at DESC LIMIT 3
        """, (m["matter_code"],))
        trans = cur.fetchall()
        if trans:
            lines.append("Recent transitions:")
            for t in trans:
                lines.append(f"  • {t['from_stage'] or '(initial)'} → {t['to_stage']}  (doc #{t['transition_doc_id']})")
        lines.append("")
    text = "\n".join(lines)
    cur.close(); conn.close()
    if send: _send_tg(text)
    return jsonify({"text": text, "matters_count": len(matters)})


@bp.route("/api/finance", methods=["POST", "GET"])
def api_finance():
    """Quick financial snapshot: firm + per-case overhead, recent costs, asset value sketch."""
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        send = payload.get("send", True)
    else:
        send = request.args.get("send", "1") != "0"
    conn = _db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT owner, sum(monthly_amount) AS total
          FROM monthly_overhead
         WHERE is_active GROUP BY owner ORDER BY owner
    """)
    overhead = cur.fetchall()
    cur.execute("""
        SELECT category, sum(amount_php) AS php_30d, sum(amount_usd) AS usd_30d, count(*) AS n
          FROM leo_operational_costs
         WHERE cost_date > now() - interval '30 days'
         GROUP BY category ORDER BY php_30d DESC NULLS LAST
    """)
    costs = cur.fetchall()
    cur.execute("""
        SELECT count(*) AS assets, count(*) FILTER (WHERE market_price_value IS NULL) AS no_mpv
          FROM asset_current_valuation
    """)
    asset_summary = cur.fetchone()
    cur.execute("SELECT count(*) FROM accounts")
    n_accts = cur.fetchone()["count"]
    cur.execute("SELECT count(*) FROM firm_goals WHERE status='active'")
    n_goals = cur.fetchone()["count"]
    cur.close(); conn.close()

    lines = ["💰 <b>Financial Snapshot</b>", ""]
    total_landtek_overhead = sum(float(o["total"]) for o in overhead if o["owner"] == "landtek")
    total_client_overhead  = sum(float(o["total"]) for o in overhead if o["owner"] != "landtek")
    lines.append(f"<b>Monthly overhead</b>")
    lines.append(f"  Landtek firm: ₱{total_landtek_overhead:,.0f}/mo")
    lines.append(f"  Clients:      ₱{total_client_overhead:,.0f}/mo")
    lines.append("")
    if costs:
        lines.append("<b>Leo operational costs (last 30d, seed)</b>")
        total_usd = sum(float(c["usd_30d"] or 0) for c in costs)
        total_php = sum(float(c["php_30d"] or 0) for c in costs)
        for c in costs:
            lines.append(f"  {c['category']:20s} ${float(c['usd_30d'] or 0):>6.2f}  ({c['n']} entries)")
        lines.append(f"  <b>Total: ${total_usd:.2f}  (≈₱{total_php:,.0f})</b>")
        lines.append("")
    lines.append(f"<b>Assets tracked:</b> {asset_summary['assets']}  ({asset_summary['no_mpv']} without MPV)")
    lines.append(f"<b>Chart of accounts:</b> {n_accts} accounts")
    lines.append(f"<b>Firm goals active:</b> {n_goals}")
    lines.append("")
    lines.append("<i>Data is seed/estimate — backfill from tax-doc corpus pending.</i>")

    text = "\n".join(lines)
    if send: _send_tg(text)
    return jsonify({"text": text})


@bp.route("/api/blueprint", methods=["POST", "GET"])
def api_blueprint():
    """Generate + send the complete system blueprint PDF."""
    import subprocess
    r = subprocess.run(["python3", "/root/landtek/build_system_blueprint.py", "--send-tg"],
                       capture_output=True, text=True, timeout=120)
    return jsonify({"ok": r.returncode == 0,
                    "stdout": r.stdout[-300:], "stderr": r.stderr[-200:]})


@bp.route("/api/case_status", methods=["POST", "GET"])
def api_case_status():
    """Per-case status: stage + party-filing inventory + pending responses."""
    case = (request.args.get("case") or "MWK-001").strip()
    send = request.args.get("send", "1") != "0"
    conn = _db(); cur = conn.cursor(cursor_factory=RealDictCursor)

    # Matter + stage
    cur.execute("""
        SELECT matter_code, title, current_stage, next_event, next_deadline, docket_number
          FROM matters WHERE case_file = %s ORDER BY status, matter_code
    """, (case,))
    matters = cur.fetchall()

    # Party-filing breakdown
    cur.execute("""
        SELECT filing_party, count(*) AS n,
               count(*) FILTER (WHERE filing_role='pleading') AS pleadings,
               count(*) FILTER (WHERE filing_role='affidavit') AS affidavits,
               count(*) FILTER (WHERE filing_role='order') AS orders,
               count(*) FILTER (WHERE filing_role='correspondence') AS letters,
               count(*) FILTER (WHERE filing_role='notice') AS notices
          FROM case_party_filings WHERE case_file = %s
         GROUP BY filing_party ORDER BY n DESC
    """, (case,))
    parties = cur.fetchall()

    # Latest 5 filings each side
    cur.execute("""
        SELECT cpf.doc_id, cpf.filing_party, cpf.filing_role, cpf.confidence,
               d.canonical_filename, d.doc_date
          FROM case_party_filings cpf JOIN documents d ON d.id = cpf.doc_id
         WHERE cpf.case_file = %s AND cpf.filing_party IN ('plaintiff','respondent')
         ORDER BY d.doc_date DESC NULLS LAST, cpf.created_at DESC LIMIT 12
    """, (case,))
    latest = cur.fetchall()

    cur.close(); conn.close()

    lines = [f"⚖️ <b>Case Status — {case}</b>", ""]
    for m in matters:
        lines.append(f"<b>{m['matter_code']}</b> — {m['title']}")
        if m["current_stage"]:
            lines.append(f"  stage: <b>{m['current_stage']}</b> · next: {m['next_event'] or '—'} · due {m['next_deadline'] or '—'}")
        else:
            lines.append("  <i>stage not tracked</i>")
        lines.append("")

    lines.append("<b>Filings by party</b>")
    for p in parties:
        emoji = {"plaintiff":"🟢", "respondent":"🔴", "court":"⚖️", "agency":"🏛", "third_party":"❓", "ambiguous":"❓"}.get(p["filing_party"], "•")
        lines.append(f"  {emoji} {p['filing_party']:12s} · {p['n']:>3} total (pld={p['pleadings']} aff={p['affidavits']} ord={p['orders']} cor={p['letters']} not={p['notices']})")
    lines.append("")

    if latest:
        lines.append("<b>Recent plaintiff vs respondent filings</b>")
        for r in latest:
            tag = "🟢" if r["filing_party"] == "plaintiff" else "🔴"
            dd = r["doc_date"]
            dt = dd.isoformat() if hasattr(dd, "isoformat") else (str(dd) if dd else "—")
            lines.append(f"  {tag} {dt}  <code>{(r['canonical_filename'] or 'doc#' + str(r['doc_id']))[:65]}</code>")
    text = "\n".join(lines)
    if send: _send_tg(text)
    return jsonify({"text": text, "case": case})


@bp.route("/api/arta", methods=["POST", "GET"])
def api_arta():
    send = request.args.get("send", "1") != "0"
    conn = _db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT ctn_no, status, filed_date, last_activity,
               email_count, attachment_count, matter_code, next_action, next_deadline
          FROM arta_cases ORDER BY filed_date ASC NULLS LAST
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()

    lines = [f"⚖️ <b>ARTA Cases ({len(rows)})</b>", ""]
    active = sum(1 for r in rows if r["status"] == "active")
    resolved = sum(1 for r in rows if r["status"] in ("resolved", "dismissed", "withdrawn"))
    lines.append(f"  active: <b>{active}</b> · resolved: <b>{resolved}</b>")
    lines.append("")
    for r in rows:
        status_emoji = {"active": "🟢", "resolved": "✓", "dismissed": "✗", "withdrawn": "⏸"}.get(r["status"], "?")
        lines.append(f"{status_emoji} <code>{r['ctn_no']}</code>")
        if r["filed_date"]:
            lines.append(f"   filed {r['filed_date']} · last activity {r['last_activity']}")
        lines.append(f"   {r['email_count']} emails ({r['attachment_count']} w/ attach)")
        if r["next_deadline"]:
            lines.append(f"   ⏰ next: {r['next_action']} due {r['next_deadline']}")
        lines.append("")
    text = "\n".join(lines)
    if send:
        _send_tg(text)
    return jsonify({"text": text, "count": len(rows), "active": active, "resolved": resolved})


@bp.route("/api/email_pull", methods=["POST", "GET"])
def api_email_pull():
    """Trigger gmail_watcher with optional query."""
    query = (request.args.get("query") or "").strip() or None
    max_n = int(request.args.get("max", "50"))
    import subprocess
    cmd = ["python3", "/root/landtek/gmail_watcher.py", "--max", str(max_n), "--send-tg"]
    if query:
        cmd += ["--query", query]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    return jsonify({"ok": r.returncode == 0, "query": query,
                    "stdout": r.stdout[-500:], "stderr": r.stderr[-300:]})


@bp.route("/api/dedupe", methods=["POST", "GET"])
def api_dedupe():
    import subprocess
    r = subprocess.run(["python3", "/root/landtek/dedupe_audit.py", "--reset", "--send-tg"],
                       capture_output=True, text=True, timeout=120)
    return jsonify({"ok": r.returncode == 0,
                    "stdout": r.stdout[-400:], "stderr": r.stderr[-200:]})


@bp.route("/api/inventory", methods=["POST", "GET"])
def api_inventory():
    case = (request.args.get("case") or "").strip() or None
    import subprocess
    cmd = ["python3", "/root/landtek/pdf_file_directory.py", "--send-tg"]
    if case:
        cmd += ["--case", case, "--out", f"/root/landtek/reports/inventory_{case}.pdf"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return jsonify({"ok": r.returncode == 0, "case": case,
                    "stdout": r.stdout[-300:]})


@bp.route("/api/tax_decs", methods=["POST", "GET"])
def api_tax_decs():
    case = (request.args.get("case") or "MWK-001").strip()
    import subprocess
    r = subprocess.run(["python3", "/root/landtek/roll_up_active_tax_decs.py", "--case", case, "--send-tg"],
                       capture_output=True, text=True, timeout=60)
    return jsonify({"ok": r.returncode == 0, "case": case,
                    "stdout": r.stdout[-400:]})


@bp.route("/api/files", methods=["POST", "GET"])
def api_files():
    case = (request.args.get("case") or "").strip() or None
    import subprocess
    cmd = ["python3", "/root/landtek/pdf_file_directory.py", "--send-tg"]
    if case:
        cmd += ["--case", case, "--out", f"/root/landtek/reports/file_directory_{case}.pdf"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return jsonify({"ok": r.returncode == 0, "case": case,
                    "stdout": r.stdout[-300:], "stderr": r.stderr[-200:]})


@bp.route("/api/cashflow", methods=["POST", "GET"])
def api_cashflow():
    case = (request.args.get("case") or "MWK-001").strip()
    import subprocess
    r = subprocess.run(["python3", "/root/landtek/pdf_financial_pack.py",
                        "--type", "cashflow", "--case", case, "--send-tg"],
                       capture_output=True, text=True, timeout=90)
    return jsonify({"ok": r.returncode == 0, "case": case,
                    "stdout": r.stdout[-300:], "stderr": r.stderr[-200:]})


@bp.route("/api/pnl", methods=["POST", "GET"])
def api_pnl():
    import subprocess
    r = subprocess.run(["python3", "/root/landtek/pdf_financial_pack.py",
                        "--type", "pnl", "--send-tg"],
                       capture_output=True, text=True, timeout=90)
    return jsonify({"ok": r.returncode == 0,
                    "stdout": r.stdout[-300:], "stderr": r.stderr[-200:]})


@bp.route("/api/valuation", methods=["POST", "GET"])
def api_valuation():
    asset = (request.args.get("asset") or "").strip()
    if not asset:
        return jsonify({"error": "asset param required"}), 400
    import subprocess
    r = subprocess.run(["python3", "/root/landtek/pdf_financial_pack.py",
                        "--type", "valuation", "--asset", asset, "--send-tg"],
                       capture_output=True, text=True, timeout=90)
    return jsonify({"ok": r.returncode == 0, "asset": asset,
                    "stdout": r.stdout[-300:], "stderr": r.stderr[-200:]})


@bp.route("/api/pack", methods=["POST", "GET"])
def api_pack():
    case = (request.args.get("case") or "MWK-001").strip()
    import subprocess
    r = subprocess.run(["python3", "/root/landtek/pdf_financial_pack.py",
                        "--type", "pack", "--case", case, "--send-tg"],
                       capture_output=True, text=True, timeout=180)
    return jsonify({"ok": r.returncode == 0, "case": case,
                    "stdout": r.stdout[-300:], "stderr": r.stderr[-200:]})


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
