#!/usr/bin/env python3
"""landtek_core — shared helpers used across the codebase.

Single source of truth for:
  • DSN (Postgres connection string)
  • .env loading
  • API key + token retrieval
  • Jonathan's Telegram chat id
  • Bare Telegram send (NOT the queued one — use tg_inquiry_queue for inquiries)
  • Common DB cursor pattern

Replaces the ~57 files hard-coding DSN, ~29 reimplementing env-parsing, ~11
redefining load_token. Import what you need:

    from landtek_core import DSN, db, env, get, tg_send_raw

    with db() as cur:
        cur.execute("SELECT 1")
"""
import contextlib
import os
from functools import lru_cache

# ─── Constants ────────────────────────────────────────────────────────────
DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
JONATHAN_TG = "6513067717"
ENV_PATH = "/root/landtek/.env"


# ─── Env loading ──────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def env() -> dict:
    """Return parsed .env as a dict. Cached for the process lifetime."""
    out = {}
    try:
        with open(ENV_PATH) as f:
            for line in f:
                if "=" in line and not line.lstrip().startswith("#"):
                    k, _, v = line.strip().partition("=")
                    out[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    # Overlay actual environment so docker-passed vars win
    for k, v in os.environ.items():
        if k.isupper() and len(k) > 2:
            out.setdefault(k, v)
    return out


def get(key: str, default=None) -> str | None:
    """Shortcut: env()[key] with fallback to default."""
    return env().get(key, default)


# ─── DB helpers ───────────────────────────────────────────────────────────
@contextlib.contextmanager
def db(real_dict=True):
    """Yield an autocommit RealDictCursor; auto-close cursor + conn on exit.

    Usage:
        with db() as cur:
            cur.execute("SELECT * FROM matters")
            rows = cur.fetchall()
    """
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cursor_factory = psycopg2.extras.RealDictCursor if real_dict else None
    cur = conn.cursor(cursor_factory=cursor_factory) if cursor_factory else conn.cursor()
    try:
        yield cur
    finally:
        cur.close()
        conn.close()


# ─── Telegram (bare send, not queued) ─────────────────────────────────────
def tg_send_raw(text: str, *, reply_to: int | None = None,
                chat_id: str = JONATHAN_TG, parse_mode: str = "HTML"):
    """Send a Telegram message directly (bypasses the inquiry queue).

    Reserved for: report deliveries (/timeline, /status), system alerts that
    are not asks (no answer expected). For any INQUIRY that needs a response,
    INSERT into tg_inquiry_queue and let tg_dispatcher fire it.

    Returns (ok: bool, info_or_msgid).
    """
    import requests
    token = get("TELEGRAM_BOT_TOKEN")
    if not token:
        return False, "no_token"
    body = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode,
            "disable_web_page_preview": True}
    if reply_to:
        body["reply_to_message_id"] = reply_to
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json=body, timeout=15)
        j = r.json()
    except Exception as e:
        return False, str(e)[:200]
    if not j.get("ok"):
        return False, j.get("description", "")[:200]
    return True, j["result"]["message_id"]


# ─── Anthropic / Gemini client helpers ────────────────────────────────────
def anthropic_client():
    """Return an anthropic.Anthropic client configured with the API key."""
    import anthropic
    return anthropic.Anthropic(api_key=get("ANTHROPIC_API_KEY"))


def gemini_configure():
    """Configure google.generativeai with the primary GEMINI_API_KEY."""
    import google.generativeai as genai
    genai.configure(api_key=get("GEMINI_API_KEY"))


if __name__ == "__main__":
    # Self-test
    print("DSN:", DSN[:40] + "...")
    print("env keys:", len(env()))
    print("ANTHROPIC_API_KEY set:", bool(get("ANTHROPIC_API_KEY")))
    print("TELEGRAM_BOT_TOKEN set:", bool(get("TELEGRAM_BOT_TOKEN")))
    with db() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM matters")
        print("matters:", cur.fetchone()["n"])
