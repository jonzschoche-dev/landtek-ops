#!/usr/bin/env python3
"""refresh_objectives.py — feed Leo the per-matter objective state (deploy_332).

Every 5 min: regenerates OBJECTIVES_TEXT const in Context Builder so Leo
sees the 75% he was missing — the 20 transferees + per-matter operational
counts + active matter list.

Designed for scale: at N transferees per matter:
  N ≤ 25: list each with status + action needed
  N > 25: list TOP 10 by urgency (leads + recent_activity), then counts

Same per-sim-strip pattern as deploy_331 — only loaded for non-sim execs.
"""
from __future__ import annotations
import json, os, re, subprocess, sys, time
from datetime import datetime, timezone
import psycopg2, psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"


def fetch_objectives(cur) -> dict:
    f = {"refreshed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
    cur.execute("SELECT * FROM v_case_objectives ORDER BY case_file")
    f["cases"] = cur.fetchall()
    cur.execute("""
        SELECT case_file, id, canonical_name, accion_status, current_possession,
               action_needed, doc_eval_total, doc_eval_gaps
          FROM v_transferee_action_state
         ORDER BY case_file, accion_status, canonical_name
    """)
    f["transferees"] = cur.fetchall()
    # Recent gmail not yet matter-tagged
    cur.execute("""
        SELECT COUNT(*) FROM gmail_messages
         WHERE received_at > now() - interval '14 days'
           AND (case_file IS NULL OR case_file = '')
    """)
    f["emails_untagged_14d"] = cur.fetchone()[0]
    # Total transfer evaluations with gaps
    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE status='gap') AS gaps,
               COUNT(*) FILTER (WHERE status='satisfied') AS satisfied,
               COUNT(*) AS total
          FROM transfer_doc_status
    """)
    r = cur.fetchone()
    f["transfer_evals"] = {"gaps": r[0], "satisfied": r[1], "total": r[2]}
    return f


def render(f: dict) -> str:
    L = ["", f"OBJECTIVES — per-matter live state (refreshed {f['refreshed_at']}, every 5 min):", ""]
    L.append("ACTIVE MATTERS (operational snapshot):")
    if not f["cases"]:
        L.append("  (none in DB)")
    else:
        L.append("  | case_file       | transferees       | claims      | obligations | emails 7d |")
        L.append("  |-----------------|-------------------|-------------|-------------|-----------|")
        for c in f["cases"]:
            cf = c[0] or "(unspec)"
            tcount = f"{c[1]} (L{c[2]} A{c[3]} P{c[4]})"
            ccount = f"{c[6]}/{c[5]}"
            L.append(f"  | {cf:15s} | {tcount:17s} | {ccount:11s} | {c[7]:11d} | {c[8]:9d} |")
        L.append("  L=lead_defendant  A=awaiting_action  P=in_process(served/answered/defaulted)")
    L.append("")

    # Group transferees by case_file; compact when N > 25
    if f["transferees"]:
        by_case = {}
        for t in f["transferees"]:
            by_case.setdefault(t[0] or "(unspec)", []).append(t)
        for cf, rows in by_case.items():
            L.append(f"TRANSFEREES — {cf}  ({len(rows)} total):")
            if len(rows) <= 25:
                for t in rows:
                    gap_str = ""
                    if t[7] > 0:
                        gap_str = f"  gaps={t[7]}/{t[6]}"
                    pos = f"  pos={t[4][:30]}" if t[4] else ""
                    action = f"  → {t[5]}" if t[5] else ""
                    L.append(f"  [{t[1]}] {t[3]:20s} {t[2]:25s}{pos}{gap_str}{action}")
            else:
                # SCALE MODE: show only leads + top by recent_activity
                by_status = {}
                for t in rows:
                    by_status.setdefault(t[3], []).append(t)
                for status in ("lead_defendant", "awaiting_action", "served", "answered", "defaulted"):
                    if status not in by_status:
                        continue
                    L.append(f"  {status} ({len(by_status[status])}):")
                    for t in by_status[status][:5]:
                        L.append(f"    [{t[1]}] {t[2]}")
                    if len(by_status[status]) > 5:
                        L.append(f"    … + {len(by_status[status])-5} more (use get_transferee tool to drill down)")
            L.append("")

    L.append(f"EMAILS UNTAGGED (last 14d, no case_file assigned):  {f['emails_untagged_14d']}")
    L.append(f"TRANSFER EVALUATIONS:  {f['transfer_evals']['satisfied']} satisfied + {f['transfer_evals']['gaps']} gaps of {f['transfer_evals']['total']}")
    L.append("")
    L.append("USAGE — when asked:")
    L.append("  'who are the 20 transferees / how are they posturing?' → TRANSFEREES section above")
    L.append("  'where does Gloria Balane stand?' → find her in TRANSFEREES, cite accion_status + action_needed")
    L.append("  'what matters are active?' → ACTIVE MATTERS table")
    L.append("  'how many transfer evaluations are gaps?' → TRANSFER EVALUATIONS line")
    L.append("  'any emails I haven't tagged?' → EMAILS UNTAGGED line + offer to triage")
    return "\n".join(L)


def patch_const(code: str, body: str) -> tuple[str, bool]:
    if "const OBJECTIVES_TEXT" in code:
        m = re.search(r"(const OBJECTIVES_TEXT\s*=\s*`)([^`]*)(`;)", code, re.DOTALL)
        if not m: raise RuntimeError("OBJECTIVES_TEXT pattern broken")
        if m.group(2).strip() == body.strip():
            return (code, False)
        return (code[: m.start(2)] + body + code[m.end(2):], True)

    # First insertion — after REALTIME_FLOW_TEXT const
    anchor = "const REALTIME_FLOW_TEXT"
    if anchor not in code:
        raise RuntimeError("REALTIME_FLOW_TEXT not found — refresh_realtime_flow must run first")
    rt_end = code.find("`;", code.find(anchor))
    insertion = rt_end + 2
    new_const = "\n\nconst OBJECTIVES_TEXT = `" + body + "`;\n"
    code = code[:insertion] + new_const + code[insertion:]
    # Interpolate (with sim-strip pattern from deploy_331)
    ret_anchor = "`;\n\nreturn [{"
    if ret_anchor in code and "${OBJECTIVES_TEXT}" not in code:
        code = code.replace(
            ret_anchor,
            "\n${isSimulation ? '' : OBJECTIVES_TEXT}\n" + ret_anchor, 1
        )
    return (code, True)


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        f = fetch_objectives(cur)
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
            print(f"[refresh_objectives] no change ({f['refreshed_at']})")
            conn.rollback(); return
        cur.execute(
            "INSERT INTO leo_workflow_snapshots (workflow_id, reason, nodes_json, connections_json, notes) "
            "VALUES (%s,%s,%s::jsonb,%s::jsonb,%s) RETURNING id",
            (WORKFLOW_ID, "refresh_objectives", json.dumps(nodes), json.dumps(conns), "objectives"),
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
        print(f"[refresh_objectives] applied snapshot #{sid}")
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
