#!/usr/bin/env python3
"""Deploy 040 — Tool node timeouts.

Add options.timeout to every @n8n/n8n-nodes-langchain.toolHttpRequest node so
Leo doesn't hang indefinitely when leo-tools Flask is slow or wedged.

Chosen value: 15000 ms (15s). All tool endpoints are internal (Flask at
172.18.0.1:8765) hitting Postgres. Healthy responses are <1s; 15s is generous
ceiling that still surfaces a problem rather than hiding it.

Not touching the non-tool HTTP nodes (Gemini Embed, Qdrant Write, Log Leo
Interaction) per the user's specific scope. Easy to add later.
"""
import json
import psycopg2

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")

TOOL_TIMEOUT_MS = 15000
TOOL_TYPE = "@n8n/n8n-nodes-langchain.toolHttpRequest"


def main():
    conn = psycopg2.connect(**DSN)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("SELECT id, nodes::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes = cur.fetchone()

    patched = []
    for n in nodes:
        if n.get("type") != TOOL_TYPE:
            continue
        opts = n["parameters"].setdefault("options", {})
        before = opts.get("timeout")
        opts["timeout"] = TOOL_TIMEOUT_MS
        n["parameters"]["options"] = opts
        patched.append((n.get("name"), before, TOOL_TIMEOUT_MS))

    for name, before, after in patched:
        print(f" - {name}: timeout {before} -> {after} ms")

    if not patched:
        print("No tool nodes found.")
        return

    cur.execute("""
        UPDATE workflow_entity SET nodes=%s::jsonb, "updatedAt"=now() WHERE id=%s
    """, (json.dumps(nodes), wf_id))
    conn.commit()
    print(f"\nworkflow_entity row updated (id={wf_id}); {len(patched)} tool nodes patched")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
