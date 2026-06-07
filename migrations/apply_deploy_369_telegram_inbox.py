#!/usr/bin/env python3
"""apply_deploy_369_telegram_inbox.py — bulletproof Telegram inbox table.

The substrate-replacement story:
  After 5 hours of n8n failure modes today (sim-guard syntax bug, ai_tool
  wiring bug, Anthropic cap, container restarts, task broker auth, webhook
  secret desync, bot privacy cache), Jonathan named the obvious:
  "we cant be this fragile."

The new architecture (deploy_369+):
  Telegram POSTs land in a Flask receiver. EVERY inbound writes one row to
  telegram_inbox and the receiver ACKs in <50ms. A separate router polls
  unprocessed rows and dispatches to handlers (vault, llm, etc.).
  No message can be lost — even if the router crashes, the row stays.

This migration creates the inbox table + supporting indexes. The receiver
and router are separate files (telegram_inbox.py, telegram_router.py).

Idempotent.
"""
from __future__ import annotations
import os
import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS telegram_inbox (
            id            BIGSERIAL PRIMARY KEY,
            received_at   timestamptz NOT NULL DEFAULT now(),
            update_id     bigint,
            update_type   text,
            chat_id       text,
            chat_type     text,
            chat_title    text,
            sender_id     text,
            sender_name   text,
            text_content  text,
            raw_update    jsonb NOT NULL,
            processed_at  timestamptz,
            processed_by  text,
            handler       text,
            handler_outcome text,
            error_msg     text
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS telegram_inbox_unprocessed_idx
            ON telegram_inbox (received_at)
            WHERE processed_at IS NULL
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS telegram_inbox_chat_idx
            ON telegram_inbox (chat_id, received_at DESC)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS telegram_inbox_update_id_idx
            ON telegram_inbox (update_id)
    """)
    # Outbox retry table for failed sends
    cur.execute("""
        CREATE TABLE IF NOT EXISTS telegram_outbox_retry (
            id          BIGSERIAL PRIMARY KEY,
            queued_at   timestamptz NOT NULL DEFAULT now(),
            chat_id     text NOT NULL,
            text        text NOT NULL,
            source      text,
            recipient_name text,
            attempt_count int NOT NULL DEFAULT 0,
            next_attempt_at timestamptz NOT NULL DEFAULT now(),
            last_error  text,
            sent_at     timestamptz
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS telegram_outbox_retry_due_idx
            ON telegram_outbox_retry (next_attempt_at)
            WHERE sent_at IS NULL
    """)
    print("[deploy_369] telegram_inbox + telegram_outbox_retry tables ready")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
