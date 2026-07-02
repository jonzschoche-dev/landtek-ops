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
import sys
from datetime import datetime, timedelta, timezone

# reuse the agenda spine — one source of truth, no duplicate gather logic
from calendar_sync import (
    db, table_exists, columns_of, load_matters_index,
    gather_from_matters, gather_from_events, gather_from_case_actions,
)

JONATHAN_CHAT_ID = "6513067717"
TZ = "Asia/Manila"


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


def run_mode(cur, mode_key, items, today, chat_id, dry):
    kind, composer = MODES[mode_key]
    text = composer(items, today)
    if not text:
        print(f"[{mode_key}] nothing to say — staying quiet.")
        return
    if dry:
        print(f"[{mode_key}] WOULD SEND → {chat_id}:\n  {text}")
        return
    on_demand = mode_key == "now"  # on-demand: no once-a-day dedup
    if not on_demand and already_sent(cur, kind, today):
        print(f"[{mode_key}] already sent for {today} — skip (dedup).")
        return
    from tg_send import send
    ok, info = send(chat_id=chat_id, text=text, source="assistant_cadence",
                    recipient_name="Jonathan")
    if ok:
        if not on_demand:
            mark_sent(cur, kind, today, text)
        print(f"[{mode_key}] sent.")
    else:
        # S14 gate (e.g. awaiting-reply / rate limit) — expected, not a failure.
        print(f"[{mode_key}] not sent ({info}). Will retry next run.")


def main():
    ap = argparse.ArgumentParser(description="Scheduling assistant — reminder cadence")
    ap.add_argument("--morning", action="store_true", help="send week-ahead brief")
    ap.add_argument("--evening", action="store_true", help="send day-before nudge")
    ap.add_argument("--now", action="store_true", help="on-demand 'what's coming' (no dedup)")
    ap.add_argument("--dry", action="store_true", help="preview only, send nothing")
    ap.add_argument("--to", default=JONATHAN_CHAT_ID, help="recipient chat_id")
    args = ap.parse_args()

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
        run_mode(cur, m, items, today, args.to, dry)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
