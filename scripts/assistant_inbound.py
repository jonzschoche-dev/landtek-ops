#!/usr/bin/env python3
"""assistant_inbound.py — the SPONGE: two-way calendar interaction over Telegram.

The other half of the scheduling assistant (docs/scheduling_assistant_design.md §7B).
Listens on a DEDICATED assistant bot (ASSISTANT_BOT_TOKEN — never @LeoLandTekBot, whose
inbound belongs to n8n/Leo + the simulator). Internal-only: it converses with Jonathan
(chat 6513067717) and no one else; strangers are logged and ignored (no reply — the bot
does not confirm its own existence to outsiders).

A sponge never drops information:
  * EVERY inbound from Jonathan is stored verbatim on the channel bus
    (channel_messages, direction='inbound') before any parsing.
  * If a date/commitment is spotted (deterministic regex, conservative), the assistant
    PROPOSES a calendar entry and waits for yes/no — confirm-before-write, never guesses.
  * If nothing parses, the message is absorbed into chat_notes ("Noted.") — kept, not lost.

Intents (deterministic-first, no LLM):
  "what's on / upcoming / calendar / week / schedule"  → the live agenda (next items)
  "pulse / coverage"                                   → timeline_coverage summary
  <text with a recognizable date>                      → propose add-to-calendar (yes/no)
  "yes" / "no"                                         → resolve the pending proposal
  anything else                                        → absorbed as a note

Governance: internal-only (operator chat hard-gated) · confirm-before-write · client
NEVER guessed (a confirmed item lands untagged unless a matter code was explicit) ·
plain-text replies (S14 spirit; a direct reply to the operator's own message is the
reply-flow, not an unsolicited push) · degrade-don't-crash (no token → clean exit 0).

Usage:
  python3 scripts/assistant_inbound.py --daemon       # long-poll loop (systemd)
  python3 scripts/assistant_inbound.py --once         # single poll pass
  python3 scripts/assistant_inbound.py --test "msg"   # parse-only: no telegram, no writes
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import psycopg2

sys.path.insert(0, "/root/landtek/scripts")

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
ENV_PATH = "/root/landtek/.env"
JONATHAN_CHAT_ID = "6513067717"
CHANNEL_NAME = "assistant_telegram"
TZ = "Asia/Manila"
MANILA_UTC_OFFSET = 8  # PH has no DST
DEFAULT_HOUR = 9  # deploy_276 convention: date-only → 9:00 AM Manila

MONTHS = {m.lower(): i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}
for m in list(MONTHS):
    MONTHS[m[:3]] = MONTHS[m]
WEEKDAYS = {d: i for i, d in enumerate(
    ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])}


def load_env():
    env = {}
    try:
        with open(ENV_PATH) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.strip().partition("=")
                    env[k] = v
    except FileNotFoundError:
        pass
    return env


def manila_today():
    return (datetime.now(timezone.utc) + timedelta(hours=MANILA_UTC_OFFSET)).date()


# ── deterministic date extraction (conservative: exactly one clear date, else None) ──
def extract_date(text):
    t = text.lower()
    today = manila_today()
    found = []

    for m in re.finditer(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", t):  # ISO
        try:
            found.append(datetime(int(m[1]), int(m[2]), int(m[3])).date())
        except ValueError:
            pass
    for m in re.finditer(  # "Aug 20" / "August 20" (optional year)
            r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:\s*,?\s*(20\d{2}))?\b", t):
        mon = MONTHS.get(m[1])
        if mon:
            yr = int(m[3]) if m[3] else today.year
            try:
                d = datetime(yr, mon, int(m[2])).date()
                if not m[3] and d < today:  # bare "Aug 20" already past → next year
                    d = datetime(yr + 1, mon, int(m[2])).date()
                found.append(d)
            except ValueError:
                pass
    for m in re.finditer(  # "20 Aug"
            r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:\s*,?\s*(20\d{2}))?\b", t):
        mon = MONTHS.get(m[2])
        if mon:
            yr = int(m[3]) if m[3] else today.year
            try:
                d = datetime(yr, mon, int(m[1])).date()
                if not m[3] and d < today:
                    d = datetime(yr + 1, mon, int(m[1])).date()
                found.append(d)
            except ValueError:
                pass
    if re.search(r"\btomorrow\b", t):
        found.append(today + timedelta(days=1))
    if re.search(r"\btoday\b", t):
        found.append(today)
    m = re.search(r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", t)
    if m:
        wd = WEEKDAYS[m[1]]
        delta = (wd - today.weekday()) % 7
        found.append(today + timedelta(days=delta + (7 if delta == 0 else 0)))
    m = re.search(r"\bon\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", t)
    if m:
        wd = WEEKDAYS[m[1]]
        delta = (wd - today.weekday()) % 7
        found.append(today + timedelta(days=delta or 7))

    uniq = sorted(set(found))
    return uniq[0] if len(uniq) == 1 else None  # conservative: exactly one


QUERY_RE = re.compile(r"\b(what'?s?\s+(on|up|coming)|upcoming|calendar|schedule|this week|my week|agenda)\b", re.I)
PULSE_RE = re.compile(r"\b(pulse|coverage)\b", re.I)
YES_RE = re.compile(r"^\s*(yes|y|yep|confirm|ok|okay|go)\s*[.!]?\s*$", re.I)
NO_RE = re.compile(r"^\s*(no|n|nope|cancel|skip)\s*[.!]?\s*$", re.I)


def classify(text):
    """Return (intent, payload). Deterministic, ordered."""
    if YES_RE.match(text):
        return ("confirm", None)
    if NO_RE.match(text):
        return ("reject", None)
    if QUERY_RE.search(text):
        return ("query_agenda", None)
    if PULSE_RE.search(text):
        return ("query_pulse", None)
    d = extract_date(text)
    if d:
        return ("propose_event", d)
    return ("absorb", None)


# ── infra ────────────────────────────────────────────────────────────────
def db():
    return psycopg2.connect(DSN)


def ensure_schema(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS assistant_proposals (
            id          SERIAL PRIMARY KEY,
            chat_id     TEXT NOT NULL,
            kind        TEXT NOT NULL DEFAULT 'calendar_event',
            title       TEXT,
            event_date  DATE,
            raw_text    TEXT,
            status      TEXT DEFAULT 'pending',   -- pending|confirmed|rejected|expired
            created_at  TIMESTAMPTZ DEFAULT now(),
            resolved_at TIMESTAMPTZ
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS assistant_state (
            key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMPTZ DEFAULT now()
        )""")


def bus_ids(cur):
    """Resolve (channel_id, channel_user_id) for the assistant channel + Jonathan."""
    cur.execute("SELECT id FROM channels WHERE name=%s", (CHANNEL_NAME,))
    row = cur.fetchone()
    if not row:
        cur.execute(
            "INSERT INTO channels (name, provider, auth_secret_ref, active, notes) "
            "VALUES (%s,'BotAPI','ASSISTANT_BOT_TOKEN', false, "
            "'Dedicated scheduling-assistant bot — internal-only (operator chat). "
            "NOT @LeoLandTekBot.') RETURNING id", (CHANNEL_NAME,))
        row = cur.fetchone()
    ch_id = row[0]
    cur.execute("SELECT id FROM channel_users WHERE channel_id=%s AND channel_user_id=%s",
                (ch_id, JONATHAN_CHAT_ID))
    row = cur.fetchone()
    if not row:
        cur.execute(
            "INSERT INTO channel_users (channel_id, channel_user_id, display_name, "
            "mapped_operator, role, authorized, authorized_at, authorized_by) "
            "VALUES (%s,%s,'Jonathan Zschoche', true, 'owner', true, now(), 'assistant_inbound bootstrap') "
            "RETURNING id", (ch_id, JONATHAN_CHAT_ID))
        row = cur.fetchone()
    return ch_id, row[0]


def bus_log(cur, ch_id, cu_id, direction, text, ext_id=None, status="received"):
    cur.execute(
        "INSERT INTO channel_messages (channel_id, channel_user_id, direction, "
        "external_msg_id, text_content, status) VALUES (%s,%s,%s,%s,%s,%s)",
        (ch_id, cu_id, direction, str(ext_id) if ext_id else None, text, status))


def sanitize(text, cap=400):
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[*_`#]+", "", text)
    return text[:cap]


def tg_api(token, method, **params):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=70) as r:
        return json.load(r)


def reply(cur, token, ch_id, cu_id, text):
    text = sanitize(text)
    tg_api(token, "sendMessage", chat_id=JONATHAN_CHAT_ID, text=text)
    bus_log(cur, ch_id, cu_id, "outbound", text, status="sent")


# ── intent handlers ──────────────────────────────────────────────────────
def agenda_reply(cur):
    try:
        from assistant_cadence import get_agenda, compose_upcoming
        items = get_agenda(cur)
        return compose_upcoming(items, manila_today())
    except Exception as e:  # noqa: BLE001
        return f"Couldn't read the agenda right now ({str(e)[:60]})."


def pulse_reply():
    import subprocess
    try:
        out = subprocess.run(
            [sys.executable, "/root/landtek/scripts/timeline_coverage.py", "--summary"],
            capture_output=True, text=True, timeout=60)
        return out.stdout.strip() or "Pulse report unavailable."
    except Exception as e:  # noqa: BLE001
        return f"Pulse report unavailable ({str(e)[:60]})."


def propose(cur, chat_id, text, d):
    # one pending proposal at a time — a new one supersedes (expires) the old
    cur.execute("UPDATE assistant_proposals SET status='expired', resolved_at=now() "
                "WHERE chat_id=%s AND status='pending'", (chat_id,))
    title = sanitize(text, 180)
    cur.execute(
        "INSERT INTO assistant_proposals (chat_id, title, event_date, raw_text) "
        "VALUES (%s,%s,%s,%s)", (chat_id, title, d, text))
    return (f"Add to calendar: \"{title[:80]}\" on {d.strftime('%b %-d, %Y')}? "
            f"Reply yes or no.")


def confirm(cur, chat_id):
    cur.execute("SELECT id, title, event_date, raw_text FROM assistant_proposals "
                "WHERE chat_id=%s AND status='pending' ORDER BY id DESC LIMIT 1", (chat_id,))
    row = cur.fetchone()
    if not row:
        return "Nothing pending to confirm."
    pid, title, d, raw = row
    # 9:00 AM Manila (deploy_276 convention), stored tz-aware
    start = datetime(d.year, d.month, d.day, DEFAULT_HOUR,
                     tzinfo=timezone(timedelta(hours=MANILA_UTC_OFFSET)))
    # client/matter NEVER guessed — lands untagged; calendar_sync marks it UNRESOLVED
    cur.execute(
        "INSERT INTO calendar_events (title, description, start_at, source, sender_id, status) "
        "VALUES (%s,%s,%s,'assistant',%s,'scheduled') RETURNING id",
        (title[:200], f"Captured by the scheduling assistant from: {raw[:500]}",
         start, chat_id))
    ev_id = cur.fetchone()[0]
    cur.execute("UPDATE assistant_proposals SET status='confirmed', resolved_at=now() "
                "WHERE id=%s", (pid,))
    return (f"Done — \"{title[:60]}\" is on the calendar for "
            f"{d.strftime('%b %-d')}, 9:00 AM. (event {ev_id}; Google Calendar within 15 min)")


def reject(cur, chat_id):
    cur.execute("UPDATE assistant_proposals SET status='rejected', resolved_at=now() "
                "WHERE chat_id=%s AND status='pending' RETURNING raw_text", (chat_id,))
    row = cur.fetchone()
    if not row:
        return "Nothing pending."
    absorb(cur, chat_id, row[0])
    return "Okay, not scheduled — kept it as a note."


def absorb(cur, chat_id, text):
    cur.execute(
        "INSERT INTO chat_notes (sender_id, sender_name, content, topic, importance) "
        "VALUES (%s,'Jonathan (assistant)',%s,'task',3)", (chat_id, text))


def handle(cur, token, ch_id, cu_id, chat_id, text):
    intent, payload = classify(text)
    if intent == "query_agenda":
        out = agenda_reply(cur)
    elif intent == "query_pulse":
        out = pulse_reply()
    elif intent == "propose_event":
        out = propose(cur, chat_id, text, payload)
    elif intent == "confirm":
        out = confirm(cur, chat_id)
    elif intent == "reject":
        out = reject(cur, chat_id)
    else:
        absorb(cur, chat_id, text)
        out = "Noted."
    if token:
        reply(cur, token, ch_id, cu_id, out)
    return intent, out


# ── poll loop ────────────────────────────────────────────────────────────
def get_offset(cur):
    cur.execute("SELECT value FROM assistant_state WHERE key='update_offset'")
    r = cur.fetchone()
    return int(r[0]) if r else 0


def set_offset(cur, off):
    cur.execute("INSERT INTO assistant_state (key, value) VALUES ('update_offset', %s) "
                "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()",
                (str(off),))


def poll_once(conn, cur, token, ch_id, cu_id, long_poll):
    off = get_offset(cur)
    resp = tg_api(token, "getUpdates", offset=off + 1,
                  timeout=(50 if long_poll else 0))
    for upd in resp.get("result", []):
        off = max(off, upd["update_id"])
        msg = upd.get("message") or {}
        chat_id = str((msg.get("chat") or {}).get("id", ""))
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        if chat_id != JONATHAN_CHAT_ID:
            # internal-only: log, do NOT reply (never confirm existence to strangers)
            bus_log(cur, ch_id, cu_id, "inbound", f"[UNAUTHORIZED {chat_id}] {text[:200]}",
                    ext_id=msg.get("message_id"), status="refused")
            conn.commit()
            continue
        bus_log(cur, ch_id, cu_id, "inbound", text, ext_id=msg.get("message_id"))
        conn.commit()  # sponge: inbound is durable BEFORE parsing
        try:
            intent, out = handle(cur, token, ch_id, cu_id, chat_id, text)
            print(f"[inbound] {text[:60]!r} → {intent}: {out[:60]!r}")
        except Exception as e:  # noqa: BLE001 — the note is already saved
            print(f"[inbound] handler error (message preserved on bus): {e}", file=sys.stderr)
        conn.commit()
    set_offset(cur, off)
    conn.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daemon", action="store_true", help="long-poll loop")
    ap.add_argument("--once", action="store_true", help="single poll pass")
    ap.add_argument("--test", metavar="MSG", help="parse-only: classify + handle with no telegram")
    args = ap.parse_args()

    if args.test:
        conn = db(); cur = conn.cursor()
        ensure_schema(cur); conn.commit()
        ch_id, cu_id = bus_ids(cur); conn.commit()
        intent, out = handle(cur, None, ch_id, cu_id, JONATHAN_CHAT_ID, args.test)
        conn.commit()
        print(f"intent: {intent}\nreply:  {out}")
        return 0

    env = load_env()
    token = env.get("ASSISTANT_BOT_TOKEN")
    if not token:
        print("[assistant_inbound] ASSISTANT_BOT_TOKEN not set — idle (create the bot "
              "via @BotFather, add the token to .env). Clean exit.")
        return 0

    conn = db(); cur = conn.cursor()
    ensure_schema(cur); conn.commit()
    ch_id, cu_id = bus_ids(cur); conn.commit()

    if args.once:
        poll_once(conn, cur, token, ch_id, cu_id, long_poll=False)
        return 0

    print("[assistant_inbound] daemon up — long-polling.")
    while True:
        try:
            poll_once(conn, cur, token, ch_id, cu_id, long_poll=True)
        except KeyboardInterrupt:
            return 0
        except Exception as e:  # noqa: BLE001 — degrade, don't crash
            print(f"[assistant_inbound] poll error: {e} — retrying in 30s", file=sys.stderr)
            time.sleep(30)
            try:
                conn.close()
            except Exception:
                pass
            conn = db(); cur = conn.cursor()


if __name__ == "__main__":
    sys.exit(main())
