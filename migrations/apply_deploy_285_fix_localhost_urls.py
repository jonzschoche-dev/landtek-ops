#!/usr/bin/env python3
"""Deploy 285 — fix three workflow nodes that point n8n at `localhost:8765`.

The n8n container resolves `localhost` to its own loopback (::1) where nothing
is listening. The leo-tools Flask service runs on the host at 0.0.0.0:8765,
reachable from inside the container via the Docker bridge gateway 172.18.0.1.

The rest of the workflow (~9 nodes) already uses 172.18.0.1. Three nodes
regressed at some point and use localhost:

  - Call Onboarding Endpoint  (CRITICAL — new clients get silently dropped)
  - Issue Files Token
  - Call Slash API            (fallback URL — still safe via $json._slash_endpoint)

Symptom: real user "joykristyle" (chat_id 5992075757) sent "Hiiii" three times
in succession; each attempt errored at Call Onboarding Endpoint with
`connect ECONNREFUSED ::1:8765` and the user got no response.

Fix: in-place URL substitution localhost:8765 → 172.18.0.1:8765.
Idempotent. Safe re-run.
"""
import json
import psycopg2
import psycopg2.extras

conn = psycopg2.connect("postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
conn.autocommit = False
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
cur.execute('SELECT nodes FROM workflow_entity WHERE id=%s FOR UPDATE', ("vSDQv1vfn6627bnA",))
nodes = cur.fetchone()["nodes"]

OLD = "localhost:8765"
NEW = "172.18.0.1:8765"

patched_nodes = []
for n in nodes:
    params = n.get("parameters", {})
    url = params.get("url", "") or ""
    if OLD in url:
        params["url"] = url.replace(OLD, NEW)
        patched_nodes.append((n["name"], url, params["url"]))

if not patched_nodes:
    print("No matching nodes — already patched or pattern not found.")
    raise SystemExit(0)

cur.execute(
    'UPDATE workflow_entity SET nodes=%s, "updatedAt"=now() WHERE id=%s',
    (json.dumps(nodes), "vSDQv1vfn6627bnA"),
)
conn.commit()

print(f"Patched {len(patched_nodes)} nodes:")
for name, old, new in patched_nodes:
    print(f"  • {name}")
    print(f"      OLD: {old}")
    print(f"      NEW: {new}")
