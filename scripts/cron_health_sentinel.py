#!/usr/bin/env python3
"""cron_health_sentinel.py — alert if any cron's log is stale.

Watches the log files of every scheduled job. If a log hasn't been
written within its expected interval × 1.5, alerts Jonathan.

Cron-checks:
  refresh-realtime-flow         every 5 min   stale if >10 min
  sim-monitor                   every 5 min   stale if >10 min
  sim_leak_sentinel             every 1 min   stale if >3 min
  refresh-evidence-facts        every 10 min  stale if >20 min
  leo-proposal-auto-verify      every 30 min  stale if >60 min
  leo-improvement-proposer      every 4 h     stale if >5 h
  refresh-title-facts           daily 06:00   stale if >26 h
  evidence-trail-proposer       daily 07:00   stale if >26 h
  apply-evidence-trail          every 1 h     stale if >2 h
  sim-daily-digest              daily 23:00   stale if >26 h

Self-suppresses: only alerts on FIRST detection, then again after
6 hours if still stale. Tracks state in cron_health_state.
"""
from __future__ import annotations
import json, os, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, "/root/landtek/scripts")
try:
    from tg_send import send as tg_send
except Exception:
    tg_send = None

import psycopg2, psycopg2.extras
DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN = "6513067717"

CRONS = [
    # (log_path, label, max_stale_minutes)
    ("/var/log/refresh-realtime-flow.log",      "refresh-realtime-flow",      10),
    ("/var/log/sim-monitor.log",                "sim-monitor",                10),
    ("/var/log/sim_leak_sentinel.log",          "sim_leak_sentinel",           3),
    ("/var/log/refresh-evidence-facts.log",     "refresh-evidence-facts",     20),
    ("/var/log/leo-proposal-auto-verify.log",   "leo-proposal-auto-verify",   60),
    ("/var/log/leo-improvement-proposer.log",   "leo-improvement-proposer",  300),
    ("/var/log/refresh-title-facts.log",        "refresh-title-facts",      1560),
    ("/var/log/evidence-trail-proposer.log",    "evidence-trail-proposer",  1560),
    ("/var/log/apply-evidence-trail.log",       "apply-evidence-trail",      120),
    ("/var/log/sim-daily-digest.log",           "sim-daily-digest",         1560),
]


def ensure_schema(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cron_health_state (
            label           text PRIMARY KEY,
            last_log_at     timestamptz,
            first_alerted_at timestamptz,
            last_alerted_at  timestamptz,
            stale_streak    integer NOT NULL DEFAULT 0
        )
    """)


def check_one(path: str, max_stale_min: int) -> tuple[bool, datetime | None]:
    p = Path(path)
    if not p.exists():
        return (True, None)
    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    stale = (now - mtime) > timedelta(minutes=max_stale_min)
    return (stale, mtime)


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_schema(cur)
    now = datetime.now(timezone.utc)

    stale_list = []
    for path, label, max_stale_min in CRONS:
        is_stale, mtime = check_one(path, max_stale_min)
        cur.execute(
            "INSERT INTO cron_health_state (label, last_log_at) VALUES (%s, %s) "
            "ON CONFLICT (label) DO UPDATE SET last_log_at = EXCLUDED.last_log_at",
            (label, mtime),
        )
        if is_stale:
            cur.execute("SELECT * FROM cron_health_state WHERE label=%s", (label,))
            state = cur.fetchone()
            # Alert if first time or >6h since last alert
            should_alert = (
                state["first_alerted_at"] is None
                or (state["last_alerted_at"] is None)
                or (now - state["last_alerted_at"]) > timedelta(hours=6)
            )
            if should_alert:
                stale_list.append({
                    "label": label, "path": path,
                    "max_stale_min": max_stale_min,
                    "last_mtime": mtime,
                    "first_alert": state["first_alerted_at"] is None,
                })
                cur.execute("""
                    UPDATE cron_health_state
                       SET first_alerted_at = COALESCE(first_alerted_at, now()),
                           last_alerted_at = now(),
                           stale_streak = stale_streak + 1
                     WHERE label = %s
                """, (label,))
        else:
            # Healthy → reset streak
            cur.execute("""
                UPDATE cron_health_state
                   SET first_alerted_at = NULL, last_alerted_at = NULL,
                       stale_streak = 0
                 WHERE label = %s AND first_alerted_at IS NOT NULL
            """, (label,))

    if not stale_list:
        print("[cron_health] all crons healthy")
        return

    parts = ["⚠️ <b>CRON HEALTH ALERT</b>", ""]
    for s in stale_list:
        last = s["last_mtime"].strftime("%Y-%m-%d %H:%M UTC") if s["last_mtime"] else "NEVER"
        new_tag = " (FIRST DETECTION)" if s["first_alert"] else " (still stale)"
        parts.append(f"  • <code>{s['label']}</code>{new_tag}")
        parts.append(f"      last log: {last}  (expected within {s['max_stale_min']}m)")
    parts.append("")
    parts.append("<i>Crons normally self-heal. If persistent, check systemd / crontab / cowork-bridge.</i>")
    text = "\n".join(parts)
    if tg_send is not None:
        try:
            tg_send(JONATHAN, text, source="watchdog",
                    recipient_name="Jonathan", override_rate_limit=True)
        except Exception:
            pass
    print(f"[cron_health] {len(stale_list)} stale crons alerted")
    for s in stale_list:
        print(f"  {s['label']}: last={s['last_mtime']}")


if __name__ == "__main__":
    main()
