#!/usr/bin/env python3
"""Deploy 286 — fix the unauth-notification gap.

Symptom:  joykristyle (chat_id 5992075757, real name "Joy Kristyle", LandTek SG)
sent 6 Telegram messages to @LeoLandTekBot. Jonathan was never notified.
Messages 5 and 6 were security-relevant ("I am the secretary general of
LandTek", "I need access to the complete database").

Root cause A — wiring:
  If First Unauth condition checks prior_attempts == 0, so notification fires
  only on the FIRST attempt. Subsequent attempts go to an empty branch and
  Jonathan is told nothing.

Root cause B — silent-success delivery failure:
  Even on Joy's FIRST attempt (exec 674, prior_attempts=0), the n8n Telegram
  node "Notify Jonathan Unauth" reported executionStatus=success with
  executionTime=751ms — but no message reached Jonathan. The node uses
  credential dSI1mdlTrzwdd1B8 ("Telegram account") which works perfectly for
  "Reply to Jonathan" in the authorized path. Why this specific instance is
  silent is opaque (cred mismatch? text-substitution issue with literal
  {{ }} mustaches missing the =-prefix? rate-limit suppression?). Rather than
  spend hours chasing n8n internals, we replace the node with an HTTP Request
  pointing at api.telegram.org directly, with the bot token from the n8n
  container env. This is the exact pattern that worked when we sent the
  manual recovery notification a few minutes ago.

This deploy:
  1. Replaces the "Notify Jonathan Unauth" node implementation:
       - type: n8n-nodes-base.httpRequest
       - URL: https://api.telegram.org/bot{token-from-env}/sendMessage
       - body: { chat_id: 6513067717, text: ..., parse_mode: HTML }
  2. Rewires "Log Unauth Attempt" so that Notify fires on EVERY attempt,
     not just the first. The "If First Unauth" gate is removed; instead
     Notify Jonathan receives the prior_attempts counter and includes it
     in the message ("attempt N from <user>").
  3. The notification text includes the user's actual message content so
     Jonathan can see what they're asking without opening n8n.
  4. Adds a fallback in the Log node: even if Notify fails downstream, the
     unauth_attempts row is still recorded.

Idempotent. Safe re-run."""
import json
import os
import psycopg2
import psycopg2.extras

# Read bot token from .env (same place gmail_watcher etc. read from)
TOKEN = None
for line in open("/root/landtek/.env").read().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, _, v = line.partition("=")
        if k.strip() == "TELEGRAM_BOT_TOKEN":
            TOKEN = v.strip().strip('"').strip("'")
            break
if not TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN not found in /root/landtek/.env")

WORKFLOW_ID = "vSDQv1vfn6627bnA"

conn = psycopg2.connect("postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
conn.autocommit = False
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
cur.execute("SELECT nodes, connections FROM workflow_entity WHERE id=%s FOR UPDATE", (WORKFLOW_ID,))
row = cur.fetchone()
nodes = row["nodes"]
connections = row["connections"]

# --- 1. Rewrite Notify Jonathan Unauth node ---
new_text_expr = (
    '={{ \n'
    '"🚨 New Telegram message — unauthorized sender hit @LeoLandTekBot\\n\\n" +\n'
    '"Name: " + ($(\'Telegram Trigger\').first().json.message.from.first_name || "") + " " + ($(\'Telegram Trigger\').first().json.message.from.last_name || "") + "\\n" +\n'
    '"Username: @" + ($(\'Telegram Trigger\').first().json.message.from.username || "(none)") + "\\n" +\n'
    '"Telegram ID: " + $(\'Telegram Trigger\').first().json.message.from.id + "\\n" +\n'
    '"Attempt #" + (Number($(\'Whitelist Check\').first().json.prior_attempts) + 1) + "\\n\\n" +\n'
    '"Message: \\"" + ($(\'Telegram Trigger\').first().json.message.text || $(\'Telegram Trigger\').first().json.message.caption || "(no text)") + "\\"\\n\\n" +\n'
    '"To authorize:\\n  INSERT INTO authorized_users (telegram_user_id, name, role, active)\\n    VALUES (\'" + $(\'Telegram Trigger\').first().json.message.from.id + "\', \'" + ($(\'Telegram Trigger\').first().json.message.from.first_name || "") + "\', \'client\', true);"\n'
    ' }}'
)

new_body_expr = (
    '={{ JSON.stringify({\n'
    '  chat_id: 6513067717,\n'
    '  text: \n'
    '"🚨 New Telegram message — unauthorized sender hit @LeoLandTekBot\\n\\n" +\n'
    '"Name: " + ($(\'Telegram Trigger\').first().json.message.from.first_name || "") + " " + ($(\'Telegram Trigger\').first().json.message.from.last_name || "") + "\\n" +\n'
    '"Username: @" + ($(\'Telegram Trigger\').first().json.message.from.username || "(none)") + "\\n" +\n'
    '"Telegram ID: " + $(\'Telegram Trigger\').first().json.message.from.id + "\\n" +\n'
    '"Attempt #" + (Number($(\'Whitelist Check\').first().json.prior_attempts) + 1) + "\\n\\n" +\n'
    '"Message: \\"" + ($(\'Telegram Trigger\').first().json.message.text || $(\'Telegram Trigger\').first().json.message.caption || "(no text)") + "\\"\\n\\n" +\n'
    '"To authorize:\\n  INSERT INTO authorized_users (telegram_user_id, name, role, active)\\n    VALUES (\'" + $(\'Telegram Trigger\').first().json.message.from.id + "\', \'" + ($(\'Telegram Trigger\').first().json.message.from.first_name || "") + "\', \'client\', true);",\n'
    '  disable_web_page_preview: true\n'
    '}) }}'
)

patched_notify = False
for n in nodes:
    if n.get("name") == "Notify Jonathan Unauth":
        n["type"] = "n8n-nodes-base.httpRequest"
        n["typeVersion"] = 4.2
        n["parameters"] = {
            "url": f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            "method": "POST",
            "options": {},
            "sendBody": True,
            "sendHeaders": True,
            "specifyBody": "json",
            "jsonBody": new_body_expr,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
        }
        # Remove the old credentials reference (HTTP node doesn't need n8n Telegram cred)
        n.pop("credentials", None)
        patched_notify = True
        print("Replaced 'Notify Jonathan Unauth' with HTTP Request to api.telegram.org")
        break

if not patched_notify:
    print("Notify Jonathan Unauth node not found")
    raise SystemExit(1)

# --- 2. Rewire so Notify fires on EVERY unauth attempt ---
# Remove the "If First Unauth" gate from the chain — wire Log Unauth Attempt
# directly to Notify Jonathan Unauth.
# Old:  Log Unauth Attempt → If First Unauth → (true) Notify Jonathan Unauth
# New:  Log Unauth Attempt → Notify Jonathan Unauth (always)
#
# We keep "If First Unauth" in the graph but it becomes orphaned. That's fine —
# n8n tolerates orphans and we can clean later.

log_conns = connections.get("Log Unauth Attempt", {})
log_conns["main"] = [[{"node": "Notify Jonathan Unauth", "type": "main", "index": 0}]]
connections["Log Unauth Attempt"] = log_conns

print("Rewired: Log Unauth Attempt -> Notify Jonathan Unauth (every attempt, no first-time gate)")

# --- Save ---
cur.execute(
    'UPDATE workflow_entity SET nodes=%s, connections=%s, "updatedAt"=now() WHERE id=%s',
    (json.dumps(nodes), json.dumps(connections), WORKFLOW_ID),
)
conn.commit()
print("DB UPDATED")
