#!/usr/bin/env python3
"""messenger_channel_bridge.py — drain queued Messenger replies → Meta Graph Send API
(parity with whatsapp_channel_bridge / viber_channel_bridge).

Messenger inbound is webhook-push (/api/channel/messenger handles it live and sends replies INLINE
once MESSENGER_PAGE_TOKEN is configured — the adapter reads /root/landtek/.env on every send, no
restart). This drains the BACKLOG: replies produced while the token was unset land in
channel_messages as 'pending_no_credentials' on the messenger channel.

Token-gated + degrade-gracefully: with no token it prints an expected-idle line and exits 0 (never
fails), so it is safe on a timer before Messenger is ever provisioned. For Messenger the token IS
the external switch (A26) — provisioning it opens the channel by design.

  python3 scripts/messenger_channel_bridge.py --send
"""
import json
import os
import sys
import urllib.parse
import urllib.request

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _env(key, default=None):
    """Read a key from /root/landtek/.env (file-first, like the adapter), then os.environ."""
    try:
        with open("/root/landtek/.env") as f:
            for line in f:
                if line.startswith(f"{key}="):
                    return line.strip().split("=", 1)[1]
    except Exception:
        pass
    return os.environ.get(key, default)


def _send(token, psid, text):
    url = ("https://graph.facebook.com/v18.0/me/messages?access_token="
           + urllib.parse.quote(token))
    req = urllib.request.Request(url, data=json.dumps(
        {"recipient": {"id": psid}, "messaging_type": "RESPONSE",
         "message": {"text": text}}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        j = json.loads(r.read().decode())
    mid = j.get("message_id")
    return bool(mid), mid


def send():
    token = _env("MESSENGER_PAGE_TOKEN")
    if not token:
        # Expected-idle: Messenger not provisioned yet. Exit 0 so the timer never shows failed.
        print("[messenger_bridge] idle — MESSENGER_PAGE_TOKEN not set; nothing to drain yet")
        return
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""SELECT id, channel_user_id, text_content FROM channel_messages
                   WHERE direction='outbound' AND status='pending_no_credentials'
                     AND channel_id=(SELECT id FROM channels WHERE name='messenger')
                   ORDER BY id ASC LIMIT 100""")
    rows = cur.fetchall(); sent = 0
    for r in rows:
        try:
            ok, mid = _send(token, r["channel_user_id"], r["text_content"])
        except Exception:
            ok, mid = False, None
        cur.execute("UPDATE channel_messages SET status=%s, external_msg_id=%s WHERE id=%s",
                    ("sent" if ok else "failed", str(mid) if mid else None, r["id"]))
        sent += 1 if ok else 0
    print(f"[messenger_bridge] drained {sent}/{len(rows)} queued Messenger replies")
    cur.close(); c.close()


def main():
    if "--send" in sys.argv:
        send()
    else:
        sys.exit("usage: messenger_channel_bridge.py --send")


if __name__ == "__main__":
    main()
