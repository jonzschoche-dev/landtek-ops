#!/usr/bin/env python3
"""Deploy 044 — Close 3 dead ends so Leo's replies actually send.

User-confirmed connection-graph fixes:

  Change 1: Log Leo Interaction -> Safe Reply
            (essential — closes the main dead end; reply now reaches Telegram)

  Change 2: Insert Chat Note -> Log Leo Interaction
            (closes Has Target Contact false-branch dead end)

  Change 3: Has File[false branch index 1] -> Insert Chat Note
            (closes Has File false-branch dead end — messages without files
             flow through the journal+reply chain instead of dying)

After this deploy, every successful Leo turn ends with Safe Reply -> Reply to
Client + Reply to Jonathan, regardless of which Switch router branch ran.

No node config changes. Only connection graph edits. Safe Reply already reads
from Parse Agent1 directly, so the reply text remains correct regardless of
which upstream branch reaches it.
"""
import json
import psycopg2

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")


def main():
    conn = psycopg2.connect(**DSN)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("SELECT id, connections::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, conns = cur.fetchone()

    changes = []

    # Change 1: Log Leo Interaction -> Safe Reply
    src = "Log Leo Interaction"
    edge = {"node": "Safe Reply", "type": "main", "index": 0}
    cur_edges = conns.get(src, {}).get("main", [])
    flat = [e for branch in cur_edges for e in branch]
    if not any(e == edge for e in flat):
        conns[src] = {"main": [[edge]]}
        changes.append(f"  + {src} -> Safe Reply")
    else:
        changes.append(f"  = {src} -> Safe Reply (already present, skipped)")

    # Change 2: Insert Chat Note -> Log Leo Interaction
    src = "Insert Chat Note"
    edge = {"node": "Log Leo Interaction", "type": "main", "index": 0}
    cur_edges = conns.get(src, {}).get("main", [])
    flat = [e for branch in cur_edges for e in branch]
    if not any(e == edge for e in flat):
        conns[src] = {"main": [[edge]]}
        changes.append(f"  + {src} -> Log Leo Interaction")
    else:
        changes.append(f"  = {src} -> Log Leo Interaction (already present, skipped)")

    # Change 3: Has File[false branch index 1] -> Insert Chat Note
    # Has File already has [true] -> Get a file, [false] -> []
    src = "Has File"
    edge = {"node": "Insert Chat Note", "type": "main", "index": 0}
    cur_main = conns.get(src, {}).get("main", [[], []])
    # Ensure two output slots exist (true at index 0, false at index 1)
    while len(cur_main) < 2:
        cur_main.append([])
    if not any(e == edge for e in cur_main[1]):
        cur_main[1].append(edge)
        conns[src]["main"] = cur_main
        changes.append(f"  + {src}[false] -> Insert Chat Note")
    else:
        changes.append(f"  = {src}[false] -> Insert Chat Note (already present, skipped)")

    for c in changes:
        print(c)

    cur.execute("""
        UPDATE workflow_entity SET connections=%s::jsonb, "updatedAt"=now() WHERE id=%s
    """, (json.dumps(conns), wf_id))
    conn.commit()
    print(f"\nworkflow_entity row updated (id={wf_id})")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
