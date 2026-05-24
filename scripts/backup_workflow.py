#!/usr/bin/env python3
"""backup_workflow.py - snapshot a workflow_entity row to a JSON file before mutation.

Tier 1 bulletproofing (deploy_266). Any migration that mutates a workflow
should call this BEFORE mutation:

  python3 scripts/backup_workflow.py vSDQv1vfn6627bnA pre_deploy_266

Output: /root/landtek/workflow_backups/<id>_<tag>_<UTC_iso>.json
Always exit 0 even if backup file already exists (idempotent timestamp).
The .json files are git-tracked so the history is recoverable.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
BACKUP_DIR = "/root/landtek/workflow_backups"


def backup(workflow_id, tag):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    conn = psycopg2.connect(DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, name, active, nodes, connections, settings, "updatedAt", "versionId"
          FROM workflow_entity WHERE id = %s
    """, (workflow_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        print(f"workflow {workflow_id} not found", file=sys.stderr)
        sys.exit(1)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    path = os.path.join(BACKUP_DIR, f"{workflow_id}_{tag}_{ts}.json")
    # Serialize datetime in updatedAt
    if "updatedAt" in row and row["updatedAt"]:
        row["updatedAt"] = row["updatedAt"].isoformat()
    with open(path, "w") as f:
        json.dump(dict(row), f, indent=2, default=str)
    print(path)
    return path


def restore(workflow_id, backup_path):
    """Restore from a backup JSON file. nodes/connections/settings are rolled back;
    id stays the same so n8n continues to recognize the workflow."""
    with open(backup_path) as f:
        data = json.load(f)
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute(
        """UPDATE workflow_entity
              SET nodes = %s::json,
                  connections = %s::json,
                  settings = %s::json,
                  "updatedAt" = now()
            WHERE id = %s""",
        (
            json.dumps(data["nodes"]),
            json.dumps(data["connections"]),
            json.dumps(data.get("settings") or {}),
            workflow_id,
        ),
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"restored {workflow_id} from {backup_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workflow_id")
    ap.add_argument("tag", help="short tag for the backup filename (e.g., 'pre_deploy_266')")
    ap.add_argument("--restore-from", help="instead of backing up, restore from this path")
    args = ap.parse_args()
    if args.restore_from:
        restore(args.workflow_id, args.restore_from)
    else:
        backup(args.workflow_id, args.tag)


if __name__ == "__main__":
    main()
