#!/usr/bin/env python3
"""apply_deploy_364_sim_guard_syntax_fix.py — repair seven Telegram send-node
chatId expressions broken by the deploy_300 sim-guard wrap.

The sim-guard pattern from deploy_300 was supposed to wrap each chatId
expression so sim senders (999000xxx) get routed to chat_id=0 (which
returns chat-not-found and prevents leakage to real recipients). The wrap
was applied with a bad regex that produced expressions like:

  ={{ ... ? "0" : ({ $('Parse Agent1').first().json.chatId) }}

The `({ ` opens an object literal that is never closed, and the trailing
`)` is unmatched. Result: every dynamic-target send node throws
"invalid syntax" at runtime. The bug stayed hidden because:

  - "Reply to Jonathan" uses hardcoded "6513067717", no expression to break
  - sim leakage tests only verified that real chats were NOT hit
  - real users only noticed when Leo stopped replying in the group

Nodes broken (seven):
  - Reply to Client
  - Send to Target Contact
  - Send Files Link to Recipient
  - Send Slash Help
  - Send Onboarding Reply
  - Ask Clarification (a different malformation: nested template string)

This migration replaces each broken chatId with the corrected expression,
preserving the sim-guard semantics. Snapshot taken first.

Idempotent: re-running on already-fixed expressions is a no-op (the regex
matches only the broken pattern).
"""
from __future__ import annotations
import json
import os
import re
import sys
from copy import deepcopy

import psycopg2

PG_DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"

# Fixed chatId expressions per node. Each preserves the sim-guard semantics
# (sender starts with "999" -> chatId="0") but uses correct JS syntax.
FIXES = {
    "Reply to Client":
        '={{ String($("Telegram Trigger").first().json.message.from.id || "").startsWith("999") ? "0" : ($("Parse Agent1").first().json.chatId || $("Telegram Trigger").first().json.message.chat.id) }}',
    "Send to Target Contact":
        '={{ String($("Telegram Trigger").first().json.message.from.id || "").startsWith("999") ? "0" : $("Safe Reply").first().json.target_chat_id }}',
    "Send Files Link to Recipient":
        '={{ String($("Telegram Trigger").first().json.message.from.id || "").startsWith("999") ? "0" : $("Issue Files Token").first().json.telegram_id }}',
    "Send Slash Help":
        '={{ String($("Telegram Trigger").first().json.message.from.id || "").startsWith("999") ? "0" : $("Telegram Trigger").first().json.message.chat.id }}',
    "Send Onboarding Reply":
        '={{ String($("Telegram Trigger").first().json.message.from.id || "").startsWith("999") ? "0" : $("Telegram Trigger").first().json.message.chat.id }}',
    "Ask Clarification":
        '={{ String($("Telegram Trigger").first().json.message.from.id || "").startsWith("999") ? "0" : ($("Parse Agent1").first().json.chatId || $("Telegram Trigger").first().json.message.chat.id) }}',
}


def main():
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    cur = conn.cursor()

    print(f"[deploy_364] loading workflow {WORKFLOW_ID} ...")
    cur.execute("SELECT nodes, connections FROM workflow_entity WHERE id = %s",
                (WORKFLOW_ID,))
    row = cur.fetchone()
    if not row:
        print("FATAL: workflow not found", file=sys.stderr)
        sys.exit(2)
    nodes_raw, conns_raw = row
    nodes = json.loads(nodes_raw) if isinstance(nodes_raw, str) else nodes_raw
    conns_json = (conns_raw if isinstance(conns_raw, str) else json.dumps(conns_raw))
    nodes = deepcopy(nodes)

    cur.execute("""
        INSERT INTO leo_workflow_snapshots
            (workflow_id, reason, nodes_json, connections_json)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """, (WORKFLOW_ID, "pre-deploy_364 sim-guard syntax fix",
          json.dumps(nodes), conns_json))
    snap_id = cur.fetchone()[0]
    print(f"  snapshot id: {snap_id}")

    changed = 0
    untouched = []
    for i, n in enumerate(nodes):
        name = n.get("name")
        if name not in FIXES:
            continue
        old = n.get("parameters", {}).get("chatId", "")
        new = FIXES[name]
        if old == new:
            untouched.append(name)
            continue
        # Confirm we're replacing the broken pattern
        broken_marker = "({ $(" if "({ $(" in old else (' : ("=' if ' : ("=' in old else None)
        if broken_marker is None:
            print(f"  ⚠ {name}: chatId doesn't match broken pattern — skipping for safety")
            print(f"      current: {old[:200]}")
            untouched.append(name)
            continue
        n.setdefault("parameters", {})["chatId"] = new
        nodes[i] = n
        changed += 1
        print(f"  ✓ {name}: fixed")

    if changed == 0:
        print("[deploy_364] nothing to change — already fixed or no broken pattern matched")
    else:
        cur.execute("""
            UPDATE workflow_entity
               SET nodes = %s, "updatedAt" = NOW()
             WHERE id = %s
        """, (json.dumps(nodes), WORKFLOW_ID))
        print(f"[deploy_364] wrote {changed} fixed chatId expressions to workflow")
    if untouched:
        print(f"[deploy_364] untouched: {untouched}")

    cur.close()
    conn.close()
    print(f"[deploy_364] DONE — snapshot {snap_id} for rollback")


if __name__ == "__main__":
    main()
