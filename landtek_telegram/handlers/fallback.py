#!/usr/bin/env python3
"""landtek_telegram/handlers/fallback.py — never-ghost reply for anything
the deterministic handlers don't claim.

Rule N (never ghost): every human message gets a reply. For non-vault,
non-sim, non-empty messages, we acknowledge with a warm one-liner that
makes clear who's authorized to drive what.

Group chat (DB, -5138695222) gets a vault-focused gentle redirect.
Jonathan's private chat gets an "ack + tell me what you need" line.
Kristyle's direct chat (if she ever uses it instead of the group) gets a
filing-assistant-aware ack.

This is deliberately NOT an LLM call — keeps latency near zero and removes
another dependency. When we want LLM reasoning, that's a separate handler
(llm.py) and we add it later.
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, "/root/landtek/scripts")
try:
    from tg_send import send as tg_send
except Exception:
    tg_send = None

DB_GROUP = "-5138695222"
JONATHAN = "6513067717"
KRISTYLE = "5992075757"


def _reply(chat_id, text):
    if tg_send is None:
        print(f"[fallback] would reply to {chat_id}: {text[:120]}")
        return False
    ok, _ = tg_send(chat_id=str(chat_id), text=text, source="fallback_handler",
                    override_pacing=True, override_rate_limit=True,
                    human_readable=False)
    return ok


def handle(row):
    chat_id = row.get("chat_id")
    sender_id = row.get("sender_id")
    text = (row.get("text_content") or "").strip()
    sender_name = row.get("sender_name") or "there"
    chat_type = row.get("chat_type")

    if not text:
        # Empty message body — likely a Telegram system event already handled
        # by another routing path. Skip without reply.
        return {"handler": "fallback", "outcome": "skip_empty", "reply_sent": False}

    if chat_id == DB_GROUP:
        # Vault coordination channel
        _reply(chat_id,
               f"Got that, {sender_name}. The DB group is where we coordinate "
               "the physical vault. Try things like 'vault AFF-1 affidavit "
               "of loss for the 4497 case', 'queue', 'find AFF-1', or "
               "'missing matter:MWK-ARTA-1210'.")
        return {"handler": "fallback", "outcome": "db_group_redirect",
                "reply_sent": True}

    if sender_id == JONATHAN and chat_type == "private":
        _reply(chat_id, f"Got it. What would you like me to do?")
        return {"handler": "fallback", "outcome": "jonathan_ack",
                "reply_sent": True}

    if sender_id == KRISTYLE:
        _reply(chat_id, f"Hi Kristyle. I'm here for filing — try 'queue' to "
                       "see what's pending, or just describe a vault entry.")
        return {"handler": "fallback", "outcome": "kristyle_ack",
                "reply_sent": True}

    # Anyone else — polite acknowledgment, no info leakage
    _reply(chat_id, "Got your message. I'll have someone follow up with you "
                   "if it's something I can help with.")
    return {"handler": "fallback", "outcome": "stranger_ack",
            "reply_sent": True}
