#!/usr/bin/env python3
"""sync_telegram_webhook.py - re-register Telegram webhook with the right secret.

n8n's Telegram Trigger uses a DETERMINISTIC secret per node (per
n8n-nodes-base source code in v2.16+):

    secret_token = workflow_id + "_" + node_id  # (alphanumerics, "_", "-")

Telegram delivers the secret in the X-Telegram-Bot-Api-Secret-Token header
on each webhook POST. If Telegram's stored secret doesn't match what n8n
expects, every webhook delivery returns 403 -> bot silently dead.

This script reads the workflow + node IDs from DB, computes the secret,
and calls Telegram's setWebhook with the right URL + secret_token. Should
run after every n8n restart (because n8n itself doesn't re-register).

Usage:
  python3 scripts/sync_telegram_webhook.py
"""
import argparse
import json
import os
import re
import sys
import urllib.request

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
WORKFLOW_ID = "vSDQv1vfn6627bnA"
WEBHOOK_BASE = "https://leo.hayuma.org/webhook"
ENV_PATH = "/root/landtek/.env"
BOT_TOKEN_KEYS = ("TG_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "BOT_TOKEN")


def load_bot_token():
    for path in (ENV_PATH, os.path.expanduser("~/.env")):
        if not os.path.exists(path):
            continue
        with open(path) as f:
            for line in f:
                for k in BOT_TOKEN_KEYS:
                    if line.startswith(k + "="):
                        return line.split("=", 1)[1].strip().strip('"\'')
    return None


def compute_secret(workflow_id, node_id):
    """Mirror of n8n-nodes-base/dist/nodes/Telegram/GenericFunctions.js getSecretToken().
    secret_token = (workflow.id + '_' + node.id) with non-[A-Za-z0-9_-] stripped."""
    raw = f"{workflow_id}_{node_id}"
    return re.sub(r"[^A-Za-z0-9_-]+", "", raw)


def get_trigger_node_info(workflow_id):
    conn = psycopg2.connect(DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT n->>'id' AS node_id, n->>'webhookId' AS webhook_id
          FROM workflow_entity, jsonb_array_elements(nodes::jsonb) n
         WHERE id = %s
           AND n->>'type' = 'n8n-nodes-base.telegramTrigger'
    """, (workflow_id,))
    r = cur.fetchone()
    cur.close()
    conn.close()
    return (r["node_id"], r["webhook_id"]) if r else (None, None)


def set_webhook(token, url, secret_token):
    body = json.dumps({
        "url": url,
        "secret_token": secret_token,
        "max_connections": 40,
        "drop_pending_updates": False,
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/setWebhook",
        data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def get_webhook_info(token):
    with urllib.request.urlopen(
        f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=10
    ) as resp:
        return json.loads(resp.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow-id", default=WORKFLOW_ID)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = load_bot_token()
    if not token:
        print(f"FAIL: no bot token in {ENV_PATH}", file=sys.stderr)
        sys.exit(1)

    node_id, webhook_id = get_trigger_node_info(args.workflow_id)
    if not node_id:
        print(f"FAIL: no Telegram Trigger node in workflow {args.workflow_id}", file=sys.stderr)
        sys.exit(1)

    secret = compute_secret(args.workflow_id, node_id)
    url = f"{WEBHOOK_BASE}/{webhook_id}/webhook"

    print(f"workflow_id: {args.workflow_id}")
    print(f"node_id:     {node_id}")
    print(f"webhook_id:  {webhook_id}")
    print(f"webhook url: {url}")
    print(f"secret:      {secret[:10]}...{secret[-6:]} (len {len(secret)})")

    info_before = get_webhook_info(token)
    cur_url = info_before.get("result", {}).get("url", "")
    print(f"\ncurrent telegram url: {cur_url[-50:] if cur_url else '(none)'}")
    print(f"pending updates:     {info_before.get('result',{}).get('pending_update_count',0)}")

    if args.dry_run:
        print("\n(dry-run; pass without --dry-run to apply)")
        return

    result = set_webhook(token, url, secret)
    if result.get("ok"):
        print(f"\nsetWebhook OK: {result.get('description','')}")
    else:
        print(f"\nsetWebhook FAILED: {result}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
