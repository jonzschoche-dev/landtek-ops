#!/usr/bin/env python3
"""Deploy 057e — Kill the triple-send by removing the deploy_044 Safe Reply hack.

Bug: Safe Reply fires 3x per execution -> Reply to Client & Reply to Jonathan
each fire 3x -> client sees identical message 3 times.

Decoded source IDs in exec 545:
  Safe Reply fire 1: source = Switch router (output[3] new_contact branch)
  Safe Reply fire 2: source = Log Leo Interaction (fire #1)
  Safe Reply fire 3: source = Log Leo Interaction (fire #2)

Log Leo Interaction itself fires 2x because:
  - Parse Agent1 -> Log Leo Interaction (direct fan-out)
  - Insert Chat Note -> Log Leo Interaction (deploy_044 hack)

The deploy_044 edge 'Log Leo Interaction -> Safe Reply' was added to close
a dead end. But Switch router (with allMatchingOutputs=false single-match
mode) already routes EVERY message to ONE branch that eventually reaches
Safe Reply. The Log Leo Interaction -> Safe Reply edge is redundant and
the cause of duplicate replies.

Fix: remove the Log Leo Interaction -> Safe Reply edge. Log Leo Interaction
becomes terminal (its purpose is just to POST to the Flask logging endpoint;
no reply emission needed from it). Result: exactly 1 reply per execution.

Note: this also addresses Log Leo Interaction firing 2x — even with 2 fires,
it just logs to Flask twice (mostly harmless). The visible client-side
double-send IS the only reply emitter, and removing that edge collapses
all 3 fires to 1.
"""
import json, sys, psycopg2
from datetime import datetime, timezone

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")


def snapshot():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = f"/root/landtek/snapshots/leos_workflow_pre_057e_{ts}.json"
    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("""SELECT row_to_json(w)::text FROM (SELECT id, name, nodes, connections, "updatedAt" FROM workflow_entity WHERE name='Leos Workflow') w;""")
    with open(path, "w") as f: f.write(cur.fetchone()[0])
    cur.close(); conn.close()
    print(f" - snapshot: {path}")


def main():
    snapshot()
    conn = psycopg2.connect(**DSN); conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SELECT id, connections::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, conns = cur.fetchone()

    # Remove the edge Log Leo Interaction -> Safe Reply (deploy_044 hack)
    src = "Log Leo Interaction"
    target = "Safe Reply"
    if src in conns:
        main = conns[src].get("main", [])
        removed_count = 0
        for branch_idx, branch in enumerate(main):
            new_branch = [e for e in branch if e.get("node") != target]
            removed_in_branch = len(branch) - len(new_branch)
            main[branch_idx] = new_branch
            removed_count += removed_in_branch
        if removed_count:
            print(f" - removed {removed_count} edge(s): {src} -> {target}")
        else:
            print(f" - no edge {src} -> {target} to remove (already absent)")
    else:
        print(f" - {src} has no outgoing connections, nothing to remove")

    cur.execute("""
        UPDATE workflow_entity SET connections=%s::jsonb, "updatedAt"=now() WHERE id=%s
    """, (json.dumps(conns), wf_id))
    conn.commit()
    print(f" - workflow_entity row updated (id={wf_id})")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
    sys.path.insert(0, "/root/landtek")
    from deploy_helpers import commit_deploy
    msg = """Kill triple-send: remove deploy_044 Log Leo Interaction -> Safe Reply edge

Safe Reply was firing 3x per execution because:
  - Switch router output[3] (new_contact) -> Safe Reply (fire 1)
  - Log Leo Interaction -> Safe Reply (fire 2, from Parse Agent1 path)
  - Log Leo Interaction -> Safe Reply (fire 3, from Insert Chat Note path)

deploy_044 added the second edge to close a dead end. But Switch router
in single-match mode (allMatchingOutputs=false) already routes every
message to ONE branch that reaches Safe Reply. The Log Leo Interaction
edge is redundant.

Removing it collapses 3 fires -> 1 fire -> 1 client reply (correct).

Log Leo Interaction itself still fires 2x (Parse Agent1 + Insert Chat
Note both feed it), but it just POSTs to Flask /api/log_interaction
twice — Flask will dedupe or accept duplicate logs.

Verified by decoded sources of exec 545:
  Safe Reply sources: [Switch router, Log Leo Interaction, Log Leo Interaction]
After this deploy, expected:
  Safe Reply sources: [Switch router]    (only)"""
    commit_deploy("057e", msg)
