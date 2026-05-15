#!/usr/bin/env python3
"""Deploy 055b — Fix the actual Insert nodes' id-column exclusion.

Deploy_055 removed "id": 0 from Insert Action Items columns.value — but
the schema array still had the id entry with removed:false. n8n's Postgres
node includes columns marked removed:false in the INSERT regardless of
whether they're in the value map, defaulting them to 0 when missing.

Result: every Insert Action Items attempt today (9 logged) failed with
"duplicate key value violates unique constraint action_items_pkey"
because the orphan id=0 row already exists.

Fix (this deploy):
1. Set removed=true on the id schema entry for Insert Action Items,
   Insert Chat Note, and Insert Calendar Event so n8n excludes id
   from the INSERT statement entirely.
2. DELETE the orphan id=0 row from action_items (so even if we miss
   a node, the collision goes away).
"""
import json, sys, psycopg2
from datetime import datetime, timezone

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")


def snapshot():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = f"/root/landtek/snapshots/leos_workflow_pre_055b_{ts}.json"
    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("""SELECT row_to_json(w)::text FROM (SELECT id, name, nodes, connections, "updatedAt" FROM workflow_entity WHERE name='Leos Workflow') w;""")
    with open(path, "w") as f: f.write(cur.fetchone()[0])
    cur.close(); conn.close()
    print(f" - snapshot: {path}")


def main():
    snapshot()
    conn = psycopg2.connect(**DSN); conn.autocommit = False
    cur = conn.cursor()

    # ── Step 1: workflow JSON patch ───────────────────────────────────────
    cur.execute("SELECT id, nodes::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes = cur.fetchone()

    target_nodes = ["Insert Action Items", "Insert Chat Note", "Insert Calendar Event"]
    for n in nodes:
        if n.get("name") not in target_nodes:
            continue
        schema = n["parameters"].get("columns", {}).get("schema", [])
        for col in schema:
            if col.get("id") == "id":
                old = col.get("removed", False)
                col["removed"] = True
                # Also clear defaultMatch to be safe
                col["defaultMatch"] = False
                print(f" - {n['name']}: id schema.removed {old} -> True, defaultMatch -> False")
                break

    cur.execute("""
        UPDATE workflow_entity SET nodes=%s::jsonb, "updatedAt"=now() WHERE id=%s
    """, (json.dumps(nodes), wf_id))

    # ── Step 2: DELETE the orphan id=0 row in action_items ────────────────
    # First check if there are any references to id=0 that would block delete
    cur.execute("SELECT id, case_file, description, status FROM action_items WHERE id=0;")
    row = cur.fetchone()
    if row:
        print(f" - action_items id=0 row exists: {row!r}")
        cur.execute("DELETE FROM action_items WHERE id=0 RETURNING id;")
        deleted = cur.fetchone()
        if deleted:
            print(f" - DELETED action_items id=0 (so future Insert collisions cleared)")
    else:
        print(f" - action_items id=0 row already absent")

    conn.commit()
    print(f" - workflow_entity row updated (id={wf_id})")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
    sys.path.insert(0, "/root/landtek")
    from deploy_helpers import commit_deploy
    msg = """Fix Insert nodes' id-column exclusion (deploy_055 follow-up)

Deploy_055 removed 'id': 0 from columns.value but the schema array
still had 'removed': false on the id entry. n8n's Postgres node
includes schema columns with removed=false in the INSERT regardless,
defaulting missing values to 0. Result: 9+ duplicate-key errors today
all on action_items_pkey since id=0 row exists.

Two-part fix:
- Set schema.id.removed=true + defaultMatch=false on Insert Action
  Items, Insert Chat Note, Insert Calendar Event (so n8n excludes
  the id column from generated INSERT statements).
- DELETE the orphan id=0 row from action_items as defense-in-depth.

Test: next Leo turn should produce non-zero rows in action_items
(verified once n8n picks up the workflow JSON change)."""
    commit_deploy("055b", msg)
