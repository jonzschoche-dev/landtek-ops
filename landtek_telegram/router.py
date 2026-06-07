#!/usr/bin/env python3
"""landtek_telegram/router.py — pulls unprocessed inbox rows and dispatches.

Runs as a long-lived process. Polls telegram_inbox for rows where
processed_at IS NULL, locks each with SELECT FOR UPDATE SKIP LOCKED so
multiple worker instances can run safely, decides which handler claims
the row, calls it, marks processed.

Failure isolation: if a handler raises, the row is marked with the error
and processed_at is still set so we don't infinite-loop. The error stays
visible for debugging.

Cadence: 2-second sleep when idle. Wake immediately when work arrives via
LISTEN/NOTIFY (future enhancement; for now just poll).
"""
from __future__ import annotations
import os
import signal
import sys
import time
import traceback

import psycopg2
import psycopg2.extras

# Make the package importable when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from landtek_telegram.handlers import vault as vault_handler
from landtek_telegram.handlers import fallback as fallback_handler
from landtek_telegram.handlers import llm as llm_handler

PG_DSN = os.environ.get("LANDTEK_TG_PG_DSN",
                        "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
POLL_INTERVAL = float(os.environ.get("LANDTEK_TG_POLL_SECONDS", "2"))
WORKER_NAME = os.environ.get("LANDTEK_TG_WORKER_NAME", "router-default")

SIM_PREFIX = "999000"
DB_GROUP = "-5138695222"

_shutdown = False


def _sigterm(_signum, _frame):
    global _shutdown
    _shutdown = True


signal.signal(signal.SIGTERM, _sigterm)
signal.signal(signal.SIGINT, _sigterm)


def _decide_handler(row):
    """Pick which handler claims this row.

    Order:
      1. Sim probe → drop silently (handled by n8n simulator if still up)
      2. Group chat or known authorized user + vault intent → vault
      3. Other inbound from authorized user → fallback (never-ghost ack)
      4. Telegram system events (my_chat_member, etc.) with no text → skip
    """
    sender_id = row.get("sender_id") or ""
    update_type = row.get("update_type") or ""
    text = (row.get("text_content") or "").strip()

    if sender_id.startswith(SIM_PREFIX):
        return "sim_drop", None

    if update_type in ("my_chat_member", "chat_member", "chat_join_request"):
        return "system_event", None

    if not text and update_type in ("message", "edited_message", "channel_post"):
        # photo/sticker/voice without caption — still a human signal
        return "fallback", fallback_handler

    if not text:
        return "skip_no_content", None

    # Vault handler claims explicit deterministic vault commands
    intent = vault_handler._classify_intent(text)
    if intent != "none":
        return "vault", vault_handler

    # Everything else from a human → LLM handler (real conversation)
    # llm_handler degrades to a one-line acknowledgment if the API is down.
    return "llm", llm_handler


def _process_one(conn, row):
    decision, handler = _decide_handler(row)
    if handler is None:
        return decision, None
    try:
        result = handler.handle(row) or {}
        return result.get("outcome", decision), None
    except Exception as e:
        tb = traceback.format_exc()[:1500]
        print(f"[router] handler {handler.__name__} raised: {e}\n{tb}",
              file=sys.stderr)
        return f"handler_error:{type(e).__name__}", str(e)[:300]


def main():
    print(f"[router] starting worker={WORKER_NAME} poll={POLL_INTERVAL}s")
    while not _shutdown:
        try:
            conn = psycopg2.connect(PG_DSN)
            conn.autocommit = False
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT id, update_id, update_type, chat_id, chat_type, chat_title,
                       sender_id, sender_name, text_content, raw_update
                  FROM telegram_inbox
                 WHERE processed_at IS NULL
                 ORDER BY id
                 LIMIT 25
                 FOR UPDATE SKIP LOCKED
            """)
            rows = cur.fetchall()
            if not rows:
                conn.rollback()
                cur.close(); conn.close()
                time.sleep(POLL_INTERVAL)
                continue

            for row in rows:
                outcome, err = _process_one(conn, row)
                cur.execute("""
                    UPDATE telegram_inbox
                       SET processed_at = NOW(),
                           processed_by = %s,
                           handler = %s,
                           handler_outcome = %s,
                           error_msg = %s
                     WHERE id = %s
                """, (WORKER_NAME,
                      (outcome.split(":", 1)[0] if outcome else "unknown"),
                      outcome, err, row["id"]))
                print(f"[router] inbox#{row['id']} chat={row.get('chat_id')} "
                      f"sender={row.get('sender_id')} text={(row.get('text_content') or '')[:50]!r} "
                      f"-> {outcome}")
            conn.commit()
            cur.close(); conn.close()
        except Exception as e:
            print(f"[router] loop error: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            time.sleep(POLL_INTERVAL * 2)
    print("[router] shutting down cleanly")


if __name__ == "__main__":
    main()
