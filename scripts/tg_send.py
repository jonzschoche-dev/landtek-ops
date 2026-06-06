#!/usr/bin/env python3
"""tg_send.py — single chokepoint for system-originated Telegram sends.

Every script/briefer/recovery/manual_ops send MUST use this helper. It:
  1. Sanitizes outbound text per Rule S14 (plain language, no HTML/markdown/lists,
     ≤280 chars). On for Jonathan by default; opt-out via `human_readable=False`.
  2. Blocks chained messages to Jonathan (Rule S14 #3): if his last outbound has
     no inbound reply since, the next outbound is REJECTED unless
     `override_pacing=True`.
  3. Checks rate limits (N messages per recipient per window).
  4. Logs to outbound_messages and outbound_blocks.
  5. Sends via Telegram API.
  6. Returns (ok, response_or_error).

Usage:
  from tg_send import send
  ok, info = send(chat_id="5992075757", text="Hi", source="manual_ops",
                  recipient_name="Joy Kristyle")

  # Plain-text Jonathan send (default — sanitize on, pacing on):
  ok, info = send(chat_id="6513067717", text="Mediation went well.",
                  source="manual_ops", recipient_name="Jonathan")

  # P0 override (use sparingly — caller owns the consequence):
  ok, info = send(chat_id="6513067717", text="orchestrator down 20m",
                  source="watchdog", override_pacing=True, override_rate_limit=True)
"""
import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# Rate limits: max N messages per chat_id per window_seconds
# Jonathan gets a higher cap because he's actively interacting
RATE_LIMITS = {
    "default": (3, 15 * 60),       # non-Jonathan: 3 messages per 15 min
    "6513067717": (12, 30 * 60),    # Jonathan: 12 per 30 min
}

JONATHAN_CHAT = "6513067717"
HUMAN_MESSAGE_CAP = 280  # chars; matches deploy_329 strict rails


# ── Rule S14: human-language sanitizer ─────────────────────────────────────
_HTML_TAG       = re.compile(r"<[^>]+>")
_MD_BOLD_ITAL   = re.compile(r"[*_~]+")
_MD_CODE        = re.compile(r"`+")
_BULLET_PREFIX  = re.compile(r"^\s*[-*•·▪▫►◦]\s+", re.MULTILINE)
_NUM_PREFIX     = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
_MULTI_SPACE    = re.compile(r"\s+")


def sanitize_for_human(text: str, cap: int = HUMAN_MESSAGE_CAP) -> str:
    """Strip markup and list scaffolding so a human reads it as one sentence.

    Removes: HTML tags, markdown bold/italic, code backticks, bullet markers,
    numbered-list prefixes. Collapses newlines + multi-spaces. Truncates at
    `cap` chars on a word boundary with an ellipsis.
    """
    if not text:
        return ""
    t = _HTML_TAG.sub("", text)
    t = _BULLET_PREFIX.sub("", t)
    t = _NUM_PREFIX.sub("", t)
    t = _MD_BOLD_ITAL.sub("", t)
    t = _MD_CODE.sub("", t)
    t = _MULTI_SPACE.sub(" ", t).strip()
    if len(t) > cap:
        t = t[: cap - 1].rsplit(" ", 1)[0] + "…"
    return t


# ── Rule S14: pacing — block double-tap to Jonathan ────────────────────────
def _is_jonathan_awaiting_reply(cur) -> bool:
    """True if Jonathan's last successful outbound has no inbound reply since.

    Cleared when leo_interactions records an inbound from him (sender_id =
    6513067717) with timestamp >= last outbound sent_at. If we've never sent
    him anything, returns False (no pacing constraint applies).
    """
    cur.execute(
        """
        SELECT MAX(sent_at) AS last_out
          FROM outbound_messages
         WHERE chat_id = %s AND success = true
        """,
        (JONATHAN_CHAT,),
    )
    row = cur.fetchone() or {}
    last_out = row.get("last_out")
    if not last_out:
        return False
    cur.execute(
        """
        SELECT 1 FROM leo_interactions
         WHERE sender_id = %s AND timestamp > %s
         LIMIT 1
        """,
        (JONATHAN_CHAT, last_out),
    )
    return cur.fetchone() is None


def _bot_token():
    for k in ("TG_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "BOT_TOKEN"):
        v = os.environ.get(k)
        if v:
            return v
    p = Path("/root/landtek/.env")
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() in ("TG_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "BOT_TOKEN"):
                return v.strip().strip('"').strip("'")
    return None


def _check_rate(cur, chat_id, source):
    cap, window = RATE_LIMITS.get(chat_id, RATE_LIMITS["default"])
    cur.execute(
        """
        SELECT COUNT(*) AS n
          FROM outbound_messages
         WHERE chat_id = %s
           AND sent_at > now() - (%s || ' seconds')::interval
           AND success = true
        """,
        (chat_id, window),
    )
    n = cur.fetchone()["n"]
    if n >= cap:
        return False, f"rate_limit: {n}/{cap} in last {window}s for chat {chat_id}"
    return True, None


def send(chat_id, text, source, recipient_name=None,
         parse_mode=None,  # changed: default plain text per Rule S14
         disable_web_page_preview=True,
         override_rate_limit=False,
         override_pacing=False,
         human_readable=None):  # auto-True for Jonathan; explicit override otherwise
    """Send a Telegram message through the chokepoint.

    Defaults follow Rule S14:
      - parse_mode=None (plain text)
      - human_readable applied automatically for Jonathan (chat_id 6513067717)
      - pacing enforced for Jonathan unless override_pacing=True

    For non-Jonathan recipients, human_readable defaults to False to preserve
    formatted templates used in client-facing replies. Callers may pass
    human_readable=True explicitly to sanitize anyway.
    """
    chat_id = str(chat_id)
    token = _bot_token()
    if not token:
        return False, "no_bot_token"

    # Default human_readable based on recipient
    if human_readable is None:
        human_readable = (chat_id == JONATHAN_CHAT)

    # Apply Rule S14 sanitizer if requested
    if human_readable:
        text = sanitize_for_human(text)

    chash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    preview = text.replace("\n", " | ")[:200]

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Rule S14 #3 — pacing check (Jonathan only, defaults on)
    if chat_id == JONATHAN_CHAT and not override_pacing:
        if _is_jonathan_awaiting_reply(cur):
            reason = "S14_awaiting_reply: prior message to Jonathan not yet replied to"
            cur.execute(
                "INSERT INTO outbound_blocks (chat_id, source, reason, content_preview) VALUES (%s, %s, %s, %s)",
                (chat_id, source, reason, preview),
            )
            cur.close()
            conn.close()
            return False, reason

    # Rate limit check
    if not override_rate_limit:
        ok, reason = _check_rate(cur, chat_id, source)
        if not ok:
            cur.execute(
                "INSERT INTO outbound_blocks (chat_id, source, reason, content_preview) VALUES (%s, %s, %s, %s)",
                (chat_id, source, reason, preview),
            )
            cur.close()
            conn.close()
            return False, reason

    # Send via Telegram
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if parse_mode:  # only set if explicit — Rule S14 default is plain
        payload["parse_mode"] = parse_mode

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        body = resp.read().decode("utf-8")
        ok = resp.status == 200
        err = None
    except Exception as e:
        ok = False
        body = ""
        err = str(e)[:300]

    cur.execute(
        """
        INSERT INTO outbound_messages
            (chat_id, recipient_name, source, content_hash, content_preview, success, error)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (chat_id, recipient_name, source, chash, preview, ok, err),
    )
    cur.close()
    conn.close()
    return ok, body if ok else err


if __name__ == "__main__":
    # CLI: tg_send.py <chat_id> <source> <text>
    if len(sys.argv) < 4:
        print("usage: tg_send.py <chat_id> <source> <text>")
        sys.exit(1)
    ok, info = send(chat_id=sys.argv[1], source=sys.argv[2], text=sys.argv[3])
    print("ok=", ok)
    print(info[:500])
