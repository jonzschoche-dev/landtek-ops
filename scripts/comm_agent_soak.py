#!/usr/bin/env python3
"""comm_agent_soak.py — drive real inbound through L4 (SHADOW) + monitor the hair-split decisions.

Why a driver: L4 (comm_agent_max.handle_chat_event) is not yet inline-wired to the live inbound reply
path (deliberate — the working leo_service/n8n flows stay untouched). So this feeds NEW inbound
channel_messages through L4 in SHADOW (emits nothing) so `comm_agent_shadow` (channel_audit) +
`propagation_log` accumulate REAL per-role decisions on live traffic, then summarizes them with the
load-bearing invariant check. Read-only w.r.t. production; sends nothing; degrade-don't-crash.

  --tick     drive new inbound through L4 (shadow) then write the summary   (for the timer)
  --status   print the current summary only
"""
import os
import sys

sys.path.insert(0, "/root/landtek/scripts")
sys.path.insert(0, "/root/landtek/leo_tools")
import psycopg2
import psycopg2.extras
import comm_agent_max as CAM

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
SUMMARY = "/root/landtek/notifications/comm_agent_soak_summary.txt"


def _ensure(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS comm_agent_soak_state (
                     id int PRIMARY KEY DEFAULT 1, last_cm_id bigint DEFAULT 0, updated_at timestamptz DEFAULT now())""")
    cur.execute("INSERT INTO comm_agent_soak_state (id,last_cm_id) VALUES (1,0) ON CONFLICT (id) DO NOTHING")


def drive(cur):
    _ensure(cur)
    cur.execute("SELECT last_cm_id FROM comm_agent_soak_state WHERE id=1")
    cursor = cur.fetchone()["last_cm_id"]
    cur.execute("""SELECT id FROM channel_messages WHERE direction='inbound' AND id > %s
                   ORDER BY id ASC LIMIT 100""", (cursor,))
    rows = cur.fetchall(); processed = 0; maxid = cursor
    for r in rows:
        try:
            CAM.handle_chat_event(cur, r["id"])  # SHADOW — writes comm_agent_shadow + propagation_log, sends nothing
            processed += 1
        except Exception as e:
            print(f"[soak] cm {r['id']}: {str(e)[:80]}")
        maxid = max(maxid, r["id"])
    if maxid > cursor:
        cur.execute("UPDATE comm_agent_soak_state SET last_cm_id=%s, updated_at=now() WHERE id=1", (maxid,))
    return processed


def summarize(cur):
    cur.execute("""
        SELECT payload->>'role' AS role, count(*) AS n,
               round(avg((payload->>'internal_ego_nodes')::float))::int AS avg_ego,
               round(100.0*avg(((payload->>'would_clamp')::boolean)::int), 1) AS pct_clamp,
               count(*) FILTER (WHERE (payload->>'would_clamp')::boolean AND result <> 'hold_for_operator') AS violations
          FROM channel_audit
         WHERE event_type='comm_agent_shadow' AND created_at > now() - interval '48 hours'
         GROUP BY 1 ORDER BY 2 DESC""")
    rows = cur.fetchall()
    cur.execute("""SELECT result AS next_action, count(*) n FROM channel_audit
                    WHERE event_type='comm_agent_shadow' AND created_at > now()-interval '48 hours'
                    GROUP BY 1 ORDER BY 2 DESC""")
    actions = cur.fetchall()
    total_viol = sum((r["violations"] or 0) for r in rows)

    lines = ["COMM-AGENT-MAX shadow soak — per-role hair-split (last 48h)",
             f"{'role':14} {'n':>5} {'avg_ego':>8} {'%clamp':>7} {'violations':>11}"]
    for r in rows:
        lines.append(f"{(r['role'] or 'unresolved'):14} {r['n']:>5} {str(r['avg_ego']):>8} "
                     f"{str(r['pct_clamp']):>7} {r['violations']:>11}")
    lines.append("next_action: " + ", ".join(f"{a['next_action']}={a['n']}" for a in actions))
    lines.append(f"INVARIANT (would_clamp ⇒ hold_for_operator): {'✓ CLEAN' if total_viol==0 else '✗ '+str(total_viol)+' VIOLATIONS'}")
    summary = "\n".join(lines)

    if total_viol:  # the one thing that must never happen — surface it
        try:
            cur.execute("SELECT ontology_reject('A79_CLAMP_NOT_HELD', %s)",
                        (f"{total_viol} comm_agent_shadow rows: would_clamp=True but next_action<>hold_for_operator",))
        except Exception:
            pass
    try:
        os.makedirs(os.path.dirname(SUMMARY), exist_ok=True)
        with open(SUMMARY, "w") as f:
            f.write(summary + "\n")
    except Exception:
        pass
    return summary


def main():
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if "--tick" in sys.argv:
        n = drive(cur)
        print(f"[soak] drove {n} new inbound through L4 (shadow)")
        print(summarize(cur))
    elif "--status" in sys.argv:
        print(summarize(cur))
    else:
        print(__doc__)
    cur.close(); c.close()


if __name__ == "__main__":
    main()
