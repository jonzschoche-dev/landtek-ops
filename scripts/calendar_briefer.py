#!/usr/bin/env python3
"""calendar_briefer.py - agentic calendar: proactive briefs to Jonathan.

Runs every 30 min via systemd timer. Four jobs:

  1. Auto-complete events whose end_at (or start_at + 2h fallback) is more
     than 2 hours in the past. Flip status='completed' so they stop appearing
     as "upcoming". Marks calendar_briefs_sent.outcome='auto_completed'.

  2. PREP BRIEFS — for any event starting in 1h-3h that hasn't had a prep
     brief sent yet, send Jonathan a Telegram message with:
       - event title, time (Asia/Manila), location, attendees
       - matter_code + last 3 docs on that matter
       - any open action_items on that matter
       - last interaction with each named attendee

  3. POST-EVENT FOLLOWUP — for any event whose end_at was 4-8h ago and has
     status='completed' but no followup_asked timestamp, send Jonathan:
       "How did <title> go? Any next actions to log?"
     Marks followup_asked so we don't re-ask.

  4. MORNING DAILY BRIEF — at 7am Manila (UTC+8 → 23:00 UTC previous day),
     send a single Telegram with: today's events, tomorrow's events,
     past-due deadlines from matters.next_deadline. Idempotent per day via
     calendar_briefs_sent.brief_type='daily_morning' + brief_date.

All briefs deduplicated via calendar_briefs_sent table (created if missing).
Bot token from .env. Jonathan's chat_id is the bot owner.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
ENV_PATH = "/root/landtek/.env"
JONATHAN_CHAT_ID = "6513067717"
LOG_PATH = "/var/log/landtek/calendar_briefer.log"

MANILA_TZ = timezone(timedelta(hours=8))


def log(msg):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(LOG_PATH, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"[{ts}] {msg}")


def load_bot_token():
    with open(ENV_PATH) as f:
        for line in f:
            for k in ("TELEGRAM_BOT_TOKEN", "TG_BOT_TOKEN", "BOT_TOKEN"):
                if line.startswith(k + "="):
                    return line.split("=", 1)[1].strip().strip('"\'')
    return None


def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text[:4000],  # Telegram cap
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return bool(data.get("ok")), data.get("description", "")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        return False, f"HTTP {e.code} {body[:200]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def ensure_schema(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS calendar_briefs_sent (
            id              SERIAL PRIMARY KEY,
            event_id        INTEGER REFERENCES calendar_events(id) ON DELETE CASCADE,
            brief_type      TEXT NOT NULL CHECK (brief_type IN
                              ('prep_2h', 'followup_post', 'auto_completed',
                               'daily_morning', 'conflict_alert')),
            brief_date      DATE,
            sent_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            telegram_ok     BOOLEAN,
            telegram_error  TEXT,
            UNIQUE (event_id, brief_type),
            UNIQUE (brief_type, brief_date)
        );
        CREATE INDEX IF NOT EXISTS idx_briefs_event ON calendar_briefs_sent(event_id);
        CREATE INDEX IF NOT EXISTS idx_briefs_type_date ON calendar_briefs_sent(brief_type, brief_date);
    """)


def fmt_manila(ts):
    """Convert a UTC timestamp to a human-readable Manila string."""
    if ts is None:
        return "TBD"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    local = ts.astimezone(MANILA_TZ)
    return local.strftime("%a %b %-d, %-I:%M %p")


def already_sent(cur, event_id, brief_type, brief_date=None):
    if brief_date is not None:
        cur.execute("SELECT 1 FROM calendar_briefs_sent WHERE brief_type=%s AND brief_date=%s",
                    (brief_type, brief_date))
    else:
        cur.execute("SELECT 1 FROM calendar_briefs_sent WHERE event_id=%s AND brief_type=%s",
                    (event_id, brief_type))
    return cur.fetchone() is not None


def mark_sent(cur, event_id, brief_type, ok, err, brief_date=None):
    cur.execute("""
        INSERT INTO calendar_briefs_sent (event_id, brief_type, brief_date, telegram_ok, telegram_error)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """, (event_id, brief_type, brief_date, ok, err))


# ─── Job 1: auto-complete passed events ──────────────────────────────────
def job_auto_complete(cur):
    cur.execute("""
        UPDATE calendar_events
           SET status = 'completed', updated_at = now()
         WHERE status = 'scheduled'
           AND COALESCE(end_at, start_at + INTERVAL '2 hours') < now() - INTERVAL '2 hours'
         RETURNING id, title
    """)
    rows = cur.fetchall()
    for r in rows:
        log(f"  auto-completed event#{r['id']} '{r['title'][:50]}'")
        mark_sent(cur, r["id"], "auto_completed", True, None)
    return len(rows)


# ─── Job 2: prep brief 1-3h before ───────────────────────────────────────
def job_prep_briefs(cur, token, dry_run=False):
    cur.execute("""
        SELECT id, title, start_at, end_at, location, attendees, related_case, related_tct, description
          FROM calendar_events
         WHERE status = 'scheduled'
           AND start_at BETWEEN now() + INTERVAL '1 hour' AND now() + INTERVAL '3 hours'
         ORDER BY start_at
    """)
    rows = cur.fetchall()
    sent = 0
    for r in rows:
        if already_sent(cur, r["id"], "prep_2h"):
            continue
        attendees = ", ".join(r["attendees"] or []) or "(none recorded)"
        # Pull last 3 docs on matter
        last_docs = []
        if r["related_case"]:
            cur.execute("""
                SELECT id, COALESCE(smart_filename, original_filename, document_title, '') AS title
                  FROM documents
                 WHERE case_file = %s OR matter_code = %s
                 ORDER BY id DESC LIMIT 3
            """, (r["related_case"], r["related_case"]))
            last_docs = cur.fetchall()
        # Pull open action items on matter
        action_items = []
        if r["related_case"]:
            cur.execute("""
                SELECT description FROM action_items
                 WHERE case_file = %s AND status = 'Open' ORDER BY id DESC LIMIT 3
            """, (r["related_case"],))
            action_items = [a["description"] for a in cur.fetchall()]

        text_parts = [
            f"🔔 <b>Prep brief — in {((r['start_at'] - datetime.now(timezone.utc)).seconds // 60)} min</b>",
            "",
            f"<b>{r['title']}</b>",
            f"📅 {fmt_manila(r['start_at'])}" + (f" – {fmt_manila(r['end_at'])}" if r['end_at'] else ""),
        ]
        if r["location"]:
            text_parts.append(f"📍 {r['location']}")
        text_parts.append(f"👥 {attendees}")
        if r["related_case"]:
            text_parts.append(f"🗂 Matter: {r['related_case']}")
        if last_docs:
            text_parts.append("")
            text_parts.append("Recent docs on this matter:")
            for d in last_docs:
                text_parts.append(f"  • doc#{d['id']} {(d['title'] or '(no title)')[:60]}")
        if action_items:
            text_parts.append("")
            text_parts.append("Open actions on this matter:")
            for ai in action_items:
                text_parts.append(f"  • {(ai or '')[:80]}")
        if r["description"]:
            text_parts.append("")
            text_parts.append(f"Notes: {r['description'][:200]}")

        msg = "\n".join(text_parts)
        if dry_run:
            log(f"  [DRY] would send prep brief for event#{r['id']}")
            continue
        ok, err = send_telegram(token, JONATHAN_CHAT_ID, msg)
        mark_sent(cur, r["id"], "prep_2h", ok, err)
        log(f"  prep brief event#{r['id']} ok={ok} err={err[:60] if err else ''}")
        sent += 1
    return sent


# ─── Job 3: post-event followup ──────────────────────────────────────────
def job_followup_asks(cur, token, dry_run=False):
    cur.execute("""
        SELECT id, title, start_at, end_at, related_case, attendees
          FROM calendar_events
         WHERE status = 'completed'
           AND COALESCE(end_at, start_at + INTERVAL '2 hours')
               BETWEEN now() - INTERVAL '8 hours' AND now() - INTERVAL '4 hours'
         ORDER BY start_at
    """)
    rows = cur.fetchall()
    sent = 0
    for r in rows:
        if already_sent(cur, r["id"], "followup_post"):
            continue
        attendees = ", ".join(r["attendees"] or []) or "those present"
        msg = (
            f"🔄 <b>Post-event followup</b>\n\n"
            f"How did <b>{r['title']}</b> go?\n"
            f"({fmt_manila(r['start_at'])} with {attendees})\n\n"
            f"Any next actions to log? Decisions reached? Documents promised? "
            f"Reply with the outcome and I'll capture it into the chronicle."
        )
        if dry_run:
            log(f"  [DRY] would send followup for event#{r['id']}")
            continue
        ok, err = send_telegram(token, JONATHAN_CHAT_ID, msg)
        mark_sent(cur, r["id"], "followup_post", ok, err)
        log(f"  followup event#{r['id']} ok={ok}")
        sent += 1
    return sent


# ─── Job 4: 7am Manila daily brief ───────────────────────────────────────
def job_daily_brief(cur, token, dry_run=False, force=False):
    now_utc = datetime.now(timezone.utc)
    now_manila = now_utc.astimezone(MANILA_TZ)
    if not force and not (6 <= now_manila.hour <= 8):
        # only send during 6-8am Manila window
        return 0
    brief_date = now_manila.date()
    if not force and already_sent(cur, None, "daily_morning", brief_date=brief_date):
        return 0

    # Today's events (Manila day)
    cur.execute("""
        SELECT id, title, start_at, location, attendees, related_case
          FROM calendar_events
         WHERE status IN ('scheduled', 'rescheduled')
           AND (start_at AT TIME ZONE 'Asia/Manila')::date = %s
         ORDER BY start_at
    """, (brief_date,))
    today_events = cur.fetchall()

    # Tomorrow's events
    cur.execute("""
        SELECT id, title, start_at, location, attendees, related_case
          FROM calendar_events
         WHERE status IN ('scheduled', 'rescheduled')
           AND (start_at AT TIME ZONE 'Asia/Manila')::date = %s
         ORDER BY start_at
    """, (brief_date + timedelta(days=1),))
    tomorrow_events = cur.fetchall()

    # Past-due deadlines
    cur.execute("""
        SELECT matter_code, next_deadline, next_event
          FROM matters
         WHERE next_deadline IS NOT NULL
           AND next_deadline < %s
           AND status = 'active'
         ORDER BY next_deadline
    """, (brief_date,))
    past_due = cur.fetchall()

    # Past 24h events that haven't had followup asked
    cur.execute("""
        SELECT e.id, e.title FROM calendar_events e
         WHERE e.status = 'completed'
           AND COALESCE(e.end_at, e.start_at + INTERVAL '2 hours') > now() - INTERVAL '24 hours'
           AND COALESCE(e.end_at, e.start_at + INTERVAL '2 hours') < now()
           AND NOT EXISTS (
                 SELECT 1 FROM calendar_briefs_sent b
                  WHERE b.event_id = e.id AND b.brief_type = 'followup_post'
               )
         ORDER BY e.start_at DESC
    """)
    unfollowed = cur.fetchall()

    if not today_events and not tomorrow_events and not past_due and not unfollowed:
        log(f"  daily brief {brief_date}: nothing to send")
        return 0

    lines = [f"☀️ <b>Daily brief — {brief_date.strftime('%a %b %-d')}</b>"]
    if today_events:
        lines.append("")
        lines.append(f"<b>Today ({len(today_events)})</b>")
        for e in today_events:
            atts = ", ".join(e["attendees"] or [])
            lines.append(f"  • {fmt_manila(e['start_at']).split(',', 1)[1].strip()} — {e['title']}"
                         + (f" [{e['related_case']}]" if e['related_case'] else ""))
            if atts:
                lines.append(f"      with {atts}")
            if e["location"]:
                lines.append(f"      at {e['location']}")
    if tomorrow_events:
        lines.append("")
        lines.append(f"<b>Tomorrow ({len(tomorrow_events)})</b>")
        for e in tomorrow_events:
            lines.append(f"  • {fmt_manila(e['start_at']).split(',', 1)[1].strip()} — {e['title']}")
    if past_due:
        lines.append("")
        lines.append(f"<b>Past-due ({len(past_due)})</b>")
        for p in past_due:
            lines.append(f"  • [{p['matter_code']}] due {p['next_deadline']}: {(p['next_event'] or '')[:100]}")
    if unfollowed:
        lines.append("")
        lines.append(f"<b>Awaiting your post-event note ({len(unfollowed)})</b>")
        for u in unfollowed:
            lines.append(f"  • {u['title']}")

    msg = "\n".join(lines)
    if dry_run:
        log(f"  [DRY] daily brief {brief_date}:\n{msg}")
        return 1
    ok, err = send_telegram(token, JONATHAN_CHAT_ID, msg)
    mark_sent(cur, None, "daily_morning", ok, err, brief_date=brief_date)
    log(f"  daily brief {brief_date} ok={ok}")
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-daily", action="store_true",
                    help="Send the daily brief regardless of time-of-day or already-sent")
    ap.add_argument("--only", choices=["complete", "prep", "followup", "daily"],
                    help="Run only one job")
    args = ap.parse_args()

    token = load_bot_token()
    if not token and not args.dry_run:
        log("FATAL: no bot token")
        sys.exit(1)

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_schema(cur)

    summary = {}
    if args.only in (None, "complete"):
        summary["completed"] = job_auto_complete(cur)
    if args.only in (None, "prep"):
        summary["prep_briefs"] = job_prep_briefs(cur, token, args.dry_run)
    if args.only in (None, "followup"):
        summary["followups"] = job_followup_asks(cur, token, args.dry_run)
    if args.only in (None, "daily"):
        summary["daily_brief"] = job_daily_brief(cur, token, args.dry_run, args.force_daily)

    cur.close()
    conn.close()
    log(f"summary: {summary}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
