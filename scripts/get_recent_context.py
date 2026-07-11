#!/usr/bin/env python3
"""get_recent_context.py — recent conversation context for a Leo reply, sourced from the CANONICAL
spine (v_comms_interactions), scoped to the sender (A5-safe).

Supersedes the legacy root-level get_recent_context.py, which queried the Telegram-only `conversations`
table (columns telegram_id/leo_response/sent_to_jonathan) — that store holds NO omnichannel data, so
for a Messenger/WhatsApp/email client it returned empty. The corrected helper reads v_comms_interactions
(channel_messages ∪ leo_interactions ∪ outbound_messages, deploy_823), the one true interaction feed.

A5 isolation: context is scoped to the SENDER's own thread (party_key), and the sender is bound to a
single client_code (A25) — so a reply is never built from another client's messages.
"""
import json
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def recent_context(cur, channel_user_id, client_code, limit=8):
    """Returns {recent_messages, open_action_items} — the sender's recent thread + the client's open items."""
    cur.execute("""
        SELECT direction, ts, preview, channel
          FROM v_comms_interactions
         WHERE party_key = %s
         ORDER BY ts DESC NULLS LAST
         LIMIT %s
    """, (str(channel_user_id), limit))
    messages = [{"direction": r["direction"], "channel": r["channel"],
                 "text": (r["preview"] or "").strip(),
                 "time": r["ts"].isoformat() if r["ts"] else None} for r in cur.fetchall()]
    messages.reverse()  # chronological for the prompt

    action_items = []
    if client_code:
        cur.execute("""
            SELECT description, due_date, priority
              FROM action_items
             WHERE case_file = %s AND status = 'open'
             ORDER BY due_date ASC NULLS LAST
             LIMIT 8
        """, (client_code,))
        action_items = [{"description": r["description"],
                         "due_date": r["due_date"].isoformat() if r["due_date"] else None,
                         "priority": r["priority"]} for r in cur.fetchall()]
    return {"client": client_code, "recent_messages": messages,
            "open_action_items": action_items}


if __name__ == "__main__":
    raw = sys.stdin.read().strip()
    data = json.loads(raw) if raw else {}
    conn = psycopg2.connect(DSN); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    print(json.dumps(recent_context(cur, data.get("channel_user_id"), data.get("client"),
                                    data.get("limit", 8)), default=str))
    cur.close(); conn.close()
