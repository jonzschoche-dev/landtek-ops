#!/usr/bin/env python3
"""Deploy 042 — Fix Fetch Pending Inquiries gate bug.

Bug: when Fetch Pending Inquiries returns 0 rows (the normal case — most
clients don't have pending inquiries), n8n stops the entire downstream flow
because there are no items to pass. The AI Agent never fires, leaving
executions as "success" with no output.

Fix: set alwaysOutputData=true on the Fetch Pending Inquiries node so n8n
always passes at least one item downstream (an empty json object if 0 rows).

Context Builder already handles this — it reads $('Fetch Pending Inquiries').all()
and filters by .id, so empty items become pendingInquiries=[].
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

    patched = False
    for n in nodes:
        if n.get("name") != "Fetch Pending Inquiries":
            continue
        before = n.get("alwaysOutputData", False)
        n["alwaysOutputData"] = True
        patched = True
        print(f" - Fetch Pending Inquiries: alwaysOutputData {before} -> True")

    if not patched:
        print("Node not found.")
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
