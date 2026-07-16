#!/usr/bin/env python3
"""landtek_telegram/inbox.py — bulletproof Telegram webhook receiver.

Runs as a Flask service on port 8766. Single responsibility: receive every
Telegram update and persist it before responding 200. Cannot lose a message
even if the process dies a moment later — the row is in Postgres before
the ACK.

The router (telegram_router.py) is a separate process that polls
telegram_inbox for unprocessed rows.

Endpoint:
    POST /landtek/tg — Telegram webhook target. Returns 200 unconditionally
    once the row is written (we never make Telegram retry a duplicate).

    GET /healthz — liveness check.

Telegram setWebhook:
    URL: https://leo.hayuma.org/landtek/tg
    secret_token: optional; if set, validated via X-Telegram-Bot-Api-Secret-Token

Env vars:
    LANDTEK_TG_PG_DSN     — Postgres DSN (default: same as n8n)
    LANDTEK_TG_SECRET     — Optional shared secret for setWebhook
    LANDTEK_TG_PORT       — Listen port (default 8766)
"""
from __future__ import annotations
import json
import os
import sys
import traceback

import psycopg2
from flask import Flask, request, jsonify

PG_DSN = os.environ.get("LANDTEK_TG_PG_DSN",
                        "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
SHARED_SECRET = os.environ.get("LANDTEK_TG_SECRET", "")
PORT = int(os.environ.get("LANDTEK_TG_PORT", "8766"))

app = Flask(__name__)


def _extract_message_fields(upd):
    """Pull (update_type, chat info, sender, text) from a Telegram update."""
    update_type = None
    chat = {}
    sender = {}
    text = None

    for key in ("message", "edited_message", "channel_post",
                "edited_channel_post"):
        if key in upd and isinstance(upd[key], dict):
            update_type = key
            msg = upd[key]
            chat = msg.get("chat") or {}
            sender = msg.get("from") or {}
            text = msg.get("text") or msg.get("caption")
            return update_type, chat, sender, text

    for key in ("callback_query",):
        if key in upd and isinstance(upd[key], dict):
            update_type = key
            cq = upd[key]
            chat = (cq.get("message") or {}).get("chat") or {}
            sender = cq.get("from") or {}
            text = cq.get("data")
            return update_type, chat, sender, text

    for key in ("my_chat_member", "chat_member", "chat_join_request"):
        if key in upd and isinstance(upd[key], dict):
            update_type = key
            obj = upd[key]
            chat = obj.get("chat") or {}
            sender = obj.get("from") or {}
            return update_type, chat, sender, text

    return update_type or "unknown", chat, sender, text


@app.route("/healthz")
def healthz():
    try:
        conn = psycopg2.connect(PG_DSN)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close(); conn.close()
        return jsonify(ok=True, service="landtek-tg-inbox"), 200
    except Exception as e:
        return jsonify(ok=False, error=str(e)[:200]), 500


@app.route("/landtek/tg", methods=["POST"])
def tg_webhook():
    """Receive a Telegram update. Write to inbox. ACK 200.

    Returns 200 even on duplicate update_id (idempotent via UNIQUE-ish dedup
    in router) so Telegram never retries.
    """
    # Optional shared-secret check
    if SHARED_SECRET:
        hdr = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if hdr != SHARED_SECRET:
            # Wrong secret — quietly drop, return 200 so Telegram doesn't
            # spam-retry (the operator should fix the secret out-of-band)
            return "", 200

    try:
        upd = request.get_json(force=True, silent=True) or {}
    except Exception:
        upd = {}

    update_id = upd.get("update_id")
    update_type, chat, sender, text = _extract_message_fields(upd)

    chat_id = str(chat.get("id")) if chat.get("id") is not None else None
    chat_type = chat.get("type")
    chat_title = chat.get("title") or chat.get("first_name") or chat.get("username")
    sender_id = str(sender.get("id")) if sender.get("id") is not None else None
    # Telegram first_name is user-editable — prefer locked channel_users.display_name
    # for approved/known identities so re-named accounts don't mislabel the principal.
    tg_name = (" ".join(filter(None, [sender.get("first_name"),
                                      sender.get("last_name")])).strip()
               or sender.get("username"))
    sender_name = tg_name

    try:
        conn = psycopg2.connect(PG_DSN); conn.autocommit = True
        cur = conn.cursor()
        if sender_id:
            cur.execute("""
                SELECT cu.display_name
                  FROM channel_users cu
                  JOIN channels c ON c.id = cu.channel_id
                 WHERE c.name = 'telegram' AND cu.channel_user_id = %s
                   AND cu.onboarding_state = 'approved'
                   AND coalesce(cu.display_name, '') <> ''
                 LIMIT 1
            """, (sender_id,))
            row = cur.fetchone()
            if row and row[0]:
                sender_name = row[0]
        cur.execute("""
            INSERT INTO telegram_inbox
                (update_id, update_type, chat_id, chat_type, chat_title,
                 sender_id, sender_name, text_content, raw_update)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
        """, (update_id, update_type, chat_id, chat_type, chat_title,
              sender_id, sender_name, text, json.dumps(upd)))
        inbox_id = cur.fetchone()[0]
        cur.close(); conn.close()
        return jsonify(ok=True, inbox_id=inbox_id), 200
    except Exception as e:
        # Even on DB error, return 200 — we don't want Telegram retry storms.
        # Log the failure to stderr so systemd journal catches it.
        print(f"[inbox] DB WRITE FAILED: {e!r}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify(ok=False, error="db_write_failed"), 200


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, threaded=True)
