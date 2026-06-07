#!/usr/bin/env python3
"""webhook_anchor.py — keep the Telegram webhook pinned to the Python service.

Multiple existing services (leo_watchdog, sync_telegram_webhook,
webhook_watchdog, cowork-bridge, others) keep flipping the webhook back to
n8n's URL. Rather than hunting and disabling each, this daemon checks
every 30 seconds and restores the URL whenever it drifts. Fastest race
condition wins.

Idempotent. Logs only when it actually had to restore.
"""
from __future__ import annotations
import json
import os
import time
import urllib.parse
import urllib.request


TARGET_URL = "https://leo.hayuma.org/landtek/tg"
CHECK_INTERVAL = 30  # seconds


def _bot_token():
    p = "/root/landtek/.env"
    if not os.path.exists(p):
        return None
    for line in open(p):
        line = line.strip()
        for k in ("TG_BOT_TOKEN=", "TELEGRAM_BOT_TOKEN=", "BOT_TOKEN="):
            if line.startswith(k):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _get_webhook_url(token):
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/getWebhookInfo",
            timeout=10) as r:
            return json.loads(r.read().decode())["result"]["url"]
    except Exception:
        return None


def _set_webhook(token, url):
    try:
        q = urllib.parse.urlencode({
            "url": url,
            "allowed_updates": json.dumps(
                ["message", "edited_message", "callback_query",
                 "my_chat_member"]),
        })
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/setWebhook?{q}",
            timeout=10) as r:
            return r.read().decode()[:120]
    except Exception as e:
        return f"set_failed: {e}"


def main():
    token = _bot_token()
    if not token:
        print("no_token")
        return
    print(f"[anchor] target={TARGET_URL} interval={CHECK_INTERVAL}s")
    last_url = None
    while True:
        try:
            current = _get_webhook_url(token)
            if current != TARGET_URL:
                result = _set_webhook(token, TARGET_URL)
                print(f"[anchor] restored from {current!r} -> {TARGET_URL} | {result[:80]}")
            elif current != last_url:
                print(f"[anchor] holding {TARGET_URL}")
            last_url = current
        except Exception as e:
            print(f"[anchor] check_error: {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
