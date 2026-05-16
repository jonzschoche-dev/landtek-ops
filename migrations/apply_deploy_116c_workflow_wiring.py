#!/usr/bin/env python3
"""Deploy 116-C — Wire onboarding into the n8n workflow.

When Whitelist Check fails (sender is not in TG_AUTHORIZED_USERS), instead
of silent rejection, route through Call Onboarding Endpoint → Send Onboarding
Reply. The /api/onboard endpoint handles the state machine and DMs Jonathan
for new escalations.

After this deploy:
  - Datu's first msg → Leo greets him + asks who he is
  - Datu's intro → Leo asks classify question
  - Datu's details → Leo escalates to Jonathan (DM)
  - Jonathan runs /approve <id> <role> → Leo confirms to Datu

Existing approved users (operators) still flow normally through the
Whitelist Check.
"""
import json, sys, time, uuid, argparse
sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

WF_NAME = "Leos Workflow"


def build_nodes(base_pos):
    x, y = base_pos
    return [
        {
            "id": str(uuid.uuid4()),
            "name": "Call Onboarding Endpoint",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [x + 700, y + 250],
            "onError": "continueRegularOutput",
            "parameters": {
                "method": "POST",
                "url": "http://localhost:8765/api/onboard",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({"
                            "channel: 'telegram', "
                            "channel_user_id: $('Telegram Trigger').first().json.message.from.id, "
                            "display_name: ($('Telegram Trigger').first().json.message.from.first_name || '') + "
                            "  (($('Telegram Trigger').first().json.message.from.last_name) ? "
                            "    (' ' + $('Telegram Trigger').first().json.message.from.last_name) : ''), "
                            "username: $('Telegram Trigger').first().json.message.from.username || '', "
                            "message: $('Telegram Trigger').first().json.message.text || "
                            "  $('Telegram Trigger').first().json.message.caption || ''"
                            "}) }}",
                "options": {"timeout": 30000},
            },
        },
        {
            "id": str(uuid.uuid4()),
            "name": "If Onboarding Reply",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [x + 900, y + 250],
            "parameters": {
                "options": {},
                "conditions": {
                    "options": {"version": 2, "caseSensitive": True, "typeValidation": "loose"},
                    "combinator": "and",
                    "conditions": [{
                        "id": str(uuid.uuid4()),
                        "operator": {"type": "string", "operation": "notEmpty", "singleValue": True},
                        "leftValue": "={{ $json.reply || '' }}",
                        "rightValue": "",
                    }],
                },
            },
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Send Onboarding Reply",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [x + 1100, y + 200],
            "onError": "continueRegularOutput",
            "parameters": {
                "chatId": "={{ $('Telegram Trigger').first().json.message.chat.id }}",
                "text": "={{ $json.reply }}",
                "additionalFields": {"appendAttribution": False, "parse_mode": "HTML"},
            },
            "credentials": {"telegramApi": {"id": "dSI1mdlTrzwdd1B8", "name": "Telegram account"}},
        },
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["staging", "prod"], default="prod")
    args = ap.parse_args()
    DSN = dict(host="172.18.0.3", port=5432, dbname="n8n", user="n8n", password="n8npassword") \
        if args.target == "prod" else \
        dict(host="127.0.0.1", port=5433, dbname="n8n", user="n8n", password="n8npassword")

    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name=%s", (WF_NAME,))
    wf_id, nodes, conns = cur.fetchone()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_116c_{args.target}_{ts}.json"
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes, "connections": conns}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    ifa = next((n for n in nodes if n["name"] == "If Authorized"), None)
    if not ifa:
        sys.exit("FATAL: If Authorized node not found")
    base_pos = ifa.get("position", [400, 0])

    existing = {n["name"] for n in nodes}
    to_add = [n for n in build_nodes(base_pos) if n["name"] not in existing]
    nodes.extend(to_add)
    print(f"  ✓ added {len(to_add)} nodes")

    # Save the existing If Authorized=FALSE branch (was: Log Unauth Attempt)
    auth_main = conns.get("If Authorized", {}).get("main", [[], []])
    existing_false_branch = auth_main[1] if len(auth_main) > 1 else []

    # Rewire: If Authorized FALSE → Call Onboarding Endpoint (in addition to existing log path)
    # We keep the audit log AND route to onboarding by inserting Call Onboarding alongside
    conns["If Authorized"] = {"main": [
        auth_main[0] if auth_main else [],  # true branch unchanged
        existing_false_branch + [{"node": "Call Onboarding Endpoint", "type": "main", "index": 0}],
    ]}

    conns["Call Onboarding Endpoint"] = {"main": [[
        {"node": "If Onboarding Reply", "type": "main", "index": 0}
    ]]}
    conns["If Onboarding Reply"] = {"main": [
        [{"node": "Send Onboarding Reply", "type": "main", "index": 0}],  # true: has reply
        [],  # false: passthrough or no reply — terminate
    ]}
    print("  ✓ wired: If Authorized=FALSE → (existing log) + Call Onboarding → Send Onboarding Reply")

    cur.close(); conn.close()
    if args.target == "prod":
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes, connections=conns)
    else:
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute('UPDATE workflow_entity SET nodes=%s::jsonb, "updatedAt"=now() WHERE id=%s',
                    (json.dumps(nodes), wf_id))
        cur.execute('UPDATE workflow_entity SET active=false WHERE id=%s', (wf_id,))
        conn.commit(); time.sleep(2)
        cur.execute('UPDATE workflow_entity SET active=true WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()


if __name__ == "__main__":
    main()
