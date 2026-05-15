#!/usr/bin/env python3
"""Deploy 072 — Whitelist auth gate before AI Agent.

Inserts a 5-node gate between Telegram Trigger and the rest of the workflow:

  Telegram Trigger
    -> Whitelist Check (Postgres SELECT — is sender_id in clients.telegram_id
       OR authorized_users.telegram_user_id? + count of prior unauth attempts)
    -> If Authorized (IF — branches on is_authorized boolean)
        TRUE  -> Execute a SQL query (existing first node — unchanged downstream)
        FALSE -> Log Unauth Attempt (Postgres INSERT INTO unauth_attempts)
              -> If First Unauth (IF — branches on prior_attempts == 0)
                 TRUE  -> Notify Jonathan Unauth (Telegram DM with sender details)
                 FALSE -> [silent — already notified once]

Why silent reject (no reply to unauthorized sender):
  - Doesn't confirm bot existence to spammers
  - No token spend (AI Agent never runs)
  - Jonathan gets ONE notification per new unauthorized sender, then silence

The script is target-agnostic: pass --target=staging or --target=prod.
"""
import json
import os
import sys
import uuid
import argparse

sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

WF_NAME = "Leos Workflow"
POSTGRES_CRED = {"id": "kPUGFA1HrZZFWnzI", "name": "Postgres account 2"}
TELEGRAM_CRED = {"id": "dSI1mdlTrzwdd1B8", "name": "Telegram account"}
JONATHAN_CHAT_ID = "6513067717"

# ── DDL: unauth_attempts table ────────────────────────────────────────────
UNAUTH_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS unauth_attempts (
    id SERIAL PRIMARY KEY,
    telegram_id VARCHAR(50) NOT NULL,
    first_name TEXT,
    username VARCHAR(100),
    message_text TEXT,
    attempted_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_unauth_attempts_telegram_id ON unauth_attempts(telegram_id);
CREATE INDEX IF NOT EXISTS idx_unauth_attempts_attempted_at ON unauth_attempts(attempted_at DESC);
"""

# ── New node definitions ──────────────────────────────────────────────────

WHITELIST_CHECK_SQL = """SELECT
  (
    EXISTS (SELECT 1 FROM clients WHERE telegram_id = '{{ $json.message.from.id }}'::text)
    OR EXISTS (SELECT 1 FROM authorized_users WHERE telegram_user_id::text = '{{ $json.message.from.id }}'::text AND active = true)
  ) AS is_authorized,
  (SELECT count(*) FROM unauth_attempts WHERE telegram_id = '{{ $json.message.from.id }}'::text) AS prior_attempts,
  '{{ $json.message.from.id }}'::text AS sender_id,
  '{{ $json.message.from.first_name }}'::text AS sender_first_name,
  '{{ $json.message.from.username }}'::text AS sender_username;"""

LOG_UNAUTH_SQL = """INSERT INTO unauth_attempts (telegram_id, first_name, username, message_text)
VALUES (
  '{{ $('Telegram Trigger').first().json.message.from.id }}'::text,
  '{{ $('Telegram Trigger').first().json.message.from.first_name }}'::text,
  NULLIF('{{ $('Telegram Trigger').first().json.message.from.username }}', '')::text,
  COALESCE(
    NULLIF('{{ $('Telegram Trigger').first().json.message.text }}', ''),
    NULLIF('{{ $('Telegram Trigger').first().json.message.caption }}', ''),
    ''
  )::text
) RETURNING id;"""

NOTIFY_TEXT = """🚨 Unauthorized sender hit @LeoLandTekBot

Name: {{ $('Telegram Trigger').first().json.message.from.first_name }} {{ $('Telegram Trigger').first().json.message.from.last_name }}
Username: @{{ $('Telegram Trigger').first().json.message.from.username }}
Telegram ID: {{ $('Telegram Trigger').first().json.message.from.id }}

Message: "{{ $('Telegram Trigger').first().json.message.text || $('Telegram Trigger').first().json.message.caption || '(no text)' }}"

They were silently rejected (no AI processing, no acknowledgment to them).

To authorize them, run:
  INSERT INTO authorized_users (telegram_user_id, name, role, active) VALUES ('{{ $('Telegram Trigger').first().json.message.from.id }}', '{{ $('Telegram Trigger').first().json.message.from.first_name }}', 'client', true);

Or to link to an existing client row (e.g. Datu Shishir → Paracale-001):
  UPDATE clients SET telegram_id = '{{ $('Telegram Trigger').first().json.message.from.id }}' WHERE case_file = 'Paracale-001';

Subsequent attempts from this ID will NOT re-notify (deduped via unauth_attempts table)."""


def build_nodes(base_position):
    """Generate the 5 new nodes. base_position is the [x, y] of Telegram Trigger."""
    x, y = base_position
    # Lay them out vertically below/beside Telegram Trigger
    return [
        {
            "id": str(uuid.uuid4()),
            "name": "Whitelist Check",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.4,
            "position": [x + 220, y],
            "parameters": {
                "operation": "executeQuery",
                "query": WHITELIST_CHECK_SQL,
                "options": {},
            },
            "credentials": {"postgres": POSTGRES_CRED},
        },
        {
            "id": str(uuid.uuid4()),
            "name": "If Authorized",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [x + 440, y],
            "parameters": {
                "options": {},
                "conditions": {
                    "options": {
                        "version": 2,
                        "leftValue": "",
                        "caseSensitive": True,
                        "typeValidation": "strict",
                    },
                    "combinator": "and",
                    "conditions": [
                        {
                            "id": str(uuid.uuid4()),
                            "operator": {
                                "type": "boolean",
                                "operation": "true",
                                "singleValue": True,
                            },
                            "leftValue": "={{ $json.is_authorized }}",
                            "rightValue": "",
                        }
                    ],
                },
            },
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Log Unauth Attempt",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.4,
            "position": [x + 660, y + 200],
            "parameters": {
                "operation": "executeQuery",
                "query": LOG_UNAUTH_SQL,
                "options": {},
            },
            "credentials": {"postgres": POSTGRES_CRED},
        },
        {
            "id": str(uuid.uuid4()),
            "name": "If First Unauth",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [x + 880, y + 200],
            "parameters": {
                "options": {},
                "conditions": {
                    "options": {
                        "version": 2,
                        "leftValue": "",
                        "caseSensitive": True,
                        "typeValidation": "strict",
                    },
                    "combinator": "and",
                    "conditions": [
                        {
                            "id": str(uuid.uuid4()),
                            "operator": {
                                "type": "number",
                                "operation": "equals",
                            },
                            "leftValue": "={{ $('Whitelist Check').first().json.prior_attempts }}",
                            "rightValue": 0,
                        }
                    ],
                },
            },
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Notify Jonathan Unauth",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [x + 1100, y + 200],
            "parameters": {
                "chatId": JONATHAN_CHAT_ID,
                "text": NOTIFY_TEXT,
                "additionalFields": {"appendAttribution": False},
            },
            "credentials": {"telegramApi": TELEGRAM_CRED},
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

    # ── 1. Create unauth_attempts table ───────────────────────────────────
    conn = psycopg2.connect(**DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(UNAUTH_TABLE_DDL)
    cur.execute("SELECT count(*) FROM unauth_attempts")
    print(f"  ✓ unauth_attempts table ready ({cur.fetchone()[0]} existing rows)")
    cur.close(); conn.close()

    # ── 2. Snapshot workflow before patching ──────────────────────────────
    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("""SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name=%s""", (WF_NAME,))
    wf_id, nodes, conns = cur.fetchone()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_072_{args.target}_{ts}.json"
    os.makedirs("/root/landtek/snapshots", exist_ok=True)
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes, "connections": conns}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    # ── 3. Locate Telegram Trigger to derive new-node positions ───────────
    tt = next((n for n in nodes if n["name"] == "Telegram Trigger"), None)
    if not tt:
        sys.exit("FATAL: Telegram Trigger node not found")
    base_pos = tt.get("position", [0, 0])

    # ── 4. Add the 5 new nodes (idempotent: skip if already exists) ───────
    new_names = ["Whitelist Check", "If Authorized", "Log Unauth Attempt",
                 "If First Unauth", "Notify Jonathan Unauth"]
    existing_names = {n["name"] for n in nodes}
    if any(name in existing_names for name in new_names):
        already = [n for n in new_names if n in existing_names]
        print(f"  ⚠ gate nodes already exist: {already} — skipping node creation")
        skip_create = True
    else:
        new_nodes = build_nodes(base_pos)
        nodes.extend(new_nodes)
        print(f"  ✓ added {len(new_nodes)} nodes: {[n['name'] for n in new_nodes]}")
        skip_create = False

    # ── 5. Rewire connections ─────────────────────────────────────────────
    # Original:    Telegram Trigger -> Execute a SQL query
    # New:         Telegram Trigger -> Whitelist Check -> If Authorized
    #                                                     |true  -> Execute a SQL query
    #                                                     |false -> Log Unauth Attempt -> If First Unauth
    #                                                              -> true: Notify Jonathan Unauth
    #                                                              -> false: (terminate)

    # Save what Telegram Trigger currently points to (Execute a SQL query)
    tt_targets = conns.get("Telegram Trigger", {}).get("main", [])

    # 5a. Telegram Trigger -> Whitelist Check
    conns["Telegram Trigger"] = {
        "main": [[{"node": "Whitelist Check", "type": "main", "index": 0}]]
    }
    # 5b. Whitelist Check -> If Authorized
    conns["Whitelist Check"] = {
        "main": [[{"node": "If Authorized", "type": "main", "index": 0}]]
    }
    # 5c. If Authorized true (index 0) -> original targets (Execute a SQL query)
    #     If Authorized false (index 1) -> Log Unauth Attempt
    conns["If Authorized"] = {
        "main": [
            tt_targets[0] if tt_targets else [],   # true: pass through
            [{"node": "Log Unauth Attempt", "type": "main", "index": 0}],
        ]
    }
    # 5d. Log Unauth Attempt -> If First Unauth
    conns["Log Unauth Attempt"] = {
        "main": [[{"node": "If First Unauth", "type": "main", "index": 0}]]
    }
    # 5e. If First Unauth true -> Notify Jonathan Unauth; false -> terminate
    conns["If First Unauth"] = {
        "main": [
            [{"node": "Notify Jonathan Unauth", "type": "main", "index": 0}],
            [],
        ]
    }
    print(f"  ✓ rewired Telegram Trigger -> Whitelist Check -> If Authorized -> [auth path | reject path]")

    cur.close(); conn.close()

    # ── 6. Persist via patch_workflow_dual (handles workflow_history too) ─
    from deploy_helpers import patch_workflow_dual
    # patch_workflow_dual expects (workflow_id, nodes, connections) — but it
    # uses a fixed DSN to prod. Patch the staging case manually.
    if args.target == "staging":
        # Manual write — patch_workflow_dual is hardcoded to prod DSN
        conn = psycopg2.connect(**DSN); conn.autocommit = False
        cur = conn.cursor()
        cur.execute(
            """UPDATE workflow_entity SET nodes=%s, connections=%s, "updatedAt"=now() WHERE id=%s""",
            (json.dumps(nodes), json.dumps(conns), wf_id),
        )
        # Also update workflow_history.latest (n8n runtime reads from here)
        cur.execute(
            """UPDATE workflow_history SET nodes=%s, connections=%s
                WHERE "workflowId"=%s
                  AND "createdAt" = (SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""",
            (json.dumps(nodes), json.dumps(conns), wf_id, wf_id),
        )
        # Force reactivation so webhook re-registers (mirror patch_workflow_dual)
        cur.execute('UPDATE workflow_entity SET active=false, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit()
        import time; time.sleep(1)
        cur.execute('UPDATE workflow_entity SET active=true, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()
        print(f"  ✓ staging workflow_entity + workflow_history updated")
    else:
        patch_workflow_dual(wf_id, nodes=nodes, connections=conns)
        print(f"  ✓ prod workflow_entity + workflow_history updated via patch_workflow_dual")


if __name__ == "__main__":
    main()
