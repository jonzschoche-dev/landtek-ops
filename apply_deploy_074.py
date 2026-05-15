#!/usr/bin/env python3
"""Deploy 074 — Back-channel context injection (Rule F).

Lets Jonathan pre-load context for a specific client's NEXT message:

  Jonathan: "When Allan asks about the receipt, tell him it was processed Friday."
  Leo: "Noted. Next time Allan messages, I'll mention that."

  [hours later]
  Allan: "Hey did you get my receipt?"
  Leo: "Yes — it was processed Friday. Anything else I can confirm?"

  Leo (DM to Jonathan): "Used your context on Allan: 'it was processed Friday'"

Architecture:
  - Table: pending_context (target_telegram_id, context_text, used_at, ...)
  - Input path:   Fetch Pending Inquiries → Fetch Pending Context → Context Builder
                  Context Builder JS reads $('Fetch Pending Context').all()
                  and injects into agentInput as "## CONTEXT FROM OPERATOR"
  - Output path:  Parse Agent1 fans out to:
                    - If Has Context To Save  → Save Pending Context
                    - If Context Was Used     → Mark Context Used → Confirm to Jonathan
  - Prompt:       Rule F added; JSON schema gains pending_context_to_save + context_used

Safe-deploy: --target=staging for full validation cycle; --target=prod after green.
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
POSTGRES_CRED = {"id": "kPUGFA1HrZZFWnzI", "name": "Postgres account 2"}
TELEGRAM_CRED = {"id": "dSI1mdlTrzwdd1B8", "name": "Telegram account"}
JONATHAN_CHAT_ID = "6513067717"

# ── DDL ───────────────────────────────────────────────────────────────────
PENDING_CONTEXT_DDL = """
CREATE TABLE IF NOT EXISTS pending_context (
    id SERIAL PRIMARY KEY,
    target_telegram_id VARCHAR(50) NOT NULL,
    target_client_name TEXT,
    context_text TEXT NOT NULL,
    given_by VARCHAR(50) NOT NULL DEFAULT '6513067717',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    used_at TIMESTAMP WITH TIME ZONE,
    used_in_reply TEXT
);
CREATE INDEX IF NOT EXISTS idx_pending_context_target_unused
    ON pending_context(target_telegram_id) WHERE used_at IS NULL;
"""

# ── SQL for new Postgres nodes ────────────────────────────────────────────
FETCH_CONTEXT_SQL = """(SELECT id, target_telegram_id, target_client_name, context_text, created_at::text AS created_at
  FROM pending_context
 WHERE target_telegram_id = '{{ $('Telegram Trigger').first().json.message.from.id }}'::text
   AND used_at IS NULL
 ORDER BY created_at ASC
 LIMIT 5)
UNION ALL SELECT NULL::int, NULL::text, NULL::text, NULL::text, NULL::text;"""

SAVE_CONTEXT_SQL = """INSERT INTO pending_context (target_telegram_id, target_client_name, context_text)
VALUES (
  '{{ $json.pending_context_to_save.target_telegram_id }}'::text,
  NULLIF('{{ $json.pending_context_to_save.target_client_name }}', '')::text,
  '{{ $json.pending_context_to_save.context_text }}'::text
) RETURNING id;"""

MARK_USED_SQL = """UPDATE pending_context
   SET used_at = now(),
       used_in_reply = '{{ $json.context_used.wording }}'::text
 WHERE id = {{ $json.context_used.context_id }}
 RETURNING id, target_telegram_id, context_text;"""

CONFIRM_TEXT = """✓ Used your context on {{ $json.target_telegram_id }}.

Context: "{{ $json.context_text }}"
Wording I used: "{{ $('Parse Agent1').first().json.context_used.wording }}"

Row marked used. New row needed for next inject."""

# ── New nodes ─────────────────────────────────────────────────────────────
def build_new_nodes(base_pos):
    x, y = base_pos
    return [
        {
            "id": str(uuid.uuid4()),
            "name": "Fetch Pending Context",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.6,
            "position": [x, y + 100],
            "parameters": {
                "query": FETCH_CONTEXT_SQL,
                "options": {},
                "operation": "executeQuery",
            },
            "credentials": {"postgres": POSTGRES_CRED},
        },
        {
            "id": str(uuid.uuid4()),
            "name": "If Has Context To Save",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [x + 200, y + 300],
            "parameters": {
                "options": {},
                "conditions": {
                    "options": {
                        "version": 2,
                        "leftValue": "",
                        "caseSensitive": True,
                        "typeValidation": "loose",
                    },
                    "combinator": "and",
                    "conditions": [
                        {
                            "id": str(uuid.uuid4()),
                            "operator": {
                                "type": "string",
                                "operation": "notEmpty",
                                "singleValue": True,
                            },
                            "leftValue": "={{ String(($json.pending_context_to_save || {}).target_telegram_id || '') }}",
                            "rightValue": "",
                        }
                    ],
                },
            },
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Save Pending Context",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.6,
            "position": [x + 400, y + 300],
            "onError": "continueRegularOutput",
            "parameters": {
                "query": SAVE_CONTEXT_SQL,
                "options": {},
                "operation": "executeQuery",
            },
            "credentials": {"postgres": POSTGRES_CRED},
        },
        {
            "id": str(uuid.uuid4()),
            "name": "If Context Was Used",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [x + 200, y + 500],
            "parameters": {
                "options": {},
                "conditions": {
                    "options": {
                        "version": 2,
                        "leftValue": "",
                        "caseSensitive": True,
                        "typeValidation": "loose",
                    },
                    "combinator": "and",
                    "conditions": [
                        {
                            "id": str(uuid.uuid4()),
                            "operator": {
                                "type": "number",
                                "operation": "gt",
                            },
                            "leftValue": "={{ Number(($json.context_used || {}).context_id || 0) }}",
                            "rightValue": 0,
                        }
                    ],
                },
            },
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Mark Context Used",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.6,
            "position": [x + 400, y + 500],
            "onError": "continueRegularOutput",
            "parameters": {
                "query": MARK_USED_SQL,
                "options": {},
                "operation": "executeQuery",
            },
            "credentials": {"postgres": POSTGRES_CRED},
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Confirm Context To Jonathan",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [x + 600, y + 500],
            "onError": "continueRegularOutput",
            "parameters": {
                "chatId": JONATHAN_CHAT_ID,
                "text": CONFIRM_TEXT,
                "additionalFields": {"appendAttribution": False},
            },
            "credentials": {"telegramApi": TELEGRAM_CRED},
        },
    ]


# ── Context Builder JS patch ──────────────────────────────────────────────
CONTEXT_BUILDER_PATCH_MARKER = "// ── pendingInquiries (deploy 038 — Response Correlation)"
CONTEXT_BUILDER_NEW_CODE = """// ── pendingContext (deploy 074 — Back-channel Context Injection) ───────
// Operator-deposited context for the CURRENT sender to apply naturally.
let pendingContext = [];
try {
  const items = $('Fetch Pending Context').all();
  pendingContext = items
    .map(i => i.json)
    .filter(r => r && r.id);
} catch (e) {
  pendingContext = [];
}

"""

CONTEXT_INPUT_INJECTION = """
OPERATOR CONTEXT (use naturally in your reply, do NOT mention Jonathan):
${pendingContext.length ? pendingContext.map(c => `[id:${c.id}] ${c.context_text}`).join('\\n') : '(none)'}
"""

# ── System prompt additions ───────────────────────────────────────────────
RULE_F_TEXT = """

---

## CONTEXT INJECTION FROM OPERATOR (Rule F — bidirectional)

### When Jonathan messages you to PRE-LOAD context for a specific client

Jonathan can deposit context that you'll apply when that client next messages.

Examples Jonathan might say:
- "When Allan asks about the receipt, tell him it was processed Friday."
- "If Datu mentions the SPA, mention I'm flying to Naga on the 22nd."
- "For Don Qi's next message, his sister's name is Marie — use it naturally if relevant."

When you detect this intent, you MUST:
1. Resolve the target client by name using Rule C's directory.
2. Emit `pending_context_to_save` in your JSON output:
   ```
   {
     "target_telegram_id": "<resolved numeric id>",
     "target_client_name": "<name Jonathan used>",
     "context_text": "<verbatim or condensed context to apply>"
   }
   ```
3. Reply to Jonathan: `"Noted. Next time <client> messages, I'll mention <gist>."`

If the target client's telegram_id is not in the Rule C directory (e.g. Datu Shishir today), REFUSE: tell Jonathan to record the telegram_id first.

### When a CLIENT (non-Jonathan) messages you AND `pendingContext[]` is non-empty in the agent input

The pendingContext block contains rows Jonathan deposited for this exact sender. For each row:
1. Read the context_text.
2. Weave it naturally into your `telegram_reply_to_client` — do NOT mention Jonathan, do NOT reveal it came from a back-channel.
3. Emit `context_used` in your JSON output:
   ```
   {
     "context_id": <id from pendingContext>,
     "wording": "<the exact sentence you used in your reply>"
   }
   ```
4. The downstream node will mark the row as used and confirm to Jonathan.

Multiple pendingContext rows: use whichever ones are relevant to this turn; leave others alone (they stay unused for future turns).

### Inviolable

- Operator context is for the TARGET client ONLY. Never apply Allan's context when Don Qi messages.
- `pending_context_to_save` may only be populated when `isJonathan === true`.
- `context_used` may only be populated when a real pendingContext row was actually applied.
- Never fabricate context_id; only use ids present in the pendingContext input."""

# Schema additions inside the JSON output spec
SCHEMA_FIELDS_ADDITION = """,
  "pending_context_to_save": {
    "target_telegram_id": "", "target_client_name": "", "context_text": ""
  },
  "context_used": {
    "context_id": 0, "wording": ""
  }"""


def patch_context_builder(node):
    """Inject pendingContext reading + agentInput injection into the existing JS."""
    js = node["parameters"]["jsCode"]
    if "pendingContext" in js:
        return False  # already patched
    # Insert new block right after pendingInquiries block
    if CONTEXT_BUILDER_PATCH_MARKER not in js:
        raise ValueError("Context Builder JS missing marker — manual review needed")
    # Find end of pendingInquiries try/catch (just before the empty line before senderId)
    insert_at = js.index("const senderId =")
    new_js = js[:insert_at] + CONTEXT_BUILDER_NEW_CODE + js[insert_at:]
    # Inject pendingContext into agentInput template
    if "OPERATOR CONTEXT" not in new_js:
        # Append to the agentInput template — find the template literal
        marker = "RECENT DOCUMENTS UPLOADED BY THIS CLIENT (last 4 with extracted content):\n${documentsBlock}`;"
        if marker not in new_js:
            raise ValueError("Context Builder JS missing agentInput marker")
        new_js = new_js.replace(
            marker,
            "RECENT DOCUMENTS UPLOADED BY THIS CLIENT (last 4 with extracted content):\n${documentsBlock}\n" + CONTEXT_INPUT_INJECTION + "`;"
        )
    # Add pendingContext to the returned json
    new_js = new_js.replace(
        "    pendingInquiries,",
        "    pendingInquiries,\n    pendingContext,"
    )
    node["parameters"]["jsCode"] = new_js
    return True


def patch_ai_agent_prompt(node):
    """Inject Rule F + schema fields into system prompt."""
    prompt = node["parameters"]["options"]["systemMessage"]
    if "## CONTEXT INJECTION FROM OPERATOR (Rule F" in prompt:
        return False  # already patched
    # Append Rule F at the end
    prompt = prompt.rstrip() + RULE_F_TEXT
    # Insert new schema fields right after target_chat_id/target_message lines
    schema_marker = '"target_chat_id": "",\n  "target_message": ""'
    if schema_marker not in prompt:
        # Try alternate format
        schema_marker = '"target_chat_id": "",'
        if schema_marker not in prompt:
            raise ValueError("AI Agent prompt missing target_chat_id schema marker")
    # Find the comma+target_message line and append our fields right after
    # The simplest reliable approach: locate '"target_message": ""' and append after the comma at end of that line
    target_msg_end = prompt.index('"target_message": ""')
    # Find the end of this JSON entry (the next comma + newline)
    after_target_msg = prompt.index('\n', target_msg_end)
    prompt = prompt[:after_target_msg] + SCHEMA_FIELDS_ADDITION + prompt[after_target_msg:]
    node["parameters"]["options"]["systemMessage"] = prompt
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["staging", "prod"], required=True)
    args = parser.parse_args()

    if args.target == "staging":
        DSN = dict(host="127.0.0.1", port=5433, dbname="n8n", user="n8n", password="n8npassword")
    else:
        DSN = dict(host="172.18.0.3", port=5432, dbname="n8n", user="n8n", password="n8npassword")
    print(f"  target={args.target}  dsn={DSN['host']}:{DSN['port']}")

    # 1. DDL
    conn = psycopg2.connect(**DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(PENDING_CONTEXT_DDL)
    cur.execute("SELECT count(*) FROM pending_context")
    print(f"  ✓ pending_context table ready ({cur.fetchone()[0]} existing rows)")
    cur.close(); conn.close()

    # 2. Read workflow
    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name=%s", (WF_NAME,))
    wf_id, nodes, conns = cur.fetchone()

    # 3. Snapshot
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_074_{args.target}_{ts}.json"
    os.makedirs("/root/landtek/snapshots", exist_ok=True)
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes, "connections": conns}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    # 4. Locate Fetch Pending Inquiries position
    fpi = next((n for n in nodes if n["name"] == "Fetch Pending Inquiries"), None)
    if not fpi:
        sys.exit("FATAL: Fetch Pending Inquiries not found")
    base_pos = fpi.get("position", [0, 0])

    # 5. Add new nodes (idempotent)
    new_names = ["Fetch Pending Context", "If Has Context To Save", "Save Pending Context",
                 "If Context Was Used", "Mark Context Used", "Confirm Context To Jonathan"]
    existing_names = {n["name"] for n in nodes}
    if all(name in existing_names for name in new_names):
        print(f"  ⚠ all 6 nodes already exist — skipping node creation")
    else:
        new_nodes = [n for n in build_new_nodes(base_pos) if n["name"] not in existing_names]
        nodes.extend(new_nodes)
        print(f"  ✓ added {len(new_nodes)} nodes: {[n['name'] for n in new_nodes]}")

    # 6. Patch Context Builder JS
    cb = next((n for n in nodes if n["name"] == "Context Builder"), None)
    if not cb:
        sys.exit("FATAL: Context Builder not found")
    changed = patch_context_builder(cb)
    print(f"  ✓ Context Builder JS {'patched' if changed else 'already up to date'}")

    # 7. Patch AI Agent system prompt
    aia = next((n for n in nodes if n["name"] == "AI Agent"), None)
    if not aia:
        sys.exit("FATAL: AI Agent not found")
    changed = patch_ai_agent_prompt(aia)
    print(f"  ✓ AI Agent prompt {'patched' if changed else 'already up to date'}")

    # 8. Wire connections
    # 8a. Fetch Pending Inquiries -> Fetch Pending Context (instead of Context Builder)
    conns["Fetch Pending Inquiries"] = {
        "main": [[{"node": "Fetch Pending Context", "type": "main", "index": 0}]]
    }
    # 8b. Fetch Pending Context -> Context Builder
    conns["Fetch Pending Context"] = {
        "main": [[{"node": "Context Builder", "type": "main", "index": 0}]]
    }
    # 8c. Parse Agent1: add new branches to existing fan-out
    pa_targets = conns.get("Parse Agent1", {}).get("main", [[]])
    existing_pa_dst_names = {t["node"] for t in pa_targets[0]}
    if "If Has Context To Save" not in existing_pa_dst_names:
        pa_targets[0].append({"node": "If Has Context To Save", "type": "main", "index": 0})
    if "If Context Was Used" not in existing_pa_dst_names:
        pa_targets[0].append({"node": "If Context Was Used", "type": "main", "index": 0})
    conns["Parse Agent1"] = {"main": pa_targets}
    # 8d. If Has Context To Save -> Save Pending Context (true branch only)
    conns["If Has Context To Save"] = {
        "main": [[{"node": "Save Pending Context", "type": "main", "index": 0}], []]
    }
    # 8e. If Context Was Used -> Mark Context Used (true branch)
    conns["If Context Was Used"] = {
        "main": [[{"node": "Mark Context Used", "type": "main", "index": 0}], []]
    }
    # 8f. Mark Context Used -> Confirm Context To Jonathan
    conns["Mark Context Used"] = {
        "main": [[{"node": "Confirm Context To Jonathan", "type": "main", "index": 0}]]
    }
    print(f"  ✓ wired connections")

    # 9. Persist
    cur.close(); conn.close()
    if args.target == "staging":
        conn = psycopg2.connect(**DSN); conn.autocommit = False
        cur = conn.cursor()
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
        print(f"  ✓ staging workflow_entity + workflow_history updated, reactivated")
    else:
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes, connections=conns)


if __name__ == "__main__":
    main()
