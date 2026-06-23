#!/usr/bin/env python3
"""viber_set_webhook.py — register / inspect the Viber Bot webhook (operator, one-time after creating the bot).

Viber Bots are PUSH: register a public HTTPS URL once and Viber POSTs events to /api/channel/viber.
Operator prereqs:
  1. Create a Viber Public Account / Bot at partners.viber.com → copy its auth token.
  2. Put it in /root/landtek/.env as  VIBER_AUTH_TOKEN=...   (and optionally VIBER_SENDER_NAME=...).
  3. Expose the leo-tools server (port 8765) at a public HTTPS URL — Tailscale is private, so use a
     tunnel (Cloudflare Tunnel / ngrok) or a public domain + TLS reverse proxy. Viber requires valid SSL.

  python3 scripts/viber_set_webhook.py --info                                  # account info + current webhook
  python3 scripts/viber_set_webhook.py --set https://HOST/api/channel/viber     # register
  python3 scripts/viber_set_webhook.py --remove                                # unset (pause inbound)
"""
import json
import os
import sys
import urllib.request

TOKEN = os.environ.get("VIBER_AUTH_TOKEN", "")
BASE = "https://chatapi.viber.com/pa"


def _post(path, body):
    req = urllib.request.Request(f"{BASE}/{path}", data=json.dumps(body).encode(),
                                 headers={"X-Viber-Auth-Token": TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def main():
    if not TOKEN:
        sys.exit("[viber] VIBER_AUTH_TOKEN not set — create the bot at partners.viber.com and add it to .env first")
    a = sys.argv[1:]
    if "--info" in a:
        print(json.dumps(_post("get_account_info", {}), indent=2)); return
    if "--remove" in a:
        print(json.dumps(_post("set_webhook", {"url": ""}), indent=2)); return
    if "--set" in a:
        url = a[a.index("--set") + 1]
        body = {"url": url,
                "event_types": ["message", "conversation_started", "delivered", "failed", "subscribed", "unsubscribed"],
                "send_name": True, "send_photo": False}
        print(json.dumps(_post("set_webhook", body), indent=2)); return
    sys.exit("usage: viber_set_webhook.py --info | --set <https-url> | --remove")


if __name__ == "__main__":
    main()
