#!/usr/bin/env python3
"""Deploy 108 — Workflow slash command router.

When Jonathan types /status, /digest, /report <case>, /help in Telegram,
the workflow detects it BEFORE AI Agent and routes to the existing
/api/* endpoints (deploy_093). Skips AI Agent entirely for these
commands (cheap, deterministic, instant).

For /q <text>, the prefix is stripped and the rest flows to AI Agent
normally.

Architecture:
  Telegram Trigger -> Whitelist Check -> If Authorized -> Slash Router
    (Code node decides: handles_inline / pass_through)
  -> If Inline Slash
       TRUE  -> Call Slash API (HTTP) -> end (endpoints DM Jonathan directly)
       FALSE -> Execute a SQL query (original flow)
"""
import json, os, sys, uuid, argparse, time
sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

WF_NAME = "Leos Workflow"

SLASH_ROUTER_JS = r"""// Slash Command Router — deploy_108
// Detects /status, /digest, /report <case>, /help, /q <text>.
// For inline commands (status, digest, report, help): set handles_inline=true.
// For /q: strip the prefix, set message.text, continue to AI Agent.

const msg = $('Telegram Trigger').first().json.message || {};
const text = String(msg.text || msg.caption || '').trim();
const senderId = String(msg.from?.id || '');
const JONATHAN = '6513067717';

let isSlash = false;
let command = null;
let args = '';
let endpoint = null;
let handlesInline = false;
let helpText = null;

if (text.startsWith('/')) {
  isSlash = true;
  const m = text.match(/^\/(\w+)(?:\s+(.*))?$/);
  if (m) {
    command = m[1].toLowerCase();
    args = (m[2] || '').trim();
  }

  // Slash commands restricted to Jonathan (operator)
  if (senderId !== JONATHAN && !['help'].includes(command)) {
    handlesInline = true;
    helpText = "Slash commands are operator-only. If you need information, just ask me directly.";
  } else if (command === 'status') {
    handlesInline = true;
    endpoint = 'http://localhost:8765/api/status?send=1';
  } else if (command === 'digest') {
    handlesInline = true;
    endpoint = 'http://localhost:8765/api/digest?send=1';
  } else if (command === 'report') {
    handlesInline = true;
    const caseArg = args || 'MWK-001';
    endpoint = 'http://localhost:8765/api/report?case=' + encodeURIComponent(caseArg) + '&send=1';
  } else if (command === 'help') {
    handlesInline = true;
    helpText =
      "Slash commands:\n" +
      "  /status            system + cases summary\n" +
      "  /digest            today's daily digest\n" +
      "  /report <case>     case intelligence brief (default MWK-001)\n" +
      "  /q <text>          query mode (just message me directly otherwise)\n" +
      "  /help              this list";
  } else if (command === 'q') {
    // strip prefix, continue to AI Agent
    handlesInline = false;
  } else {
    handlesInline = true;
    helpText = "Unknown slash command. Type /help for available commands.";
  }
}

return [{
  json: {
    ...$('Telegram Trigger').first().json,
    _slash_is_slash: isSlash,
    _slash_command: command,
    _slash_args: args,
    _slash_endpoint: endpoint,
    _slash_handles_inline: handlesInline,
    _slash_help_text: helpText,
  },
}];"""

CALL_SLASH_HTTP_PARAMS = {
    "method": "GET",
    "url": "={{ $json._slash_endpoint || 'http://localhost:8765/api/status?send=0' }}",
    "options": {"timeout": 30000},
}

# When help text exists (not an endpoint), send via Telegram directly
SEND_HELP_TEXT = "={{ $json._slash_help_text }}"


def build_nodes(base_pos):
    x, y = base_pos
    return [
        {
            "id": str(uuid.uuid4()),
            "name": "Slash Router",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [x + 200, y - 100],
            "parameters": {"jsCode": SLASH_ROUTER_JS},
        },
        {
            "id": str(uuid.uuid4()),
            "name": "If Inline Slash",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [x + 400, y - 100],
            "parameters": {
                "options": {},
                "conditions": {
                    "options": {"version": 2, "caseSensitive": True, "typeValidation": "loose"},
                    "combinator": "and",
                    "conditions": [{
                        "id": str(uuid.uuid4()),
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                        "leftValue": "={{ $json._slash_handles_inline }}",
                        "rightValue": "",
                    }],
                },
            },
        },
        {
            "id": str(uuid.uuid4()),
            "name": "If Slash Has Endpoint",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [x + 600, y - 200],
            "parameters": {
                "options": {},
                "conditions": {
                    "options": {"version": 2, "caseSensitive": True, "typeValidation": "loose"},
                    "combinator": "and",
                    "conditions": [{
                        "id": str(uuid.uuid4()),
                        "operator": {"type": "string", "operation": "notEmpty", "singleValue": True},
                        "leftValue": "={{ String($json._slash_endpoint || '') }}",
                        "rightValue": "",
                    }],
                },
            },
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Call Slash API",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [x + 800, y - 250],
            "onError": "continueRegularOutput",
            "parameters": CALL_SLASH_HTTP_PARAMS,
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Send Slash Help",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [x + 800, y - 100],
            "onError": "continueRegularOutput",
            "parameters": {
                "chatId": "={{ $('Telegram Trigger').first().json.message.chat.id }}",
                "text": SEND_HELP_TEXT,
                "additionalFields": {"appendAttribution": False},
            },
            "credentials": {"telegramApi": {"id": "dSI1mdlTrzwdd1B8", "name": "Telegram account"}},
        },
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["staging", "prod"], required=True)
    args = ap.parse_args()
    DSN = dict(host="172.18.0.3", port=5432, dbname="n8n", user="n8n", password="n8npassword") if args.target == "prod" else dict(host="127.0.0.1", port=5433, dbname="n8n", user="n8n", password="n8npassword")
    print(f"  target={args.target}")

    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name=%s", (WF_NAME,))
    wf_id, nodes, conns = cur.fetchone()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_108_{args.target}_{ts}.json"
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

    # Rewire: If Authorized TRUE -> Slash Router (was: -> Execute a SQL query)
    # Then Slash Router -> If Inline Slash:
    #   TRUE -> If Slash Has Endpoint:
    #     TRUE -> Call Slash API (end)
    #     FALSE -> Send Slash Help (end)
    #   FALSE -> Execute a SQL query (continue original flow)
    auth_main = conns.get("If Authorized", {}).get("main", [[], []])
    # auth_main[0] is true branch, auth_main[1] is false
    orig_true = auth_main[0]  # was [{node: "Execute a SQL query", ...}]
    conns["If Authorized"] = {"main": [
        [{"node": "Slash Router", "type": "main", "index": 0}],
        auth_main[1] if len(auth_main) > 1 else [],
    ]}
    conns["Slash Router"] = {"main": [[{"node": "If Inline Slash", "type": "main", "index": 0}]]}
    conns["If Inline Slash"] = {"main": [
        [{"node": "If Slash Has Endpoint", "type": "main", "index": 0}],  # true: inline
        orig_true,  # false: pass through to original Execute a SQL query
    ]}
    conns["If Slash Has Endpoint"] = {"main": [
        [{"node": "Call Slash API", "type": "main", "index": 0}],   # true: endpoint
        [{"node": "Send Slash Help", "type": "main", "index": 0}],  # false: help text
    ]}
    print("  ✓ wired: If Authorized -> Slash Router -> If Inline Slash -> [API call | help text | passthrough]")

    cur.close(); conn.close()
    if args.target == "prod":
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes, connections=conns)
    else:
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute('UPDATE workflow_entity SET nodes=%s::jsonb, connections=%s::jsonb, "updatedAt"=now() WHERE id=%s', (json.dumps(nodes), json.dumps(conns), wf_id))
        cur.execute("""UPDATE workflow_history SET nodes=%s::json, connections=%s::json WHERE "workflowId"=%s AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""", (json.dumps(nodes), json.dumps(conns), wf_id, wf_id))
        cur.execute('UPDATE workflow_entity SET active=false WHERE id=%s', (wf_id,))
        conn.commit(); time.sleep(2)
        cur.execute('UPDATE workflow_entity SET active=true WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()
        print("  ✓ staging done")


if __name__ == "__main__":
    main()
