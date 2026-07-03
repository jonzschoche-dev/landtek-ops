#!/usr/bin/env python3
"""Scheduling Assistant — cadence engine (the "reminder" half).

Speaks in human cadence, not computer cadence: it decides *whether to say anything*
and, if so, ONE plain-language message. It reuses the agenda spine (calendar_sync's
gather) as the source of truth and tg_send.py for delivery (S14: plain, one-at-a-time,
no double-tap to Jonathan — so this deliberately sends at most ONE message per run).

Deterministic-first: the brief is composed from templates, no LLM.

Modes:
  --morning     week-ahead brief (what's coming; the soonest few). Dedup: once/day.
  --evening     day-before nudge (what's tomorrow / due now). Dedup: once/day.
  (no mode)     DRY preview of both — prints what it *would* send, sends nothing.
  --dry         force preview even with a mode.
  --to <chatid> override recipient (default: Jonathan 6513067717).

Design: docs/scheduling_assistant_design.md
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

# reuse the agenda spine — one source of truth, no duplicate gather logic
from calendar_sync import (
    db, table_exists, columns_of, load_matters_index, load_env,
    gather_from_matters, gather_from_events, gather_from_case_actions,
)

JONATHAN_CHAT_ID = "6513067717"
JONATHAN_EMAIL = "jonathan@hayuma.org"  # self-only; never an external address
TZ = "Asia/Manila"
OAUTH_CLIENT_PATH = "/root/landtek/gmail_oauth_client.json"

SUBJECTS = {
    "morning_brief": "LandTek — your week ahead",
    "day_before": "LandTek — tomorrow's agenda",
    "on_demand": "LandTek — what's coming",
}


def manila_today():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(TZ)).date()
    except Exception:
        return datetime.now(timezone.utc).date()


def item_date(it):
    return it.start.date() if isinstance(it.start, datetime) else it.start


def get_agenda(cur):
    """Unified, forward-looking agenda from the spine (same sources as calendar_sync)."""
    index, by_code = load_matters_index(cur)
    clients_by_id = {}
    if table_exists(cur, "clients") and "client_code" in columns_of(cur, "clients"):
        cur.execute("SELECT id, client_code FROM clients WHERE client_code IS NOT NULL")
        clients_by_id = {cid: code for cid, code in cur.fetchall()}
    items = (gather_from_matters(cur, None, index, by_code)
             + gather_from_events(cur, None, index, clients_by_id)
             + gather_from_case_actions(cur, None, index))
    # NB: matter_plays (kind='play') are deliberately EXCLUDED from the spoken
    # reminder — they are strategic-move suggestions that pile onto a matter's
    # deadline date, not scheduled commitments. A human reminder names the event,
    # not the whole playbook. (Plays still appear on the Google Calendar canvas.)
    return [i for i in items if i.start is not None]


def ensure_log(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS assistant_nudge_log (
            kind      TEXT NOT NULL,
            ref_date  DATE NOT NULL,
            sent_at   TIMESTAMPTZ DEFAULT now(),
            preview   TEXT,
            PRIMARY KEY (kind, ref_date)
        )
        """
    )


def already_sent(cur, kind, ref_date):
    cur.execute("SELECT 1 FROM assistant_nudge_log WHERE kind=%s AND ref_date=%s",
                (kind, ref_date))
    return cur.fetchone() is not None


def mark_sent(cur, kind, ref_date, preview):
    cur.execute(
        "INSERT INTO assistant_nudge_log (kind, ref_date, preview) VALUES (%s,%s,%s) "
        "ON CONFLICT (kind, ref_date) DO UPDATE SET sent_at=now(), preview=EXCLUDED.preview",
        (kind, ref_date, preview))


# ── plain-language composition (deterministic, no markup, ≤280 handled by tg_send) ──
def _tag(it):
    """A short human tag: prefer the owner, else the matter, else the client."""
    return it.owner or it.matter or it.client or ""


def _short(it, n=52):
    t = (it.title or "").strip().replace("\n", " ")
    return (t[:n] + "…") if len(t) > n else t


def _fmt_day(d):
    return d.strftime("%b %-d") if hasattr(d, "strftime") else str(d)


def compose_morning(items, today):
    window = sorted([i for i in items if today <= item_date(i) <= today + timedelta(days=7)],
                    key=item_date)
    if not window:
        return None
    lead = window[0]
    bits = [f"{_fmt_day(item_date(i))} {_short(i, 34)}"
            + (f" ({_tag(i)})" if _tag(i) else "") for i in window[:3]]
    more = f" +{len(window) - 3} more" if len(window) > 3 else ""
    return (f"Morning. {len(window)} on the calendar this week. "
            + "; ".join(bits) + more + ".")


def compose_evening(items, today):
    tomorrow = today + timedelta(days=1)
    due = sorted([i for i in items if item_date(i) == tomorrow], key=item_date)
    if not due:
        return None
    bits = [_short(i, 40) + (f" ({_tag(i)})" if _tag(i) else "") for i in due[:3]]
    more = f" +{len(due) - 3} more" if len(due) > 3 else ""
    return "Tomorrow: " + "; ".join(bits) + more + "."


def compose_upcoming(items, today, n=5):
    """On-demand 'what's coming' — the next N items from today forward, no 7-day cap.
    Used for --now (ask any time; also the live test)."""
    ahead = sorted([i for i in items if item_date(i) >= today], key=item_date)
    if not ahead:
        return "Nothing on the calendar ahead right now."
    bits = [f"{_fmt_day(item_date(i))} {_short(i, 34)}"
            + (f" ({_tag(i)})" if _tag(i) else "") for i in ahead[:n]]
    return "Coming up: " + "; ".join(bits) + "."


MODES = {
    "morning": ("morning_brief", compose_morning),
    "evening": ("day_before", compose_evening),
    "now": ("on_demand", compose_upcoming),  # on-demand, no dedup
}


def email_send(subject, body_text, to=JONATHAN_EMAIL):
    """Send a plain-text brief via the (send-scoped) Gmail token. Self-only.
    Degrades gracefully: returns (False, reason) if the token can't send."""
    try:
        import base64
        from email.mime.text import MIMEText
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        env = load_env()
        rt = env.get("GMAIL_REFRESH_TOKEN")
        if not rt:
            return False, "no GMAIL_REFRESH_TOKEN"
        with open(OAUTH_CLIENT_PATH) as f:
            conf = json.load(f)
        c = conf.get("web") or conf.get("installed")
        cr = Credentials(token=None, refresh_token=rt,
                         token_uri="https://oauth2.googleapis.com/token",
                         client_id=c["client_id"], client_secret=c["client_secret"])
        cr.refresh(Request())
        svc = build("gmail", "v1", credentials=cr, cache_discovery=False)
        msg = MIMEText(body_text, "plain")
        msg["To"], msg["From"], msg["Subject"] = to, to, subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        r = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
        return True, r.get("id")
    except Exception as e:  # noqa: BLE001 — degrade, don't crash a timer
        return False, f"gmail send failed: {e}"


def run_mode(cur, mode_key, items, today, dry, channel="telegram", chat_id=JONATHAN_CHAT_ID):
    kind, composer = MODES[mode_key]
    text = composer(items, today)
    if not text:
        print(f"[{mode_key}/{channel}] nothing to say — staying quiet.")
        return
    # channel-aware dedup so telegram + email of the same brief don't block each other
    dkey = kind if channel == "telegram" else f"{kind}:{channel}"
    dest = chat_id if channel == "telegram" else JONATHAN_EMAIL
    if dry:
        print(f"[{mode_key}/{channel}] WOULD SEND → {dest}:\n  {text}")
        return
    on_demand = mode_key == "now"  # on-demand: no once-a-day dedup
    if not on_demand and already_sent(cur, dkey, today):
        print(f"[{mode_key}/{channel}] already sent for {today} — skip (dedup).")
        return
    if channel == "email":
        ok, info = email_send(SUBJECTS.get(kind, "LandTek — calendar"), text)
    else:
        from tg_send import send
        ok, info = send(chat_id=chat_id, text=text, source="assistant_cadence",
                        recipient_name="Jonathan")
    if ok:
        if not on_demand:
            mark_sent(cur, dkey, today, text)
        print(f"[{mode_key}/{channel}] sent{'' if channel=='telegram' else ' (id '+str(info)+')'}.")
    else:
        # tg S14 gate / gmail hiccup — expected-ish, not a crash. Retry next run.
        print(f"[{mode_key}/{channel}] not sent ({info}). Will retry next run.")


def main():
    ap = argparse.ArgumentParser(description="Scheduling assistant — reminder cadence")
    ap.add_argument("--morning", action="store_true", help="send week-ahead brief")
    ap.add_argument("--evening", action="store_true", help="send day-before nudge")
    ap.add_argument("--now", action="store_true", help="on-demand 'what's coming' (no dedup)")
    ap.add_argument("--email", action="store_true", help="deliver via email to Jonathan (self only)")
    ap.add_argument("--dry", action="store_true", help="preview only, send nothing")
    ap.add_argument("--to", default=JONATHAN_CHAT_ID, help="telegram recipient chat_id")
    args = ap.parse_args()
    channel = "email" if args.email else "telegram"

    conn = db()
    cur = conn.cursor()
    ensure_log(cur)
    conn.commit()

    today = manila_today()
    items = get_agenda(cur)
    print(f"[assistant_cadence] {len(items)} agenda item(s); today={today} (Manila)")

    modes = [m for m in ("morning", "evening", "now") if getattr(args, m)]
    dry = args.dry or not modes
    if not modes:  # no explicit mode → preview morning + evening
        modes = ["morning", "evening"]

    for m in modes:
        run_mode(cur, m, items, today, dry, channel=channel, chat_id=args.to)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
