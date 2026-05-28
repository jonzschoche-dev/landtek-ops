#!/usr/bin/env python3
"""Deploy 289 — make the memory-write tail fail-safe (Qdrant Write).

Root cause of tonight's recurring "error" execs (696, 697, 698, ...):
  - Gemini Embed returns {"error": "access to env vars denied"} (n8n is
    blocking $env.GEMINI_API_KEY access; the key is also rate-limited).
  - Gemini Embed has onError=continueRegularOutput, so it passes the error
    object downstream instead of stopping.
  - Qdrant Write's jsonBody does `$json.data[0].embedding`. With $json =
    {error: ...}, `$json.data` is undefined, `$json.data[0]` THROWS, the
    whole expression returns undefined, and Qdrant Write (onError=None)
    errors the entire execution.

Net effect: Leo replies fine, but every conversation is marked 'error' and
the operator sees red. This is the same silent-failure CLASS we've hit
repeatedly — a non-critical tail node taking down the whole run.

Architectural fix (this deploy):
  1. Qdrant Write onError := continueRegularOutput
       A failed memory-write can NEVER again error the conversation.
  2. jsonBody guarded: if the embedding is missing/undefined, emit
       {"points": []}  (a valid Qdrant no-op upsert) instead of throwing.
       When the embedding IS present, write the point as before.

This makes the memory tail degrade gracefully: when embeddings work, memory
accumulates; when they don't (rate limit, env block), the conversation still
completes cleanly and we simply skip that one vector.

NB: this does NOT fix the underlying Gemini Embed env-access problem — that
requires either N8N_BLOCK_ENV_ACCESS_IN_NODE=false in docker-compose or a
fresh embedding API key. Tracked separately. But memory is non-critical, so
unblocking the conversation path is the priority.

Idempotent."""
import json
import psycopg2
import psycopg2.extras

WORKFLOW_ID = "vSDQv1vfn6627bnA"

GUARDED_BODY = (
    "={{ (() => {\n"
    "  try {\n"
    "    const emb = ($json && $json.data && $json.data[0] && $json.data[0].embedding) ? $json.data[0].embedding : null;\n"
    "    if (!emb || !Array.isArray(emb) || emb.length === 0) {\n"
    "      return JSON.stringify({ points: [] });\n"
    "    }\n"
    "    let convId;\n"
    "    try { convId = $('Log Conversation').first().json.id; } catch(e) { convId = Date.now(); }\n"
    "    let caseFile, clientName, rawText, category, ts;\n"
    "    try { caseFile = $('Parse Agent1').first().json.case_file; } catch(e) { caseFile = null; }\n"
    "    try { clientName = $('Context Builder').first().json.senderName; } catch(e) { clientName = null; }\n"
    "    try { rawText = $('Context Builder').first().json.rawText; } catch(e) { rawText = null; }\n"
    "    try { category = $('Parse Agent1').first().json.classification; } catch(e) { category = null; }\n"
    "    try { ts = $('Parse Agent1').first().json.timestamp; } catch(e) { ts = new Date().toISOString(); }\n"
    "    return JSON.stringify({ points: [ { id: convId, vector: emb, payload: { case_file: caseFile, client_name: clientName, message: rawText, category: category, timestamp: ts } } ] });\n"
    "  } catch(e) {\n"
    "    return JSON.stringify({ points: [] });\n"
    "  }\n"
    "})() }}"
)

conn = psycopg2.connect("postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
conn.autocommit = False
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
cur.execute("SELECT nodes FROM workflow_entity WHERE id=%s FOR UPDATE", (WORKFLOW_ID,))
nodes = cur.fetchone()["nodes"]

patched = False
for n in nodes:
    if n.get("name") == "Qdrant Write":
        n["onError"] = "continueRegularOutput"
        # also set legacy continueOnFail for older n8n compatibility
        n["continueOnFail"] = True
        n.setdefault("parameters", {})["jsonBody"] = GUARDED_BODY
        n["parameters"]["specifyBody"] = "json"
        patched = True
        print("Patched Qdrant Write:")
        print("  onError = continueRegularOutput")
        print("  continueOnFail = True")
        print("  jsonBody = guarded (emits {points:[]} when embedding missing)")
        break

if not patched:
    print("Qdrant Write node not found")
    raise SystemExit(1)

cur.execute(
    'UPDATE workflow_entity SET nodes=%s, "updatedAt"=now() WHERE id=%s',
    (json.dumps(nodes), WORKFLOW_ID),
)
conn.commit()
print("DB UPDATED")
