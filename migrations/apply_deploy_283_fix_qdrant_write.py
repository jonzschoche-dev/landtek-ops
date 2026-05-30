#!/usr/bin/env python3
"""Deploy 283 — fix Qdrant Write node payload format (cascading silent error).

Symptom: every Leo Telegram interaction marked status=error in n8n. Root cause:
the Qdrant Write HTTP Request node used `bodyParameters` (keypair) mode with
`name: "points"` and an expression value that evaluates to an array. n8n
serializes such complex expression values as a JSON STRING inside the body
object, producing:

    { "points": "[{...}]" }   ← stringified, breaks Qdrant
    instead of
    { "points": [{...}] }     ← what Qdrant requires

Qdrant rejects with HTTP 400 "Invalid PointInsertOperations format".

Fix: switch the node to `specifyBody: 'json'` + `jsonBody: <expression>` so the
expression result IS the raw JSON body. This is also the n8n-idiomatic way to
send computed JSON bodies.

Side effects of the silent failure (before this fix):
- Every Leo interaction marked error in n8n (false alarm — Leo still replied,
  but vector-DB save at the end failed)
- Qdrant collection stale — conversational memory not accumulating

Post-deploy:
- Telegram message to Leo from Jonathan should produce status=success
- Qdrant points_count increments per interaction

Idempotent: if the node is already in jsonBody mode, second run is a no-op.

Audit: app.actor not used (workflow JSON mutation, audited via workflow_history).
"""

import json
import psycopg2
import psycopg2.extras

conn = psycopg2.connect("postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
conn.autocommit = False
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
cur.execute('SELECT nodes FROM workflow_entity WHERE id=%s FOR UPDATE', ("vSDQv1vfn6627bnA",))
row = cur.fetchone()
nodes = row["nodes"]

# Build the new jsonBody expression. Use single-quoted Python string so $() is preserved.
JSON_BODY_EXPR = (
    '={{ JSON.stringify({ points: [ { '
    'id: $("Log Conversation").first().json.id, '
    'vector: $json.data[0].embedding, '
    'payload: { '
    'case_file: $("Parse Agent1").first().json.case_file, '
    'client_name: $("Context Builder").first().json.senderName, '
    'message: $("Context Builder").first().json.rawText, '
    'category: $("Parse Agent1").first().json.classification, '
    'timestamp: $("Parse Agent1").first().json.timestamp '
    '} } ] }) }}'
)

patched = False
for n in nodes:
    if n.get("name") == "Qdrant Write":
        params = n["parameters"]
        params["specifyBody"] = "json"
        params["jsonBody"] = JSON_BODY_EXPR
        params.pop("bodyParameters", None)
        patched = True
        print("PATCHED Qdrant Write")
        print("New jsonBody:")
        print(JSON_BODY_EXPR)
        break

if not patched:
    print("NO PATCH MADE — Qdrant Write node not found")
    raise SystemExit(1)

cur.execute(
    'UPDATE workflow_entity SET nodes=%s, "updatedAt"=now() WHERE id=%s',
    (json.dumps(nodes), "vSDQv1vfn6627bnA"),
)
conn.commit()
print(f"DB UPDATED — workflow_entity.nodes rewritten ({len(nodes)} nodes)")
