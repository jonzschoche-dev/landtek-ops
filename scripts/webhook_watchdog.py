#!/usr/bin/env python3
"""webhook_watchdog.py - poll Telegram every N seconds; re-register if empty.

Today (May 25 2026) the Telegram webhook has spontaneously deregistered THREE
TIMES in a span of hours. Root cause is still unclear (could be Telegram
auto-disabling after consecutive delivery failures, or n8n's deprecated
N8N_SKIP_WEBHOOK_DEREGISTRATION_SHUTDOWN behavior changing in v2.16).

Until root cause is known, this watchdog runs every 60 seconds, checks
Telegram's getWebhookInfo, and if URL is empty calls sync_telegram_webhook.py
to re-register. Designed to run as a systemd timer.

Usage (one-shot):
  python3 scripts/webhook_watchdog.py

Usage (loop, with optional interval):
  python3 scripts/webhook_watchdog.py --loop --interval 60

Exit codes:
  0  webhook is healthy (URL set, no recent 403/secret errors)
  1  webhook was empty; just re-registered
  2  failed to re-register
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

ENV_PATH = "/root/landtek/.env"
SYNC_SCRIPT = "/root/landtek/scripts/sync_telegram_webhook.py"
LOG_PATH = "/var/log/landtek/webhook_watchdog.log"
NOTIF_PATH = "/root/landtek/notifications/pending.txt"

BOT_TOKEN_KEYS = ("TG_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "BOT_TOKEN")


def load_bot_token():
    if not os.path.exists(ENV_PATH):
        return None
    with open(ENV_PATH) as f:
        for line in f:
            for k in BOT_TOKEN_KEYS:
                if line.startswith(k + "="):
                    return line.split("=", 1)[1].strip().strip('"\'')
    return None


def log(msg):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n"
    with open(LOG_PATH, "a") as f:
        f.write(line)
    print(line.strip())


def notify(msg):
    """Surface to next session-start hook."""
    os.makedirs(os.path.dirname(NOTIF_PATH), exist_ok=True)
    with open(NOTIF_PATH, "a") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] webhook_watchdog: {msg}\n")


def check_webhook(token):
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=8
        ) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"ok": False, "_error": str(e)}


def one_pass():
    token = load_bot_token()
    if not token:
        log("FAIL: no bot token in env")
        return 2

    info = check_webhook(token)
    if not info.get("ok"):
        log(f"getWebhookInfo failed: {info.get('_error') or info}")
        return 2

    result = info.get("result", {})
    url = result.get("url", "")
    pending = result.get("pending_update_count", 0)
    last_err = result.get("last_error_message", "")
    last_err_date = result.get("last_error_date")

    if url:
        # Healthy. Log a heartbeat occasionally only.
        if last_err_date:
            age = int(time.time()) - last_err_date
            if age < 300 and ("403" in last_err or "secret" in last_err.lower()):
                # Recent secret failure even though URL is set — re-register
                log(f"recent error ({age}s ago): {last_err[:80]} — re-registering")
                rc = subprocess.run(["python3", SYNC_SCRIPT], capture_output=True, text=True).returncode
                if rc == 0:
                    log("re-registered after recent 403/secret error")
                    notify(f"webhook had recent {last_err[:60]} error; re-registered")
                    return 1
                else:
                    log(f"re-register FAILED rc={rc}")
                    notify(f"webhook had recent {last_err[:60]} AND re-register failed (rc={rc})")
                    return 2
        return 0

    # URL is empty -> re-register
    log(f"webhook URL empty (pending={pending}, last_err='{last_err[:60]}') — re-registering")
    rc = subprocess.run(["python3", SYNC_SCRIPT], capture_output=True, text=True).returncode
    if rc == 0:
        log("re-registered successfully")
        notify(f"webhook URL went empty (pending={pending}); auto-re-registered")
        return 1
    log(f"re-register FAILED rc={rc}")
    notify(f"webhook URL empty AND re-register failed (rc={rc})")
    return 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true",
                    help="Run forever, checking every --interval seconds")
    ap.add_argument("--interval", type=int, default=60)
    args = ap.parse_args()

    if not args.loop:
        sys.exit(one_pass())

    while True:
        try:
            one_pass()
        except Exception as e:
            log(f"unhandled error: {type(e).__name__}: {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
