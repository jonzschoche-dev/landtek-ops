#!/usr/bin/env python3
"""Deploy 080 — Auth gate (retry of failed deploy_072, this time with typeVersion 2.6).

Previous attempt (deploy_072) used Postgres nodes with typeVersion 2.4 +
parameter shape that triggered n8n's 'dbTime.getTime is not a function'
error loop, blocking workflow activation. Killed Leo for ~10 min.

This rewrite:
  - Uses typeVersion 2.6 (matches Fetch Pending Inquiries / Execute a SQL query)
  - Uses the operation:executeQuery + query+options parameter shape (proven safe)
  - Validates on staging via the now-fixed start-staging.sh + functional checks
  - Promotes via patch_workflow_dual (zero-outage)

Gate placement:
  Telegram Trigger -> Whitelist Check -> If Authorized
    TRUE  -> Execute a SQL query (existing path)
    FALSE -> Log Unauth Attempt -> If First Unauth
              TRUE  -> Notify Jonathan Unauth (Telegram DM)
              FALSE -> (silent)
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

UNAUTH_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS unauth_attempts (
    id SERIAL PRIMARY KEY,
    telegram_id VARCHAR(50) NOT NULL,
    first_name TEXT,
    username VARCHAR(100),
    message_text TEXT,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_unauth_attempts_telegram_id ON unauth_attempts(telegram_id);
CREATE INDEX IF NOT EXISTS idx_unauth_attempts_attempted_at ON unauth_attempts(attempted_at DESC);
"""

WHITELIST_SQL = """SELECT
  (EXISTS (SELECT 1 FROM clients WHERE telegram_id = '{{ $json.message.from.id }}'::text)
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
  COALESCE(NULLIF('{{ $('Telegram Trigger').first().json.message.text }}', ''),
           NULLIF('{{ $('Telegram Trigger').first().json.message.caption }}', ''), '')::text
) RETURNING id;"""

NOTIFY_TEXT = """🚨 Unauthorized sender hit @LeoLandTekBot

Name: {{ $('Telegram Trigger').first().json.message.from.first_name }}
Username: @{{ $('Telegram Trigger').first().json.message.from.username }}
Telegram ID: {{ $('Telegram Trigger').first().json.message.from.id }}

Message: "{{ $('Telegram Trigger').first().json.message.text || '(no text)' }}"

Silently rejected. To authorize:
  INSERT INTO authorized_users (telegram_user_id, name, role, active)
    VALUES ('{{ $('Telegram Trigger').first().json.message.from.id }}',
            '{{ $('Telegram Trigger').first().json.message.from.first_name }}', 'client', true);

Or link to existing client (e.g. Paracale-001):
  UPDATE clients SET telegram_id = '{{ $('Telegram Trigger').first().json.message.from.id }}'
   WHERE case_file = 'Paracale-001';

Subsequent attempts from this ID won't re-notify (deduped via unauth_attempts)."""


def build_nodes(base_pos):
    x, y = base_pos
    return [
        {"id": str(uuid.uuid4()), "name": "Whitelist Check",
         "type": "n8n-nodes-base.postgres", "typeVersion": 2.6,
         "position": [x + 220, y],
         "parameters": {"operation": "executeQuery", "query": WHITELIST_SQL, "options": {}},
         "credentials": {"postgres": POSTGRES_CRED}},
        {"id": str(uuid.uuid4()), "name": "If Authorized",
         "type": "n8n-nodes-base.if", "typeVersion": 2.2,
         "position": [x + 440, y],
         "parameters": {"options": {},
                        "conditions": {"options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
                                       "combinator": "and",
                                       "conditions": [{"id": str(uuid.uuid4()),
                                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                                                       "leftValue": "={{ $json.is_authorized }}",
                                                       "rightValue": ""}]}}},
        {"id": str(uuid.uuid4()), "name": "Log Unauth Attempt",
         "type": "n8n-nodes-base.postgres", "typeVersion": 2.6,
         "position": [x + 660, y + 200],
         "onError": "continueRegularOutput",
         "parameters": {"operation": "executeQuery", "query": LOG_UNAUTH_SQL, "options": {}},
         "credentials": {"postgres": POSTGRES_CRED}},
        {"id": str(uuid.uuid4()), "name": "If First Unauth",
         "type": "n8n-nodes-base.if", "typeVersion": 2.2,
         "position": [x + 880, y + 200],
         "parameters": {"options": {},
                        "conditions": {"options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
                                       "combinator": "and",
                                       "conditions": [{"id": str(uuid.uuid4()),
                                                       "operator": {"type": "number", "operation": "equals"},
                                                       "leftValue": "={{ Number($('Whitelist Check').first().json.prior_attempts) }}",
                                                       "rightValue": 0}]}}},
        {"id": str(uuid.uuid4()), "name": "Notify Jonathan Unauth",
         "type": "n8n-nodes-base.telegram", "typeVersion": 1.2,
         "position": [x + 1100, y + 200],
         "onError": "continueRegularOutput",
         "parameters": {"chatId": JONATHAN_CHAT_ID, "text": NOTIFY_TEXT,
                        "additionalFields": {"appendAttribution": False}},
         "credentials": {"telegramApi": TELEGRAM_CRED}},
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

    # DDL
    conn = psycopg2.connect(**DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(UNAUTH_TABLE_DDL)
    cur.execute("SELECT count(*) FROM unauth_attempts")
    print(f"  ✓ unauth_attempts table ({cur.fetchone()[0]} rows)")
    cur.close(); conn.close()

    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name=%s", (WF_NAME,))
    wf_id, nodes, conns = cur.fetchone()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_080_{args.target}_{ts}.json"
    os.makedirs("/root/landtek/snapshots", exist_ok=True)
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes, "connections": conns}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    tt = next((n for n in nodes if n["name"] == "Telegram Trigger"), None)
    base_pos = tt.get("position", [0, 0])
    existing = {n["name"] for n in nodes}
    new_names = ["Whitelist Check", "If Authorized", "Log Unauth Attempt", "If First Unauth", "Notify Jonathan Unauth"]
    if all(n in existing for n in new_names):
        print("  ⚠ all gate nodes already present")
    else:
        to_add = [n for n in build_nodes(base_pos) if n["name"] not in existing]
        nodes.extend(to_add)
        print(f"  ✓ added {len(to_add)} gate nodes")

    # Rewire: Telegram Trigger -> Whitelist Check -> If Authorized -> [original | reject path]
    tt_targets = conns.get("Telegram Trigger", {}).get("main", [])
    conns["Telegram Trigger"] = {"main": [[{"node": "Whitelist Check", "type": "main", "index": 0}]]}
    conns["Whitelist Check"] = {"main": [[{"node": "If Authorized", "type": "main", "index": 0}]]}
    conns["If Authorized"] = {"main": [
        tt_targets[0] if tt_targets else [],
        [{"node": "Log Unauth Attempt", "type": "main", "index": 0}],
    ]}
    conns["Log Unauth Attempt"] = {"main": [[{"node": "If First Unauth", "type": "main", "index": 0}]]}
    conns["If First Unauth"] = {"main": [
        [{"node": "Notify Jonathan Unauth", "type": "main", "index": 0}],
        [],
    ]}
    print("  ✓ rewired (Whitelist Check is now the first hop)")

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
        print("  ✓ staging updated + reactivated")
    else:
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes, connections=conns)


if __name__ == "__main__":
    main()
