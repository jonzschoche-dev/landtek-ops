#!/usr/bin/env python3
"""refresh_realtime_flow.py — preparation-aware flow context (deploy_325).

Every 5 minutes, regenerate REALTIME_FLOW_TEXT covering:
  - UPCOMING EVENTS (next 30 days) with readiness %
  - OPEN PREP REQUIREMENTS (blocked or open) grouped by event
  - PRIORITY SIGNALS (last 7 days) — what shifted recently
  - PENDING DECISIONS (proposals awaiting Jonathan)
  - VELOCITY (last 24h bonafide pass rate trend, evidence links added)
  - SYSTEM STATE (sim probes active, leaks, library size)

Leo uses this to answer:
  "What do I need for the Barandon meeting?"
  "What's my prep status for the pretrial?"
  "What shifted in the last day?"
  "What needs me right now?"
"""
from __future__ import annotations
import json, os, re, subprocess, sys, time
from datetime import datetime, timezone
import psycopg2, psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"


def fetch_flow(cur) -> dict:
    f = {"refreshed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

    # Upcoming events with readiness
    cur.execute("""SELECT id, short_label, scheduled_for, event_kind,
                          priority, readiness_pct, req_total, req_done, req_open, req_blocked,
                          time_until
                     FROM v_upcoming_events_30d ORDER BY scheduled_for LIMIT 12""")
    f["events"] = cur.fetchall()

    # Open prep requirements (top 15 by priority of event + due_date)
    cur.execute("""
        SELECT e.id AS event_id, e.short_label AS event_label, e.scheduled_for,
               pr.id AS req_id, pr.requirement_kind, pr.description,
               pr.required_doc_lts, pr.due_date, pr.status, pr.blocker
          FROM prep_requirements pr
          JOIN case_events e ON e.id = pr.event_id
         WHERE pr.status IN ('open','blocked')
           AND e.status IN ('upcoming','in_progress')
           AND e.scheduled_for < now() + interval '30 days'
         ORDER BY e.scheduled_for, pr.status DESC, pr.due_date NULLS LAST
         LIMIT 15
    """)
    f["open_reqs"] = cur.fetchall()

    # Priority signals (last 7d)
    cur.execute("""SELECT occurred_at, signal_kind, short_text, detail,
                          affects_event_ids, affects_claim_ids
                     FROM v_active_priority_signals_7d LIMIT 10""")
    f["signals"] = cur.fetchall()

    # Obligations at risk (deploy_326)
    try:
        cur.execute("""SELECT id, client_code, short_label, due_by, status, risk_window,
                              priority, obligation_kind
                         FROM v_obligations_at_risk LIMIT 10""")
        f["obligations_at_risk"] = cur.fetchall()
    except Exception:
        f["obligations_at_risk"] = []

    # Open obligations grouped by client
    try:
        cur.execute("""SELECT client_code, client_name, total_open, blocked, imminent, overdue,
                              obligations
                         FROM v_open_obligations_by_client""")
        f["obligations_by_client"] = cur.fetchall()
    except Exception:
        f["obligations_by_client"] = []

    # Current project phase per case
    try:
        cur.execute("""SELECT case_file, phase_label, description, current_focus,
                              success_criteria, exit_signals
                         FROM v_current_phase_per_case""")
        f["active_phases"] = cur.fetchall()
    except Exception:
        f["active_phases"] = []

    # Open client needs
    try:
        cur.execute("""SELECT client_code, client_name, need_kind, short_label,
                              priority, description
                         FROM v_open_client_needs""")
        f["client_needs"] = cur.fetchall()
    except Exception:
        f["client_needs"] = []

    # Pending decisions
    cur.execute("SELECT COUNT(*) FROM leo_improvement_proposals WHERE status='pending'")
    f["leo_proposals_pending"] = cur.fetchone()["count"]
    cur.execute("SELECT COUNT(*) FROM evidence_trail_proposals WHERE status='pending'")
    f["evidence_proposals_pending"] = cur.fetchone()["count"]
    cur.execute("SELECT COUNT(*) FROM doc_role_proposals WHERE status='pending' AND confidence >= 0.75")
    f["doc_role_high"] = cur.fetchone()["count"]

    # Activity
    cur.execute("SELECT COUNT(*) FROM leo_interactions WHERE timestamp > now() - interval '24 hours' AND sender_id NOT LIKE '999000%'")
    f["real_int_24h"] = cur.fetchone()["count"]
    cur.execute("SELECT COUNT(*) FROM documents WHERE created_at > now() - interval '7 days'")
    f["docs_added_7d"] = cur.fetchone()["count"]
    try:
        cur.execute("SELECT COUNT(*) FROM gmail_messages WHERE received_at > now() - interval '24 hours'")
        f["emails_24h"] = cur.fetchone()["count"]
    except Exception:
        f["emails_24h"] = 0

    # Velocity
    cur.execute("""
        SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE passed) AS passes
          FROM leo_qa_sim_payloads s JOIN leo_qa_probes p ON p.id=s.probe_id
         WHERE p.intent IN ('engage_helpfully','verify_facts','honest_disclosure')
           AND s.posted_at > now() - interval '24 hours'
    """)
    r = cur.fetchone()
    f["bonafide_total"] = r["total"] or 0
    f["bonafide_pass"] = r["passes"] or 0
    f["bonafide_pct"] = round(100.0 * (r["passes"] or 0) / max(r["total"] or 1, 1), 1)
    cur.execute("SELECT COUNT(*) FROM evidence_trail WHERE added_at > now() - interval '24 hours'")
    f["evidence_added_24h"] = cur.fetchone()["count"]

    # System
    cur.execute("SELECT COUNT(*) FROM leo_qa_probes WHERE active AND rail='sim'")
    f["library"] = cur.fetchone()["count"]
    cur.execute("SELECT COUNT(*) FROM sim_leak_incidents WHERE detected_at > now() - interval '24 hours'")
    f["leaks"] = cur.fetchone()["count"]
    return f


def fmt_time_until(td) -> str:
    if td is None: return "?"
    secs = td.total_seconds() if hasattr(td, "total_seconds") else 0
    days = int(secs // 86400)
    if days > 1: return f"{days}d"
    hours = int(secs // 3600)
    if hours > 0: return f"{hours}h"
    return "<1h"


def render(f: dict) -> str:
    L = ["", f"REAL-TIME FLOW (refreshed {f['refreshed_at']}, every 5 min):", ""]

    # UPCOMING EVENTS
    L.append("UPCOMING EVENTS (next 30 days, by date):")
    if not f["events"]:
        L.append("  (no upcoming events on the calendar)")
    else:
        for e in f["events"]:
            tu = fmt_time_until(e["time_until"])
            ready = "—" if e["req_total"] == 0 else f"{e['readiness_pct']}%"
            L.append(f"  [{e['id']}] {tu:>5s} ({e['scheduled_for'].strftime('%Y-%m-%d %H:%M UTC')})  "
                     f"p{e['priority']}  ready={ready}  ({e['event_kind']}) {e['short_label']}")
    L.append("")

    # OPEN PREP REQUIREMENTS
    if f["open_reqs"]:
        L.append("OPEN PREP REQUIREMENTS (by event, top 15):")
        cur_event = None
        for r in f["open_reqs"]:
            if r["event_id"] != cur_event:
                L.append(f"  EVENT [{r['event_id']}] {r['event_label']} ({r['scheduled_for'].strftime('%Y-%m-%d')}):")
                cur_event = r["event_id"]
            lts = r["required_doc_lts"] or []
            lt_str = f"  docs: {', '.join(lts)}" if lts else ""
            status_glyph = "🚧" if r["status"] == "blocked" else "○"
            L.append(f"    {status_glyph} [{r['req_id']}] [{r['requirement_kind']}] {r['description']}{lt_str}")
            if r["blocker"]:
                L.append(f"        blocked by: {r['blocker']}")
        L.append("")

    # PRIORITY SIGNALS
    if f["signals"]:
        L.append("PRIORITY SIGNALS (last 7 days, recent first):")
        for s in f["signals"][:6]:
            ack = "" if s.get("acknowledged_at") else " [UNACKED]"
            L.append(f"  • {s['occurred_at'].strftime('%m-%d %H:%M')} [{s['signal_kind']}]{ack} {s['short_text']}")
        if len(f["signals"]) > 6:
            L.append(f"  … +{len(f['signals'])-6} more")
        L.append("")

    # CURRENT PROJECT PHASE PER CASE (deploy_326)
    if f.get("active_phases"):
        L.append("CURRENT PROJECT PHASE PER CASE:")
        for p in f["active_phases"]:
            L.append(f"  [{p['case_file']}]  phase: {p['phase_label']}")
            if p['description']:
                L.append(f"    {p['description'][:160]}")
            if p['success_criteria']:
                L.append(f"    success: {p['success_criteria'][:140]}")
        L.append("")

    # LANDTEK OBLIGATIONS — what we owe each client
    if f.get("obligations_by_client"):
        L.append("LANDTEK OBLIGATIONS — what we owe each client:")
        for c in f["obligations_by_client"]:
            risk_flags = []
            if c['overdue']:  risk_flags.append(f"{c['overdue']} OVERDUE")
            if c['imminent']: risk_flags.append(f"{c['imminent']} imminent")
            if c['blocked']:  risk_flags.append(f"{c['blocked']} blocked")
            flags = " · ".join(risk_flags) if risk_flags else "all on track"
            cname = (c['client_name'] or c['client_code'])[:40]
            L.append(f"  {cname}  ({c['total_open']} open  ·  {flags})")
            for ob in (c['obligations'] or [])[:4]:
                due = ob.get('due_by') or "no due date"
                if hasattr(due, 'strftime'): due = due.strftime("%Y-%m-%d")
                L.append(f"    [{ob['id']}] [{ob['kind']}] {ob['label']}  (due {due}, p{ob['priority']}, {ob['status']})")
        L.append("")

    # OBLIGATIONS AT RISK
    if f.get("obligations_at_risk"):
        L.append("⚠️  OBLIGATIONS AT RISK (overdue or due within 14 days):")
        for o in f["obligations_at_risk"][:8]:
            due = o['due_by'].strftime("%Y-%m-%d %H:%M") if o.get('due_by') else "?"
            L.append(f"  [{o['id']}] [{o['risk_window']}] [{o['client_code']}] {o['short_label']}  (due {due})")
        L.append("")

    # OPEN CLIENT NEEDS
    if f.get("client_needs"):
        L.append("OPEN CLIENT NEEDS — what each client expects from us:")
        for n in f["client_needs"][:10]:
            cname = (n['client_name'] or n['client_code'])[:30]
            L.append(f"  [{n['client_code']}] (p{n['priority']}) [{n['need_kind']}] {n['short_label']}")
        L.append("")

    # PENDING DECISIONS
    L.append("PENDING DECISIONS — awaiting Jonathan's review:")
    L.append(f"  - Leo improvement proposals:        {f['leo_proposals_pending']}")
    L.append(f"  - Evidence trail proposals:         {f['evidence_proposals_pending']}")
    L.append(f"  - Doc role proposals (≥0.75 conf):  {f['doc_role_high']}")
    L.append("")

    # ACTIVITY
    L.append("RECENT ACTIVITY (last 24-168h):")
    L.append(f"  - Real-client messages (24h):       {f['real_int_24h']}")
    L.append(f"  - Documents added (7d window):      {f['docs_added_7d']}")
    L.append(f"  - Emails received (24h):            {f['emails_24h']}")
    L.append("")

    # VELOCITY
    L.append("VELOCITY (last 24h):")
    L.append(f"  - Bonafide engagement: {f['bonafide_pass']}/{f['bonafide_total']} ({f['bonafide_pct']}%)")
    L.append(f"  - New evidence links:               {f['evidence_added_24h']}")
    L.append("")

    # SYSTEM
    L.append(f"SYSTEM: {f['library']} sim probes active · leaks 24h={f['leaks']}")
    L.append("")

    L.append("USAGE — when Jonathan asks:")
    L.append("  'what do I need for [EVENT]?' / 'prep status for [EVENT]?'")
    L.append("    → consult OPEN PREP REQUIREMENTS for that event_id;")
    L.append("    → list the open + blocked items with their LT-NNNN doc citations.")
    L.append("  'what does [CLIENT] need?' / 'what do we owe [CLIENT]?'")
    L.append("    → surface LANDTEK OBLIGATIONS for that client_code;")
    L.append("    → list the OPEN CLIENT NEEDS;")
    L.append("    → if any obligations are at risk, lead with those.")
    L.append("  'what phase are we in on [CASE]?' / 'where are we on [matter]?'")
    L.append("    → cite CURRENT PROJECT PHASE for that case_file;")
    L.append("    → state success criteria + current focus.")
    L.append("  'what shifted?' / 'any updates?' / 'what's new?'")
    L.append("    → lead with PRIORITY SIGNALS (last 7d, unacked first);")
    L.append("    → follow with PENDING DECISIONS counts.")
    L.append("  'what's coming up?' / 'what's next?'")
    L.append("    → list UPCOMING EVENTS in date order with readiness %.")
    L.append("  'status?' / 'what's going on?'")
    L.append("    → 3-line summary: top upcoming event, top pending decision count,")
    L.append("    → highest-priority obligation at risk, most recent priority signal.")
    L.append("  'are we keeping our promises?' / 'what's our obligation status?'")
    L.append("    → summarize OBLIGATIONS AT RISK + total open obligations + breached.")
    return "\n".join(L)


def patch_const(code: str, body: str) -> tuple[str, bool]:
    if "const REALTIME_FLOW_TEXT" in code:
        m = re.search(r"(const REALTIME_FLOW_TEXT\s*=\s*`)([^`]*)(`;)", code, re.DOTALL)
        if not m: raise RuntimeError("REALTIME_FLOW_TEXT pattern broken")
        if m.group(2).strip() == body.strip(): return (code, False)
        return (code[: m.start(2)] + body + code[m.end(2):], True)
    evid_end = code.find("`;", code.find("const EVIDENCE_TRAIL_FACTS_TEXT"))
    if evid_end < 0:
        raise RuntimeError("EVIDENCE_TRAIL_FACTS_TEXT not found")
    insertion = evid_end + 2
    new_const = "\n\nconst REALTIME_FLOW_TEXT = `" + body + "`;\n"
    code = code[:insertion] + new_const + code[insertion:]
    ret_anchor = "`;\n\nreturn [{"
    if ret_anchor in code and "${REALTIME_FLOW_TEXT}" not in code:
        code = code.replace(ret_anchor, "\n${REALTIME_FLOW_TEXT}\n" + ret_anchor, 1)
    return (code, True)


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        f = fetch_flow(cur)
        body = render(f)
        cur.execute("SELECT nodes, connections FROM workflow_entity WHERE id=%s FOR UPDATE",
                    (WORKFLOW_ID,))
        row = cur.fetchone()
        nodes, conns = row["nodes"], row["connections"]
        cb = next((n for n in nodes if n.get("name") == "Context Builder"), None)
        if not cb: raise RuntimeError("Context Builder missing")
        code = cb["parameters"]["jsCode"]
        new_code, changed = patch_const(code, body)
        if not changed:
            print(f"[refresh_realtime_flow] no change ({f['refreshed_at']})")
            conn.rollback(); return
        cur.execute(
            "INSERT INTO leo_workflow_snapshots (workflow_id, reason, nodes_json, connections_json, notes) "
            "VALUES (%s,%s,%s::jsonb,%s::jsonb,%s) RETURNING id",
            (WORKFLOW_ID, "refresh_realtime_flow", json.dumps(nodes), json.dumps(conns), "realtime_flow"),
        )
        sid = cur.fetchone()["id"]
        cb["parameters"]["jsCode"] = new_code
        cur.execute('UPDATE workflow_entity SET nodes=%s, "updatedAt"=now() WHERE id=%s',
                    (json.dumps(nodes), WORKFLOW_ID))
        conn.commit()
        subprocess.run(["python3","/root/landtek/scripts/sync_workflow_history.py",WORKFLOW_ID],
                       check=True, capture_output=True, text=True, timeout=30)
        subprocess.run(["docker","restart","n8n-n8n-1"], check=True, capture_output=True, timeout=60)
        deadline = time.time() + 60
        while time.time() < deadline:
            if subprocess.run(["curl","-sf","http://localhost:5678/healthz"],
                              capture_output=True, timeout=5).returncode == 0: break
            time.sleep(2)
        print(f"[refresh_realtime_flow] applied snapshot #{sid}")
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
