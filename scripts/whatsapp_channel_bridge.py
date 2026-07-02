#!/usr/bin/env python3
"""whatsapp_channel_bridge.py — drain queued WhatsApp replies → Meta Cloud API (parity with viber_channel_bridge).

WhatsApp inbound is webhook-push (the /api/channel/whatsapp adapter handles it live, and sends
replies INLINE the moment WHATSAPP_API_TOKEN + WHATSAPP_PHONE_NUMBER_ID are configured — no
restart needed, the adapter reads /root/landtek/.env on every send). What's missing is the
BACKLOG drain: replies produced while the token was unset land in channel_messages as
'pending_no_credentials'. This drains them once the credentials are configured.

Token-gated + degrade-gracefully: with no token it prints an expected-idle line and exits 0
(never fails), so it's safe to run on a timer before WhatsApp is ever provisioned. The moment
the token lands in .env, the next tick drains the backlog automatically. For WhatsApp the
token IS the external switch — provisioning it opens the channel by design.

  python3 scripts/whatsapp_channel_bridge.py --send
"""
import json
import os
import sys
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


def _send(phone_id, token, to_wa_id, text):
    req = urllib.request.Request(
        f"https://graph.facebook.com/v18.0/{phone_id}/messages",
        data=json.dumps({"messaging_product": "whatsapp", "to": to_wa_id,
                         "type": "text", "text": {"body": text}}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        j = json.loads(r.read().decode())
    mid = (j.get("messages") or [{}])[0].get("id")
    return bool(mid), mid


def send():
    token = _env("WHATSAPP_API_TOKEN")
    phone_id = _env("WHATSAPP_PHONE_NUMBER_ID")
    if not token or not phone_id:
        # Expected-idle: WhatsApp not provisioned yet. Exit 0 so the timer never shows failed.
        print("[whatsapp_bridge] idle — WHATSAPP_API_TOKEN / WHATSAPP_PHONE_NUMBER_ID not set; nothing to drain yet")
        return
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""SELECT id, channel_user_id, text_content FROM channel_messages
                   WHERE direction='outbound' AND status='pending_no_credentials'
                     AND channel_id=(SELECT id FROM channels WHERE name='whatsapp')
                   ORDER BY id ASC LIMIT 100""")
    rows = cur.fetchall(); sent = 0
    for r in rows:
        try:
            ok, mid = _send(phone_id, token, r["channel_user_id"], r["text_content"])
        except Exception:
            ok, mid = False, None
        cur.execute("UPDATE channel_messages SET status=%s, external_msg_id=%s WHERE id=%s",
                    ("sent" if ok else "failed", str(mid) if mid else None, r["id"]))
        sent += 1 if ok else 0
    print(f"[whatsapp_bridge] drained {sent}/{len(rows)} queued WhatsApp replies")
    cur.close(); c.close()


def main():
    if "--send" in sys.argv:
        send()
    else:
        sys.exit("usage: whatsapp_channel_bridge.py --send")


if __name__ == "__main__":
    main()
