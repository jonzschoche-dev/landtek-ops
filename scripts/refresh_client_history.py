#!/usr/bin/env python3
"""refresh_client_history.py — feed Leo per-client chronological narrative.

10-min cron. Compact-by-default for scale:
  - Per active client: counts by kind (last 30d) + last 5 events with dates
  - At thousands-of-clients scale, only clients with activity in last 7d
    appear in the prompt; rest available via tools.

Pure SQL. $0 token cost.

Same sim-strip pattern as deploys 331 + 332 — sim execs skip this const.
"""
from __future__ import annotations
import json, os, re, subprocess, sys, time
from datetime import datetime, timezone
import psycopg2, psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"

# Scale guard: at >N active clients, switch to summary-only mode in the prompt
ACTIVE_CLIENT_DETAIL_THRESHOLD = 5
RECENT_EVENTS_PER_CLIENT = 5


def fetch(cur) -> dict:
    f = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
    cur.execute("""
        SELECT client_code, total_events_lifetime, events_30d, events_7d,
               most_recent_event, kind_30d_breakdown
          FROM v_client_history_summary
         ORDER BY events_7d DESC NULLS LAST, events_30d DESC NULLS LAST
    """)
    f["summaries"] = cur.fetchall()
    # Per-client recent events (only for clients with 7d activity)
    cur.execute("""
        SELECT DISTINCT client_code FROM v_client_history_summary
         WHERE events_7d > 0
         ORDER BY client_code
    """)
    active_codes = [r["client_code"] for r in cur.fetchall()]
    f["recents"] = {}
    for cc in active_codes:
        cur.execute(f"""
            SELECT event_date, event_kind_canonical, source_table, what_short
              FROM v_client_recent_history
             WHERE client_code = %s
             ORDER BY COALESCE(event_datetime, event_date::timestamptz) DESC NULLS LAST
             LIMIT {RECENT_EVENTS_PER_CLIENT}
        """, (cc,))
        f["recents"][cc] = cur.fetchall()
    return f


def render(f: dict) -> str:
    L = ["", f"CLIENT HISTORY — canonical chronological state (refreshed {f['at']}, every 10 min):", ""]
    if not f["summaries"]:
        L.append("  (no client_history records)")
        return "\n".join(L)

    L.append("PER-CLIENT SUMMARY (counts by event kind, last 30d):")
    L.append("  | client          | lifetime | 30d | 7d | latest      | breakdown (30d) |")
    L.append("  |-----------------|----------|-----|-----|-------------|-----------------|")
    for s in f["summaries"]:
        latest = s["most_recent_event"].strftime("%Y-%m-%d") if s["most_recent_event"] else "—"
        breakdown = ""
        if s["kind_30d_breakdown"]:
            breakdown = ", ".join(f"{k}={v}" for k, v in s["kind_30d_breakdown"].items())
        L.append(f"  | {(s['client_code'] or '?'):15s} | {s['total_events_lifetime']:8d} | {s['events_30d']:3d} | {s['events_7d']:3d} | {latest:11s} | {breakdown[:40]} |")
    L.append("")

    # Recent events for active clients (only if list is small enough)
    if len(f["recents"]) <= ACTIVE_CLIENT_DETAIL_THRESHOLD:
        for cc, events in f["recents"].items():
            if not events:
                continue
            L.append(f"RECENT EVENTS — {cc}  (last {len(events)}):")
            for e in events:
                ed = e["event_date"].isoformat() if e["event_date"] else "?"
                L.append(f"  {ed}  [{e['event_kind_canonical'] or e['source_table']}] {e['what_short']}")
            L.append("")
    else:
        L.append(f"  {len(f['recents'])} clients with 7d activity — use get_client_history(client_code) tool for per-client drill-down.")
        L.append("")

    L.append("USAGE — when asked:")
    L.append("  'what's happened on [CLIENT] lately?' → recent events list above (if present)")
    L.append("  'anything from [CLIENT] in the last week?' → events_7d count + recent events")
    L.append("  'show me [CLIENT]'s history' → cite the summary; offer drill-down if needed")
    return "\n".join(L)


def patch_const(code: str, body: str) -> tuple[str, bool]:
    if "const CLIENT_HISTORY_TEXT" in code:
        m = re.search(r"(const CLIENT_HISTORY_TEXT\s*=\s*`)([^`]*)(`;)", code, re.DOTALL)
        if not m: raise RuntimeError("CLIENT_HISTORY_TEXT pattern broken")
        if m.group(2).strip() == body.strip():
            return (code, False)
        return (code[: m.start(2)] + body + code[m.end(2):], True)
    # First insertion — after OBJECTIVES_TEXT
    anchor = "const OBJECTIVES_TEXT"
    if anchor not in code:
        anchor = "const REALTIME_FLOW_TEXT"
    if anchor not in code:
        raise RuntimeError("can't anchor — neither OBJECTIVES_TEXT nor REALTIME_FLOW_TEXT found")
    end = code.find("`;", code.find(anchor))
    insertion = end + 2
    new_const = "\n\nconst CLIENT_HISTORY_TEXT = `" + body + "`;\n"
    code = code[:insertion] + new_const + code[insertion:]
    # Interpolate with sim-strip
    ret_anchor = "`;\n\nreturn [{"
    if ret_anchor in code and "${CLIENT_HISTORY_TEXT}" not in code:
        code = code.replace(
            ret_anchor,
            "\n${isSimulation ? '' : CLIENT_HISTORY_TEXT}\n" + ret_anchor, 1
        )
    return (code, True)


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        f = fetch(cur)
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
            print(f"[refresh_client_history] no change ({f['at']})")
            conn.rollback(); return
        cur.execute(
            "INSERT INTO leo_workflow_snapshots (workflow_id, reason, nodes_json, connections_json, notes) "
            "VALUES (%s,%s,%s::jsonb,%s::jsonb,%s) RETURNING id",
            (WORKFLOW_ID, "refresh_client_history", json.dumps(nodes), json.dumps(conns), "client_history"),
        )
        sid = cur.fetchone()["id"]
        cb["parameters"]["jsCode"] = new_code
        cur.execute('UPDATE workflow_entity SET nodes=%s WHERE id=%s',
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
        print(f"[refresh_client_history] applied snapshot #{sid}")
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
