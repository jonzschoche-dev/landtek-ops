#!/usr/bin/env python3
"""viber_channel_bridge.py — drain queued Viber replies → Viber API (parity with email_channel_bridge).

Viber inbound is webhook-push (the /api/channel/viber adapter handles it live — no --inbound poll needed).
Outbound replies queued while VIBER_AUTH_TOKEN was unset land in channel_messages as 'pending_viber_send';
this drains them once the token is configured. Safe to run on a timer.

  python3 scripts/viber_channel_bridge.py --send
"""
import json
import os
import sys
import urllib.request

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
NAME = os.environ.get("VIBER_SENDER_NAME", "Leo · LandTek")
URL = "https://chatapi.viber.com/pa/send_message"


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


def _send(token, receiver, text):
    req = urllib.request.Request(URL, data=json.dumps(
        {"receiver": receiver, "type": "text", "text": text, "sender": {"name": NAME}}).encode(),
        headers={"X-Viber-Auth-Token": token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        j = json.loads(r.read().decode())
    return j.get("status") == 0, j.get("message_token")


def send():
    token = _env("VIBER_AUTH_TOKEN")
    if not token:
        # Expected-idle: Viber not provisioned yet. Exit 0 so a timer never shows failed.
        print("[viber_bridge] idle — VIBER_AUTH_TOKEN not set; nothing to drain yet")
        return
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""SELECT id, channel_user_id, text_content FROM channel_messages
                   WHERE status='pending_viber_send' AND direction='outbound'
                   ORDER BY id ASC LIMIT 100""")
    rows = cur.fetchall(); sent = 0
    for r in rows:
        try:
            ok, tok = _send(token, r["channel_user_id"], r["text_content"])
        except Exception:
            ok, tok = False, None
        cur.execute("UPDATE channel_messages SET status=%s, external_msg_id=%s WHERE id=%s",
                    ("sent" if ok else "failed", str(tok) if tok else None, r["id"]))
        sent += 1 if ok else 0
    print(f"[viber_bridge] drained {sent}/{len(rows)} queued Viber replies")


def main():
    if "--send" in sys.argv:
        send()
    else:
        sys.exit("usage: viber_channel_bridge.py --send")


if __name__ == "__main__":
    main()
