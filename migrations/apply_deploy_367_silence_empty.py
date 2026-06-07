#!/usr/bin/env python3
"""apply_deploy_367_silence_empty.py — Rule N: don't reply to blank triggers.

Issue 2026-06-07: Leo replied "Standing by. No message content detected"
to Telegram system events (members added/removed, chat title changes,
etc.) — execs 2268-2271. Pollutes the DB group channel with noise.

Rule N appended to systemMessage: when inbound text+caption are both
empty, set telegram_reply_to_client to empty string. Safe Reply skips
empty bodies.

Already applied live at ~03:46 UTC (snapshot 1690). This file is the
durable record. Idempotent.
"""
from __future__ import annotations
import json, os, sys
import psycopg2

PG_DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"
RULE_START = "## Rule N — Silence on empty messages (deploy_367)"
RULE_END = "## END Rule N"
RULE = f"""{RULE_START}

If the inbound message has NO text and NO caption (it is a Telegram system
event: a member added/removed, chat title change, pinned message, photo
without caption you can't read, etc.), DO NOT REPLY. Set
telegram_reply_to_client to "" (empty string) and telegram_summary_for_jonathan
to "" as well. The Safe Reply node won't send when the body is empty.

Never reply with "Standing by", "No message content detected", or any
acknowledgment to a blank trigger. It pollutes the group channel.

{RULE_END}
"""


def main():
    conn = psycopg2.connect(PG_DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT nodes, connections FROM workflow_entity WHERE id = %s",
                (WORKFLOW_ID,))
    nodes_raw, conns_raw = cur.fetchone()
    nodes = json.loads(nodes_raw) if isinstance(nodes_raw, str) else nodes_raw
    conns_json = conns_raw if isinstance(conns_raw, str) else json.dumps(conns_raw)
    cur.execute("""
        INSERT INTO leo_workflow_snapshots (workflow_id, reason, nodes_json, connections_json)
        VALUES (%s,%s,%s,%s) RETURNING id
    """, (WORKFLOW_ID, "pre-deploy_367 silence empty", json.dumps(nodes), conns_json))
    print(f"snapshot: {cur.fetchone()[0]}")
    for i, n in enumerate(nodes):
        if n.get("type") == "@n8n/n8n-nodes-langchain.agent":
            sm = n["parameters"]["options"]["systemMessage"]
            if RULE_START in sm and RULE_END in sm:
                s = sm.index(RULE_START); e = sm.index(RULE_END) + len(RULE_END)
                new_sm = sm[:s] + RULE.strip() + sm[e:]
            else:
                new_sm = sm.rstrip() + "\n\n" + RULE.strip() + "\n"
            nodes[i]["parameters"]["options"]["systemMessage"] = new_sm
            print(f"Rule N applied  delta={len(new_sm)-len(sm):+d}  total={len(new_sm)}")
            break
    cur.execute('UPDATE workflow_entity SET nodes = %s, "updatedAt"=NOW() WHERE id = %s',
                (json.dumps(nodes), WORKFLOW_ID))
    print("done")


if __name__ == "__main__":
    main()
