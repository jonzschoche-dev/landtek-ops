#!/usr/bin/env python3
"""leo_proposal_apply.py — apply an approved improvement proposal (deploy_305).

Usage:
    python3 scripts/leo_proposal_apply.py <proposal_id>          # apply
    python3 scripts/leo_proposal_apply.py <proposal_id> --dry    # preview only
    python3 scripts/leo_proposal_apply.py --rollback <snapshot_id>

What it does:
  1. Loads proposal #ID, ensures status in ('pending','approved').
  2. Loads current workflow_entity.nodes for vSDQv1vfn6627bnA.
  3. Takes a snapshot row in leo_workflow_snapshots and remembers the snapshot_id.
  4. Applies patch_payload to the AI Agent node's systemMessage:
       - system_prompt_add:     append patch_payload.append_text
       - system_prompt_replace: replace exactly one occurrence of find_text with replace_text
  5. Writes new nodes back to workflow_entity, syncs workflow_history.
  6. Restarts n8n container so the change picks up.
  7. Updates proposal: status='applied', applied_at=now(), snapshot_id=<sid>.
  8. Prints next-step instructions for verify.

Rollback:
    python3 scripts/leo_proposal_apply.py --rollback <snapshot_id>
  loads that snapshot back into workflow_entity, syncs history, restarts n8n.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time

import psycopg2
import psycopg2.extras

DSN         = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"


def sync_history(conn, workflow_id: str):
    try:
        subprocess.run(
            ["python3", "/root/landtek/scripts/sync_workflow_history.py", workflow_id],
            check=True, capture_output=True, text=True, timeout=30,
        )
        print("  ✓ workflow_history synced")
    except Exception as e:
        print(f"  ! workflow_history sync FAILED: {e}", file=sys.stderr)
        raise


def restart_n8n():
    print("  ▸ restarting n8n container …")
    subprocess.run(["docker", "restart", "n8n-n8n-1"], check=True, capture_output=True, timeout=60)
    deadline = time.time() + 60
    while time.time() < deadline:
        r = subprocess.run(["curl", "-sf", "http://localhost:5678/healthz"],
                           capture_output=True, timeout=5)
        if r.returncode == 0:
            print("  ✓ n8n ready")
            return
        time.sleep(2)
    raise RuntimeError("n8n did not return healthz=200 within 60s")


def get_workflow_nodes(cur):
    cur.execute("SELECT nodes, connections FROM workflow_entity WHERE id = %s FOR UPDATE",
                (WORKFLOW_ID,))
    r = cur.fetchone()
    if not r:
        raise RuntimeError("workflow not found")
    return r["nodes"], r["connections"]


def write_workflow_nodes(cur, nodes):
    cur.execute(
        'UPDATE workflow_entity SET nodes=%s, "updatedAt"=now() WHERE id=%s',
        (json.dumps(nodes), WORKFLOW_ID),
    )


def snapshot(cur, nodes, conns, reason: str, notes: str) -> int:
    cur.execute(
        "INSERT INTO leo_workflow_snapshots (workflow_id, reason, nodes_json, connections_json, notes) "
        "VALUES (%s, %s, %s::jsonb, %s::jsonb, %s) RETURNING id",
        (WORKFLOW_ID, reason, json.dumps(nodes), json.dumps(conns), notes),
    )
    return cur.fetchone()["id"]


def find_ai_agent(nodes):
    for n in nodes:
        if n.get("name") == "AI Agent":
            return n
    raise RuntimeError("AI Agent node not found")


def apply_patch_to_prompt(current: str, kind: str, payload: dict) -> str:
    if kind == "system_prompt_add":
        sep = "\n\n" if current and not current.endswith("\n") else ""
        return current + sep + payload["append_text"].strip() + "\n"
    if kind == "system_prompt_replace":
        find = payload["find_text"]
        repl = payload["replace_text"]
        if find not in current:
            raise RuntimeError("find_text not present in current system prompt")
        if current.count(find) > 1:
            raise RuntimeError("find_text appears more than once — refusing ambiguous replace")
        return current.replace(find, repl, 1)
    raise RuntimeError(f"unknown patch_kind {kind!r}")


def rollback(snapshot_id: int):
    conn = psycopg2.connect(DSN); conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT nodes_json FROM leo_workflow_snapshots WHERE id=%s", (snapshot_id,))
        r = cur.fetchone()
        if not r:
            print(f"snapshot #{snapshot_id} not found", file=sys.stderr); sys.exit(2)
        nodes = r["nodes_json"]
        cur.execute('UPDATE workflow_entity SET nodes=%s, "updatedAt"=now() WHERE id=%s',
                    (json.dumps(nodes), WORKFLOW_ID))
        conn.commit()
        sync_history(conn, WORKFLOW_ID)
        restart_n8n()
        print(f"✓ rolled back to snapshot #{snapshot_id}")
    finally:
        cur.close(); conn.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)

    if sys.argv[1] == "--rollback":
        rollback(int(sys.argv[2])); return

    pid = int(sys.argv[1])
    dry = "--dry" in sys.argv

    conn = psycopg2.connect(DSN); conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT * FROM leo_improvement_proposals WHERE id=%s FOR UPDATE", (pid,))
    p = cur.fetchone()
    if not p:
        print(f"proposal #{pid} not found"); sys.exit(2)
    if p["status"] not in ("pending", "approved"):
        print(f"proposal #{pid} status is {p['status']!r} — refusing to apply"); sys.exit(2)

    print(f"━━━ Proposal #{pid} — {p['failure_pattern']} ━━━")
    print(f"  kind:        {p['patch_kind']}")
    print(f"  baseline:    {p['baseline_pass_rate']}")
    print(f"  targets:     {p['target_probes']}")
    print(f"  rationale:   {p['rationale'][:300]}")
    print(f"  expected:    {p['expected_impact']}")
    print(f"\n--- patch_diff (preview) ---\n{p['patch_diff'][:1500]}\n")

    nodes, conns = get_workflow_nodes(cur)
    agent = find_ai_agent(nodes)
    current_prompt = agent.get("parameters", {}).get("options", {}).get("systemMessage", "")
    try:
        new_prompt = apply_patch_to_prompt(current_prompt, p["patch_kind"], p["patch_payload"])
    except Exception as e:
        print(f"\n✗ patch could not be applied: {e}", file=sys.stderr)
        cur.execute(
            "UPDATE leo_improvement_proposals SET status='failed_to_apply', "
            "notes = COALESCE(notes,'') || %s WHERE id=%s",
            (f"\napply error: {e}", pid),
        )
        conn.commit()
        sys.exit(2)

    delta = len(new_prompt) - len(current_prompt)
    print(f"system prompt size: {len(current_prompt)} → {len(new_prompt)}  (delta {delta:+d})")

    if dry:
        print("\n--dry: not writing. exiting.")
        conn.rollback(); return

    sid = snapshot(cur, nodes, conns, reason=f"pre-deploy_305 proposal #{pid}",
                   notes=p["failure_pattern"])
    agent.setdefault("parameters", {}).setdefault("options", {})["systemMessage"] = new_prompt
    write_workflow_nodes(cur, nodes)
    cur.execute(
        "UPDATE leo_improvement_proposals "
        "SET status='applied', applied_at=now(), snapshot_id=%s, reviewed_by='termius', reviewed_at=now() "
        "WHERE id=%s",
        (sid, pid),
    )
    conn.commit()
    print(f"\n  ✓ snapshot #{sid} taken")
    sync_history(conn, WORKFLOW_ID)
    restart_n8n()
    print(f"\n  ✓ proposal #{pid} APPLIED")
    print(f"\nNext step (after ~30 min of simulator runs against target probes):")
    print(f"    python3 scripts/leo_proposal_verify.py {pid}")
    print(f"\nIf you need to undo:")
    print(f"    python3 scripts/leo_proposal_apply.py --rollback {sid}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
