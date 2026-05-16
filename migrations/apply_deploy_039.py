#!/usr/bin/env python3
"""Deploy 039 — Anthropic Chat Model resilience.

Add maxRetries + timeout to the Anthropic Chat Model node's options block so
transient 529 Overloaded responses get retried with exponential backoff
instead of bubbling up as workflow errors.

maxRetries=3: covers most transient overloads (Anthropic typically recovers
within 1-5 seconds during congestion).
timeout=180000ms (3 min): generous ceiling for slow responses on large
system prompts (20k+ chars) — well under n8n's default execution timeout.
"""
import json
import psycopg2

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")


def main():
    conn = psycopg2.connect(**DSN)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("SELECT id, nodes::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes = cur.fetchone()

    changed = False
    for n in nodes:
        if n.get("name") != "Anthropic Chat Model":
            continue
        opts = n["parameters"].setdefault("options", {})
        before = dict(opts)
        opts["maxRetries"] = 3
        opts["timeout"] = 180000
        n["parameters"]["options"] = opts
        changed = True
        print(f" - Anthropic Chat Model: options updated")
        print(f"     before: {before}")
        print(f"     after:  {opts}")

    if not changed:
        print("No changes — Anthropic Chat Model node not found.")
        return

    cur.execute("""
        UPDATE workflow_entity SET nodes=%s::jsonb, "updatedAt"=now() WHERE id=%s
    """, (json.dumps(nodes), wf_id))
    conn.commit()
    print(f"\nworkflow_entity row updated (id={wf_id})")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
