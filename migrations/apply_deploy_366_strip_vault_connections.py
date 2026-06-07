#!/usr/bin/env python3
"""apply_deploy_366_strip_vault_connections.py — remove ai_tool connections
for the six vault tool nodes.

Bug found 2026-06-07: Leo's first real vault call (exec 2265, Jonathan
instructing Leo to assist Kristyle building the vault) threw:
  "The node @n8n/n8n-nodes-langchain.toolHttpRequest has a supplyData
   method but no execute method"

Root cause: deploy_362 added explicit `ai_tool` outgoing connections from
each vault tool to AI Agent. n8n's working pattern (visible on
query_documents, get_thread, etc.) is to NOT connect tool nodes at all —
the AI Agent auto-discovers tools in the workflow via their type. The
explicit connection caused n8n's runtime to try invoking the tool as a
regular execute() node, which doesn't exist on tool nodes.

Fix: delete the connection entries for all six vault tool nodes. Auto-
discovery handles the rest.

This was already applied live via /tmp/fix_vault_conns.py at 2026-06-07
~03:35 UTC (snapshot 1682). This migration is the durable record.

Idempotent: re-runs are no-ops if the connections are already absent.
"""
from __future__ import annotations
import json
import os
import sys

import psycopg2

PG_DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"
VAULT_TOOLS = [
    "vault_register", "vault_attach_scan", "vault_find",
    "vault_queue", "vault_missing", "vault_last",
]


def main():
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT nodes, connections FROM workflow_entity WHERE id = %s",
                (WORKFLOW_ID,))
    nodes_raw, conns_raw = cur.fetchone()
    nodes_json = nodes_raw if isinstance(nodes_raw, str) else json.dumps(nodes_raw)
    conns = (json.loads(conns_raw) if isinstance(conns_raw, str)
             else conns_raw)

    cur.execute("""
        INSERT INTO leo_workflow_snapshots (workflow_id, reason, nodes_json, connections_json)
        VALUES (%s, %s, %s, %s) RETURNING id
    """, (WORKFLOW_ID, "pre-deploy_366 strip vault connections",
          nodes_json, json.dumps(conns)))
    print(f"snapshot id: {cur.fetchone()[0]}")

    removed = []
    for t in VAULT_TOOLS:
        if t in conns:
            del conns[t]
            removed.append(t)
    if removed:
        cur.execute('UPDATE workflow_entity SET connections = %s, "updatedAt"=NOW() WHERE id = %s',
                    (json.dumps(conns), WORKFLOW_ID))
        print(f"removed connections for: {removed}")
    else:
        print("nothing to remove — already absent")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
