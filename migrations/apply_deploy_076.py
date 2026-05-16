#!/usr/bin/env python3
"""Deploy 076 — Fix duplicate Send to Target Contact firings.

Bug: when Jonathan ran a Rule C inquiry-to-relay command, Don Qi (the
target client) received TWO copies of the inquiry. Two pending_inquiry
rows were inserted per execution.

Cause: 'Has Target Contact' IF node sat at the end of the action_items
processing chain:
  Parse Agent1 -> Update Case Intelligence -> Split Action Items ->
    Insert Action Items -> Gemini Embed -> Qdrant Write -> Has Target Contact

Split Action Items uses `items.map(...)` -> outputs N items for N action_items.
Even when action_items=0, somewhere in the chain (likely Gemini Embed or
Qdrant Write) is emitting 2 items per logical execution. Each Has Target
Contact input runs the true branch -> Send to Target Contact fires N times.

Fix: rewire so Has Target Contact gets input directly from Parse Agent1
(which always emits exactly 1 item from `return [{ json: parsed }]`).
The action_items pipeline keeps doing its DB+embedding work but no longer
gates the target send.

Before:
  Qdrant Write -> Has Target Contact (true) -> Send to Target Contact
After:
  Parse Agent1 -> Has Target Contact (true) -> Send to Target Contact
  (Qdrant Write's downstream becomes terminal — it was only feeding the IF)
"""
import json
import os
import sys
import argparse

sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

WF_NAME = "Leos Workflow"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["staging", "prod"], required=True)
    args = parser.parse_args()

    if args.target == "staging":
        DSN = dict(host="127.0.0.1", port=5433, dbname="n8n", user="n8n", password="n8npassword")
    else:
        DSN = dict(host="172.18.0.3", port=5432, dbname="n8n", user="n8n", password="n8npassword")
    print(f"  target={args.target}  dsn={DSN['host']}:{DSN['port']}")

    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name=%s", (WF_NAME,))
    wf_id, nodes, conns = cur.fetchone()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_076_{args.target}_{ts}.json"
    os.makedirs("/root/landtek/snapshots", exist_ok=True)
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes, "connections": conns}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    # ── 1. Disconnect Qdrant Write -> Has Target Contact ─────────────────
    if "Qdrant Write" in conns:
        qw_main = conns["Qdrant Write"].get("main", [])
        for branch in qw_main:
            branch[:] = [t for t in branch if t.get("node") != "Has Target Contact"]
        # If the branch is now empty AND that was the only branch, leave it as []
        # so Qdrant Write properly terminates
        print(f"  ✓ disconnected Qdrant Write -> Has Target Contact (action_items pipeline now terminates at Qdrant)")

    # ── 2. Add Parse Agent1 -> Has Target Contact to Parse Agent1's fan-out ──
    pa_main = conns.get("Parse Agent1", {}).get("main", [[]])
    existing_dst = {t["node"] for t in pa_main[0]}
    if "Has Target Contact" not in existing_dst:
        pa_main[0].append({"node": "Has Target Contact", "type": "main", "index": 0})
        print(f"  ✓ added Parse Agent1 -> Has Target Contact (single-item path)")
    else:
        print(f"  ⚠ Parse Agent1 -> Has Target Contact already exists, skipping")
    conns["Parse Agent1"] = {"main": pa_main}

    cur.close(); conn.close()

    # ── 3. Persist via fixed patch_workflow_dual ───────────────────────────
    if args.target == "staging":
        import time
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute(
            'UPDATE workflow_entity SET connections=%s::jsonb, "updatedAt"=now() WHERE id=%s',
            (json.dumps(conns), wf_id))
        cur.execute("""UPDATE workflow_history SET connections=%s::json
                         WHERE "workflowId"=%s
                           AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""",
                    (json.dumps(conns), wf_id, wf_id))
        cur.execute('UPDATE workflow_entity SET active=false, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); time.sleep(2)
        cur.execute('UPDATE workflow_entity SET active=true, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()
        print(f"  ✓ staging connections updated + reactivated")
    else:
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, connections=conns)


if __name__ == "__main__":
    main()
