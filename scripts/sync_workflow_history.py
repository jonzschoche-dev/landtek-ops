#!/usr/bin/env python3
"""sync_workflow_history.py - critical fix.

n8n v2.16 introduced workflow_history (the published/executing version) as
separate from workflow_entity (the draft). DB-side mutations to
workflow_entity DO NOT affect what n8n executes.

This script reads the current draft (workflow_entity) and writes the same
nodes+connections to workflow_history. EVERY workflow-mutating migration
MUST call this after its DB updates, otherwise the changes won't take effect.

Usage:
  python3 scripts/sync_workflow_history.py vSDQv1vfn6627bnA
"""
import argparse
import json
import sys

import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workflow_id")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        "SELECT nodes, connections FROM workflow_entity WHERE id = %s",
        (args.workflow_id,),
    )
    row = cur.fetchone()
    if not row:
        print(f"workflow {args.workflow_id} not found", file=sys.stderr)
        sys.exit(1)
    nodes, conns = row

    cur.execute(
        """UPDATE workflow_history
              SET nodes = %s::json,
                  connections = %s::json,
                  "updatedAt" = now()
            WHERE "workflowId" = %s""",
        (json.dumps(nodes), json.dumps(conns), args.workflow_id),
    )
    print(f"synced {cur.rowcount} workflow_history rows for {args.workflow_id}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
