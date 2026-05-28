#!/usr/bin/env python3
"""Append Rules G/H/I (filing assistant + context-blindness + imperative recognition)
to the AI Agent system message."""
import json
import psycopg2
import psycopg2.extras

WORKFLOW_ID = "vSDQv1vfn6627bnA"

addendum = open("/tmp/rule_g.txt").read()

conn = psycopg2.connect("postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
conn.autocommit = False
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
cur.execute("SELECT nodes FROM workflow_entity WHERE id=%s FOR UPDATE", (WORKFLOW_ID,))
nodes = cur.fetchone()["nodes"]

patched = False
for n in nodes:
    if n.get("name") == "AI Agent":
        opts = n.setdefault("parameters", {}).setdefault("options", {})
        current = opts.get("systemMessage", "")
        # Idempotency: don't append if Rule G already there
        if "## FILING ASSISTANT INTERACTION (Rule G" in current:
            print("Already patched — Rule G already present in system message.")
            raise SystemExit(0)
        opts["systemMessage"] = current.rstrip() + "\n\n" + addendum.lstrip()
        patched = True
        print(f"Patched. Old length: {len(current)}  New length: {len(opts['systemMessage'])}")
        break

if not patched:
    print("AI Agent node not found")
    raise SystemExit(1)

cur.execute(
    'UPDATE workflow_entity SET nodes=%s, "updatedAt"=now() WHERE id=%s',
    (json.dumps(nodes), WORKFLOW_ID),
)
conn.commit()
print("DB UPDATED")
