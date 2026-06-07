"""landtek_telegram — bulletproof Telegram pipeline (deploy_369).

Replaces n8n as the load-bearing path for inbound Telegram traffic.

Components:
    inbox.py    — Flask receiver; writes every update to telegram_inbox,
                  ACKs Telegram in <50ms. Cannot lose a message.
    router.py   — Worker; polls unprocessed inbox rows, dispatches to
                  handlers, marks processed_at.
    handlers/   — One file per handler (vault, llm, sim_drop, etc.).
                  Each is a pure function: (inbox_row) -> outcome.
    outbox_retry.py — Worker; replays failed sends from telegram_outbox_retry.

systemd:
    landtek-telegram-inbox.service   (port 8766)
    landtek-telegram-router.service  (poll every 2s)
    landtek-telegram-outbox.service  (poll every 10s)
"""
