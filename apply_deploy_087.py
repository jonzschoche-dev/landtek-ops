#!/usr/bin/env python3
"""Deploy 087 — Leo issues file-access tokens via natural language.

Per deploy_086 + Jonathan's directive: clients should access their files
on-demand. This wires the existing /api/issue_files_token endpoint into
Leo's behavior.

Triggers:
  Client says: "show me my files" / "send me my documents" / "where can
               I see what's been uploaded" / "give me my dashboard"
    -> Leo emits issue_files_token: {telegram_id: <sender's id>}
    -> Workflow issues 1-hour token, Telegram DMs the sender the URL.

  Jonathan says: "send Don Qi his files" / "give Don Qi his dashboard link" /
                 "let Allan see his documents"
    -> Leo resolves target via Rule C directory + emits
       issue_files_token: {telegram_id: <target's id>}
    -> Workflow issues + DMs the TARGET CLIENT (with auth identity)
    -> Jonathan gets a confirmation in telegram_summary_for_jonathan

Implementation:
  - 1 new JSON schema field: issue_files_token
  - 1 new IF node "If Files Token Requested"
  - 1 new HTTP Request node "Issue Files Token" (POSTs to leo-tools)
  - 1 new Telegram node "Send Files Link to Recipient"
  - Prompt addition documenting the new flow
"""
import json
import os
import sys
import uuid
import argparse
import time

sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

WF_NAME = "Leos Workflow"
TELEGRAM_CRED = {"id": "dSI1mdlTrzwdd1B8", "name": "Telegram account"}

_FOLDER_EMOJI = "\U0001F4C2"  # 📂
LINK_MSG_BODY = (
    "={{ `" + _FOLDER_EMOJI + " Your files dashboard\n\n"
    "${$('Issue Files Token').first().json.client_name} - ${$('Issue Files Token').first().json.case_file}\n"
    "Valid 1 hour from now.\n\n"
    "${$('Issue Files Token').first().json.url}` }}"
)


def build_new_nodes(base_pos):
    x, y = base_pos
    return [
        {
            "id": str(uuid.uuid4()),
            "name": "If Files Token Requested",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [x + 800, y + 600],
            "parameters": {
                "options": {},
                "conditions": {
                    "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "loose"},
                    "combinator": "and",
                    "conditions": [{
                        "id": str(uuid.uuid4()),
                        "operator": {"type": "string", "operation": "notEmpty", "singleValue": True},
                        "leftValue": "={{ String(($json.issue_files_token || {}).telegram_id || '') }}",
                        "rightValue": "",
                    }],
                },
            },
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Issue Files Token",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [x + 1000, y + 600],
            "onError": "continueRegularOutput",
            "parameters": {
                "method": "POST",
                "url": "http://localhost:8765/api/issue_files_token",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({telegram_id: String($json.issue_files_token.telegram_id), ttl_hours: Number($json.issue_files_token.ttl_hours || 1), issued_by: $json.senderId }) }}",
                "options": {"timeout": 10000},
            },
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Send Files Link to Recipient",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [x + 1200, y + 600],
            "onError": "continueRegularOutput",
            "parameters": {
                "chatId": "={{ $('Issue Files Token').first().json.telegram_id }}",
                "text": LINK_MSG_BODY,
                "additionalFields": {"appendAttribution": False},
            },
            "credentials": {"telegramApi": TELEGRAM_CRED},
        },
    ]


# ── Prompt additions ──────────────────────────────────────────────────────
SCHEMA_ANCHOR = '"entities_to_register": ['

SCHEMA_ADDITION = '''"issue_files_token": {"telegram_id": "", "ttl_hours": 1},
  '''

RULE_ANCHOR = "### Entity capture per turn (added 2026-05-16 — deploy_082)"

RULE_ADDITION = """### File dashboard link on demand (added 2026-05-16 — deploy_087)

When ANY sender asks to see/access/retrieve their own files, OR when Jonathan instructs you to send another client their files:

**Detect these intents:**
  Client (self) — "show me my files", "where can I see my documents", "send me my dashboard", "give me the link to my files", "list everything you have for me"
  Jonathan (for someone else) — "send Don Qi his files", "give Allan his dashboard link", "let <client> see his documents"

**Action:**
1. Resolve the target's telegram_id:
   - For self-request: use `$json.senderId` (the current sender)
   - For Jonathan's instruction: resolve via Rule C directory (Heirs of MWK = 8575986732, Allan / Paracale-001 = not yet recorded)
2. Emit `issue_files_token: {telegram_id: "<resolved id>", ttl_hours: 1}` in your JSON output.
3. Reply briefly:
   - Self: "Generating your files link — should land in a moment."
   - Jonathan: "Sending <client>'s files link to him now. He'll have it in seconds."
4. The workflow will POST to the issue-token endpoint and DM the target the URL automatically.

**Inviolable:**
  - Never include a fake URL in your reply. The real URL is generated by the workflow AFTER you respond.
  - Never set `issue_files_token.telegram_id` to a value not in Rule C's directory unless it's the current sender (self-request). For unrecorded clients (Datu Shishir today), refuse and tell Jonathan to record the telegram_id first.
  - This is the ONLY exception to Rule E's "you can't send things you don't have" — because the workflow handles the actual issue + send.
"""


def patch_prompt(node):
    p = node["parameters"]["options"]["systemMessage"]
    changed = False
    if "issue_files_token" not in p:
        if SCHEMA_ANCHOR not in p:
            raise ValueError("Schema anchor (entities_to_register) not found in prompt")
        p = p.replace(SCHEMA_ANCHOR, SCHEMA_ADDITION + SCHEMA_ANCHOR)
        changed = True
    if "File dashboard link on demand (added 2026-05-16 — deploy_087)" not in p:
        if RULE_ANCHOR not in p:
            raise ValueError("Rule anchor (entity capture) not found in prompt")
        p = p.replace(RULE_ANCHOR, RULE_ADDITION + "\n\n" + RULE_ANCHOR)
        changed = True
    node["parameters"]["options"]["systemMessage"] = p
    return changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["staging", "prod"], required=True)
    args = parser.parse_args()
    if args.target == "staging":
        DSN = dict(host="127.0.0.1", port=5433, dbname="n8n", user="n8n", password="n8npassword")
    else:
        DSN = dict(host="172.18.0.3", port=5432, dbname="n8n", user="n8n", password="n8npassword")
    print(f"  target={args.target}")

    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name=%s", (WF_NAME,))
    wf_id, nodes, conns = cur.fetchone()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_087_{args.target}_{ts}.json"
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes, "connections": conns}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    pa = next((n for n in nodes if n["name"] == "Parse Agent1"), None)
    base_pos = pa.get("position", [400, 0])

    existing = {n["name"] for n in nodes}
    to_add = [n for n in build_new_nodes(base_pos) if n["name"] not in existing]
    nodes.extend(to_add)
    print(f"  ✓ added {len(to_add)} nodes")

    # Wire: Parse Agent1 -> If Files Token Requested (fan-out)
    pa_main = conns.get("Parse Agent1", {}).get("main", [[]])
    if not any(t.get("node") == "If Files Token Requested" for t in pa_main[0]):
        pa_main[0].append({"node": "If Files Token Requested", "type": "main", "index": 0})
    conns["Parse Agent1"] = {"main": pa_main}
    # IF true -> Issue Files Token -> Send Files Link
    conns["If Files Token Requested"] = {"main": [
        [{"node": "Issue Files Token", "type": "main", "index": 0}],
        [],
    ]}
    conns["Issue Files Token"] = {"main": [
        [{"node": "Send Files Link to Recipient", "type": "main", "index": 0}],
    ]}
    print("  ✓ wired Parse Agent1 -> IF -> HTTP -> Telegram send")

    aia = next((n for n in nodes if n["name"] == "AI Agent"), None)
    if aia and patch_prompt(aia):
        print("  ✓ AI Agent prompt: schema + Rule for file dashboard link")
    else:
        print("  ⚠ Prompt already patched")

    cur.close(); conn.close()

    if args.target == "staging":
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute('UPDATE workflow_entity SET nodes=%s::jsonb, connections=%s::jsonb, "updatedAt"=now() WHERE id=%s',
                    (json.dumps(nodes), json.dumps(conns), wf_id))
        cur.execute("""UPDATE workflow_history SET nodes=%s::json, connections=%s::json
                         WHERE "workflowId"=%s
                           AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""",
                    (json.dumps(nodes), json.dumps(conns), wf_id, wf_id))
        cur.execute('UPDATE workflow_entity SET active=false, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); time.sleep(2)
        cur.execute('UPDATE workflow_entity SET active=true, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()
        print("  ✓ staging done")
    else:
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes, connections=conns)


if __name__ == "__main__":
    main()
