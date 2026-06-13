#!/usr/bin/env python3
"""email_channel_bridge.py — wire Gmail into the omnichannel pipeline (Pillar 7).

The `/api/channel/email` adapter (leo_tools/channel_adapters.py) already normalizes inbound
email → routes through onboarding/agent → queues the reply as `pending_gmail_send`. What was
missing is the FEED (Gmail is polled, not webhooked to us) and the SEND drain. This bridges
both, reusing the already-ingested `gmail_messages` rows and the existing adapter.

  --inbound : new client inbound emails (gmail_messages) → POST /api/channel/email
              Creditless plumbing: routing/onboarding/audit run here; the reply CONTENT is
              produced by the agent (Leo) and is credit-gated, so it simply queues until fuel.
  --send    : drain channel_messages 'pending_gmail_send' → Gmail API send
              Needs gmail.send scope on GMAIL_REFRESH_TOKEN; best-effort (gated on reply content).

Idempotent via an email_bridge_state cursor (first run anchors at current max — no history replay).
"""
import base64
import json
import os
import sys
import urllib.request
from email.mime.text import MIMEText

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ADAPTER = os.environ.get("CHANNEL_EMAIL_URL", "http://localhost:8765/api/channel/email")
JONATHAN_ADDRS = ("jonzschoche@gmail.com", "jonathan@hayuma.org")


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def ensure(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS email_bridge_state (
        id int PRIMARY KEY DEFAULT 1, last_gmail_id bigint DEFAULT 0, updated_at timestamptz DEFAULT now())""")
    cur.execute("SELECT coalesce(max(id),0) FROM gmail_messages")
    cur.execute("INSERT INTO email_bridge_state (id,last_gmail_id) VALUES (1,(SELECT coalesce(max(id),0) FROM gmail_messages)) ON CONFLICT (id) DO NOTHING")


def inbound():
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor); ensure(cur)
    cur.execute("SELECT last_gmail_id FROM email_bridge_state WHERE id=1")
    cursor = cur.fetchone()["last_gmail_id"]
    cur.execute("""SELECT id, message_id, from_addr, subject, left(coalesce(body_plain,''),4000) AS body
                     FROM gmail_messages
                    WHERE id > %s AND coalesce(body_plain,'') <> ''
                      AND lower(coalesce(from_addr,'')) NOT IN %s
                    ORDER BY id ASC LIMIT 100""",
                (cursor, tuple(a.lower() for a in JONATHAN_ADDRS)))
    rows = cur.fetchall()
    sent = maxid = 0
    for r in rows:
        maxid = max(maxid, r["id"])
        payload = {"from": r["from_addr"], "subject": r["subject"] or "",
                   "body": r["body"], "message_id": r["message_id"] or ""}
        try:
            req = urllib.request.Request(ADAPTER, data=json.dumps(payload).encode(),
                                         headers={"content-type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=30).read()
            sent += 1
        except Exception as e:
            print(f"  ! {r['from_addr']}: {str(e)[:80]}")
    if maxid:
        cur.execute("UPDATE email_bridge_state SET last_gmail_id=%s, updated_at=now() WHERE id=1", (maxid,))
    print(f"[email_bridge] inbound: routed {sent}/{len(rows)} new client emails to the channel adapter; cursor->{maxid or cursor}")
    cur.close(); c.close()


def send():
    """Drain queued replies via Gmail. Best-effort; needs gmail.send scope."""
    try:
        sys.path.insert(0, "/root/landtek/scripts")
        from gmail_watcher import gmail_client
        svc = gmail_client()
    except Exception as e:
        print(f"[email_bridge] send: gmail client unavailable ({str(e)[:80]}) — replies stay queued")
        return
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""SELECT id, channel_user_id, text_content, metadata
                     FROM channel_messages
                    WHERE direction='outbound' AND status='pending_gmail_send'
                    ORDER BY id ASC LIMIT 50""")
    rows = cur.fetchall(); done = 0
    for r in rows:
        try:
            meta = r["metadata"] or {}
            mime = MIMEText(r["text_content"] or "")
            mime["To"] = r["channel_user_id"]
            mime["Subject"] = (meta.get("subject") if isinstance(meta, dict) else None) or "Re:"
            raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
            svc.users().messages().send(userId="me", body={"raw": raw}).execute()
            cur.execute("UPDATE channel_messages SET status='sent' WHERE id=%s", (r["id"],))
            done += 1
        except Exception as e:
            print(f"  ! send {r['id']}: {str(e)[:100]}")
    print(f"[email_bridge] send: delivered {done}/{len(rows)} queued replies")
    cur.close(); c.close()


if __name__ == "__main__":
    if "--send" in sys.argv:
        send()
    elif "--inbound" in sys.argv:
        inbound()
    else:
        print(__doc__)
