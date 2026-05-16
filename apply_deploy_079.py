#!/usr/bin/env python3
"""Deploy 079 — Persist email/phone/username from client messages.

Today's incident (9:06 AM Manila):
  Don Qi gave email at 8:50: "jonzschoche@gmail.com"
  Leo correctly summarized DOC 623 at 9:06 but asked AGAIN for email
  because clientRow.email is "" in DB. The 'email_update' field that
  AI emits never gets written to clients.email — pure data loss.

Per feedback_information_is_gold: every piece of data Leo receives
must be captured and reusable. The current pipeline loses client-
stated emails, phones, and usernames every turn.

Fix: 3 new workflow nodes off Parse Agent1's fan-out:
  - If Has Email Update -> Save Email To Client (Postgres UPDATE)
  - If Has Phone Update -> Save Phone To Client (Postgres UPDATE)
  - If Has Username Update -> Save Username To Client (Postgres UPDATE)
Each updates clients WHERE telegram_id = senderId.

Also prompt addition (Rule B subsection): when recent_conversations
shows a client previously stated their email/phone/anything, USE IT
— don't ask again unless you have a specific reason to doubt.
"""
import json
import os
import sys
import argparse
import time
import uuid

sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

WF_NAME = "Leos Workflow"
POSTGRES_CRED = {"id": "kPUGFA1HrZZFWnzI", "name": "Postgres account 2"}

# Prompt addition: don't re-ask info already given
RULE_DONTREASK_MARKER = "**Before asking any follow-up, scan the client's current message for the answer.**"

RULE_DONTREASK_ADDITION = """ ALSO scan `RECENT CONVERSATION HISTORY` for previously-stated facts before asking. The client's email, phone number, names of associated people, dates, and similar facts persist across turns. If they told you "jonzschoche@gmail.com" three turns ago, DO NOT ask "what's your email?" again — just use it. Acknowledge with "I have <fact> from our earlier exchange — using that."
"""


def build_save_nodes(base_pos):
    x, y = base_pos
    return [
        # ── EMAIL ─────────────────────────────────────────────────────────
        {
            "id": str(uuid.uuid4()),
            "name": "If Has Email Update",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [x, y],
            "parameters": {
                "options": {},
                "conditions": {
                    "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "loose"},
                    "combinator": "and",
                    "conditions": [{
                        "id": str(uuid.uuid4()),
                        "operator": {"type": "string", "operation": "regex", "singleValue": True},
                        "leftValue": "={{ String($json.email_update || '') }}",
                        "rightValue": "[^@]+@[^@]+\\.[^@]+",
                    }],
                },
            },
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Save Email To Client",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.6,
            "position": [x + 200, y],
            "onError": "continueRegularOutput",
            "parameters": {
                "operation": "executeQuery",
                "query": "UPDATE clients SET email = '{{ $json.email_update }}'::text, updated_at = now() WHERE telegram_id = '{{ $json.senderId }}'::varchar RETURNING id, telegram_id, email;",
                "options": {},
            },
            "credentials": {"postgres": POSTGRES_CRED},
        },
        # ── PHONE ─────────────────────────────────────────────────────────
        {
            "id": str(uuid.uuid4()),
            "name": "If Has Phone Update",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [x, y + 200],
            "parameters": {
                "options": {},
                "conditions": {
                    "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "loose"},
                    "combinator": "and",
                    "conditions": [{
                        "id": str(uuid.uuid4()),
                        "operator": {"type": "string", "operation": "notEmpty", "singleValue": True},
                        "leftValue": "={{ String($json.phone_update || '').trim() }}",
                        "rightValue": "",
                    }],
                },
            },
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Save Phone To Client",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.6,
            "position": [x + 200, y + 200],
            "onError": "continueRegularOutput",
            "parameters": {
                "operation": "executeQuery",
                "query": "UPDATE clients SET phone = '{{ $json.phone_update }}'::text, updated_at = now() WHERE telegram_id = '{{ $json.senderId }}'::varchar RETURNING id, telegram_id, phone;",
                "options": {},
            },
            "credentials": {"postgres": POSTGRES_CRED},
        },
        # ── USERNAME ──────────────────────────────────────────────────────
        {
            "id": str(uuid.uuid4()),
            "name": "If Has Username Update",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [x, y + 400],
            "parameters": {
                "options": {},
                "conditions": {
                    "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "loose"},
                    "combinator": "and",
                    "conditions": [{
                        "id": str(uuid.uuid4()),
                        "operator": {"type": "string", "operation": "notEmpty", "singleValue": True},
                        "leftValue": "={{ String($json.telegram_username_update || '').trim() }}",
                        "rightValue": "",
                    }],
                },
            },
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Save Username To Client",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.6,
            "position": [x + 200, y + 400],
            "onError": "continueRegularOutput",
            "parameters": {
                "operation": "executeQuery",
                "query": "UPDATE clients SET telegram_username = '{{ $json.telegram_username_update }}'::text, updated_at = now() WHERE telegram_id = '{{ $json.senderId }}'::varchar RETURNING id, telegram_id, telegram_username;",
                "options": {},
            },
            "credentials": {"postgres": POSTGRES_CRED},
        },
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["staging", "prod"], required=True)
    args = parser.parse_args()
    if args.target == "staging":
        DSN = dict(host="127.0.0.1", port=5433, dbname="n8n", user="n8n", password="n8npassword")
    else:
        DSN = dict(host="172.18.0.3", port=5432, dbname="n8n", user="n8n", password="n8npassword")
    print(f"  target={args.target}  dsn={DSN['host']}:{DSN['port']}")

    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name=%s", (WF_NAME,))
    wf_id, nodes, conns = cur.fetchone()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_079_{args.target}_{ts}.json"
    os.makedirs("/root/landtek/snapshots", exist_ok=True)
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes, "connections": conns}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    # Locate Parse Agent1 to derive node positions
    pa = next((n for n in nodes if n["name"] == "Parse Agent1"), None)
    if not pa:
        sys.exit("FATAL: Parse Agent1 not found")
    base_pos = pa.get("position", [400, 0])

    # Add 6 new nodes (3 IF + 3 Postgres UPDATE) — idempotent
    new_names = ["If Has Email Update", "Save Email To Client",
                 "If Has Phone Update", "Save Phone To Client",
                 "If Has Username Update", "Save Username To Client"]
    existing = {n["name"] for n in nodes}
    to_add = [n for n in build_save_nodes([base_pos[0] + 1500, base_pos[1] + 600]) if n["name"] not in existing]
    nodes.extend(to_add)
    print(f"  ✓ added {len(to_add)} nodes: {[n['name'] for n in to_add]}")

    # Wire: Parse Agent1 → 3 IF nodes (fan-out additions)
    pa_main = conns.get("Parse Agent1", {}).get("main", [[]])
    dst_names = {t["node"] for t in pa_main[0]}
    for if_name in ["If Has Email Update", "If Has Phone Update", "If Has Username Update"]:
        if if_name not in dst_names:
            pa_main[0].append({"node": if_name, "type": "main", "index": 0})
    conns["Parse Agent1"] = {"main": pa_main}

    # Wire: each IF true → matching Save Postgres node
    for if_name, save_name in [
        ("If Has Email Update", "Save Email To Client"),
        ("If Has Phone Update", "Save Phone To Client"),
        ("If Has Username Update", "Save Username To Client"),
    ]:
        conns[if_name] = {"main": [
            [{"node": save_name, "type": "main", "index": 0}],
            [],
        ]}
    print(f"  ✓ wired fan-outs from Parse Agent1 + IF→Save edges")

    # Prompt addition — don't re-ask info already given in conversation history
    aia = next((n for n in nodes if n["name"] == "AI Agent"), None)
    if aia:
        p = aia["parameters"]["options"]["systemMessage"]
        if "ALSO scan `RECENT CONVERSATION HISTORY` for previously-stated" not in p:
            if RULE_DONTREASK_MARKER in p:
                p = p.replace(RULE_DONTREASK_MARKER, RULE_DONTREASK_MARKER + RULE_DONTREASK_ADDITION)
                aia["parameters"]["options"]["systemMessage"] = p
                print("  ✓ AI Agent prompt: 'don't re-ask facts already given' added")
            else:
                print("  ⚠ RULE_DONTREASK_MARKER not found — skipping prompt addition")
        else:
            print("  ⚠ AI Agent prompt: already patched")

    cur.close(); conn.close()

    if args.target == "staging":
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute(
            'UPDATE workflow_entity SET nodes=%s::jsonb, connections=%s::jsonb, "updatedAt"=now() WHERE id=%s',
            (json.dumps(nodes), json.dumps(conns), wf_id))
        cur.execute("""UPDATE workflow_history SET nodes=%s::json, connections=%s::json
                         WHERE "workflowId"=%s
                           AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""",
                    (json.dumps(nodes), json.dumps(conns), wf_id, wf_id))
        cur.execute('UPDATE workflow_entity SET active=false, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); time.sleep(2)
        cur.execute('UPDATE workflow_entity SET active=true, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()
        print("  ✓ staging updated + reactivated")
    else:
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes, connections=conns)
        # Backfill Don Qi's email RIGHT NOW from the chat note that captured it
        conn = psycopg2.connect(**DSN); conn.autocommit = True
        cur = conn.cursor()
        cur.execute("""
            UPDATE clients
               SET email = 'jonzschoche@gmail.com',
                   updated_at = now()
             WHERE case_file = 'MWK-001' AND telegram_id = '8575986732' AND (email IS NULL OR email = '')
             RETURNING id, name, email;
        """)
        row = cur.fetchone()
        if row:
            print(f"  ✓ backfilled email for {row[1]}: {row[2]}")
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
