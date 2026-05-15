#!/usr/bin/env python3
"""Deploy 043 — Force Fetch Pending Inquiries to always return >= 1 row.

Bug: alwaysOutputData=true (deploy 042) didn't actually fix the gate problem.
That setting governs "no input data" behavior, not "0 query result rows."
When the SELECT returns 0 rows, n8n still stops the downstream flow.

Fix: rewrite the query to UNION-append a NULL sentinel row so the result
set always has at least 1 item. Context Builder already filters by .id
truthiness, so the sentinel (with id=NULL) is dropped from pendingInquiries[].

Real rows: positive id → kept
Sentinel:  id=NULL → filtered out
"""
import json
import psycopg2

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")

# Note the parens around the inner SELECT — required for ORDER BY inside UNION.
NEW_QUERY = (
    "(SELECT id, question_text, relayed_message, asked_at::text AS asked_at, target_client_name "
    "FROM pending_inquiries "
    "WHERE target_chat_id = '{{ $('Telegram Trigger').first().json.message.from.id }}' "
    "AND status='open' AND expires_at > now() "
    "ORDER BY asked_at ASC LIMIT 3) "
    "UNION ALL "
    "SELECT NULL::int, NULL::text, NULL::text, NULL::text, NULL::text;"
)


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
        old_query = n["parameters"].get("query", "")
        n["parameters"]["query"] = NEW_QUERY
        patched = True
        print(f" - Fetch Pending Inquiries query rewritten ({len(old_query)} -> {len(NEW_QUERY)} chars)")
        print(f"     real rows: positive id (preserved), sentinel: NULL id (filtered by Context Builder)")

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
