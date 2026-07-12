#!/usr/bin/env python3
"""telegram_gateway.py — the SOVEREIGN Telegram gateway. Owns @LeoLandtekBot via getUpdates long-polling
(no webhook, no tunnel) and puts Telegram on the same spine as every other channel:

    Telegram --getUpdates--> gateway --> channel_messages (bus) --NOTIFY--> leo_instant --> leo_service
                                    |                                       (local Ollama, memory,
                                    +--> doc-triage command handler          equilibrium, A79, tg_send)
                                         (file/skip/unrelated NNN)

Retires n8n from Telegram conversation. On start it deleteWebhook's (takes the bot from n8n's
leo.hayuma.org/landtek/tg). Conversation replies are produced by the existing leo_instant daemon (the
gateway only lands the message on the bus); triage COMMANDS are applied here (the consumer n8n used to
own — the doc_triage.py PRODUCER is unchanged). Persistent systemd service; degrade-don't-crash.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
TRIAGE_RE = re.compile(r"^\s*(file|skip|unrelated)\s+(\d+)(?:\s+to\s+(\S+))?\s*$", re.I)


def _token():
    try:
        with open("/root/landtek/.env") as f:
            for line in f:
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    return line.strip().split("=", 1)[1]
    except Exception:
        pass
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _api(token, method, **params):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode() if params else None
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode())


def _send(token, chat_id, text):
    try:
        _api(token, "sendMessage", chat_id=chat_id, text=text)
    except Exception as e:
        print(f"[tg_gw] send fail {chat_id}: {str(e)[:80]}", flush=True)


def _ensure(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS telegram_gateway_state (
                     id int PRIMARY KEY DEFAULT 1, last_update_id bigint DEFAULT 0)""")
    cur.execute("INSERT INTO telegram_gateway_state (id,last_update_id) VALUES (1,0) ON CONFLICT (id) DO NOTHING")
    cur.execute("SELECT last_update_id FROM telegram_gateway_state WHERE id=1")
    return cur.fetchone()["last_update_id"]


def _log_inbound(cur, chat_user_id, text):
    """Land a CONVERSATION message on the bus → NOTIFY trigger → leo_instant replies via the sovereign engine."""
    cur.execute("""INSERT INTO channel_messages (channel_id, channel_user_id, direction, text_content, status)
                   VALUES ((SELECT id FROM channels WHERE name='telegram'), %s, 'inbound', %s, 'received')""",
                (str(chat_user_id), text))


def _handle_triage(cur, token, chat_id, text):
    """Apply a doc-triage command (the consumer n8n used to own). Returns True if it was a triage command.
    file NNN to MATTER -> documents.matter_code (fires autolink) · skip NNN -> defer 7d · unrelated NNN."""
    m = TRIAGE_RE.match(text)
    if not m:
        return False
    action, doc_id, matter = m.group(1).lower(), int(m.group(2)), m.group(3)
    cur.execute("SELECT id FROM documents WHERE id=%s", (doc_id,))
    if not cur.fetchone():
        _send(token, chat_id, f"No document #{doc_id} found.")
        return True
    if action == "file":
        if not matter:
            _send(token, chat_id, f"Which matter? e.g. `file {doc_id} to MWK-CV26360`")
            return True
        cur.execute("SELECT 1 FROM matters WHERE matter_code=%s", (matter,))
        if not cur.fetchone():
            _send(token, chat_id, f"Unknown matter '{matter}'. Filing aborted — check the code.")
            return True
        cur.execute("UPDATE documents SET matter_code=%s WHERE id=%s", (matter, doc_id))  # fires autolink trigger
        _send(token, chat_id, f"✅ Filed doc {doc_id} → {matter} (autolink fired).")
    elif action == "skip":
        cur.execute("""INSERT INTO doc_triage_pushed (doc_id, telegram_ok, suggestion)
                       VALUES (%s, true, 'skip_defer_7d')""", (doc_id,))
        _send(token, chat_id, f"⏭ Skipped doc {doc_id} (deferred 7 days).")
    elif action == "unrelated":
        cur.execute("UPDATE documents SET matter_code='UNRELATED' WHERE id=%s", (doc_id,))
        _send(token, chat_id, f"🚫 Marked doc {doc_id} as unrelated (not case-relevant).")
    return True


def _process_update(cur, token, upd):
    msg = upd.get("message") or {}
    text = (msg.get("text") or "").strip()
    frm = (msg.get("from") or {}).get("id")
    chat = (msg.get("chat") or {}).get("id")
    if not text or frm is None:
        return                                   # ignore non-text / service updates for now
    if _handle_triage(cur, token, chat, text):
        return                                   # a command — handled here, not conversation
    _log_inbound(cur, frm, text)                 # conversation — the engine (leo_instant) answers it
    print(f"[tg_gw] conversation from {frm} → bus", flush=True)


def main():
    token = _token()
    if not token:
        sys.exit("[tg_gw] TELEGRAM_BOT_TOKEN not set")
    # take the bot from n8n so getUpdates works (the deliberate cut)
    try:
        _api(token, "deleteWebhook", drop_pending_updates="false")
        print("[tg_gw] webhook deleted — gateway now owns the bot via getUpdates", flush=True)
    except Exception as e:
        print(f"[tg_gw] deleteWebhook warn: {str(e)[:80]}", flush=True)
    while True:
        conn = None
        try:
            conn = psycopg2.connect(DSN); conn.autocommit = True
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            offset = _ensure(cur) + 1
            print(f"[tg_gw] polling from offset {offset}", flush=True)
            while True:
                res = _api(token, "getUpdates", offset=offset, timeout=25,
                           allowed_updates=json.dumps(["message"]))
                for upd in res.get("result", []):
                    offset = upd["update_id"] + 1
                    try:
                        _process_update(cur, token, upd)
                    except Exception as e:
                        print(f"[tg_gw] update {upd.get('update_id')} err: {str(e)[:100]}", flush=True)
                    cur.execute("UPDATE telegram_gateway_state SET last_update_id=%s WHERE id=1",
                                (upd["update_id"],))
        except Exception as e:
            print(f"[tg_gw] reconnect after: {str(e)[:100]}", flush=True)
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
            time.sleep(5)


if __name__ == "__main__":
    main()
