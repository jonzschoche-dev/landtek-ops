#!/usr/bin/env python3
"""Deadline sentinel — Leo never misses a deadline (deploy_112-D).

Runs every 15 min via systemd timer. For each active case_deadlines row:
  - Compute days_until = due_date - today
  - Pick tier:
      days >= 14 : NONE (still calm)
      14 > days >= 7 : 't14'
      7  > days >= 3 : 't7'
      3  > days >= 1 : 't3'
      days == 1      : 't1'
      days == 0      : 't0'
      days <  0      : 'overdue'
  - If tier reminder hasn't been sent yet (or overdue: pulse every 4h), send to Jonathan
  - Log to deadline_alerts (audit trail)
  - For overdue: also pull bottlenecks + suggested actions

Usage:
  python3 deadline_sentinel.py            # send any due reminders
  python3 deadline_sentinel.py --dry-run  # show what would fire
"""
import argparse
import json
import os
import sys
from datetime import datetime, date, timedelta, timezone
import psycopg2
import psycopg2.extras
import requests

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
JONATHAN_TG_ID = "6513067717"

# Tier thresholds (in days). Order matters — lowest threshold wins.
TIER_FOR_DAYS = [
    (-9999, "overdue"),
    (0,     "t0"),
    (1,     "t1"),
    (3,     "t3"),   # 1..3
    (7,     "t7"),   # 3..7
    (14,    "t14"),  # 7..14
    # >= 14 → no tier
]

REMINDER_COL = {
    "t14": "reminder_t14_sent_at",
    "t7":  "reminder_t7_sent_at",
    "t3":  "reminder_t3_sent_at",
    "t1":  "reminder_t1_sent_at",
    "t0":  "reminder_t0_sent_at",
    "dayof": "reminder_dayof_sent_at",
}

TIER_EMOJI = {"t14": "🟢", "t7": "🟡", "t3": "🟠", "t1": "🔴", "t0": "🚨", "overdue": "🆘"}
OVERDUE_PULSE_HOURS = 4


def pick_tier(days_until):
    if days_until < 0: return "overdue"
    if days_until == 0: return "t0"
    if days_until == 1: return "t1"
    if days_until <= 3: return "t3"
    if days_until <= 7: return "t7"
    if days_until <= 14: return "t14"
    return None


def load_env_token():
    env = {}
    with open("/root/landtek/.env") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, _, v = line.strip().partition("=")
                env[k.strip()] = v.strip()
    return env.get("TELEGRAM_BOT_TOKEN")


def tg_send(text, token):
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": JONATHAN_TG_ID, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": True},
        timeout=15,
    )
    return r.status_code == 200, r.text[:200]


def compose_reminder(d, tier, days_until, bottlenecks):
    em = TIER_EMOJI.get(tier, "⏰")
    title = d["title"]
    when = d["due_date"].strftime("%Y-%m-%d")
    if tier == "overdue":
        line2 = f"⚠️ <b>OVERDUE by {abs(days_until)} day(s)</b> (was due {when})"
    elif tier == "t0":
        line2 = f"<b>DUE TODAY</b> — {when}"
    else:
        line2 = f"Due {when} — <b>T-{days_until}d</b>"

    lines = [
        f"{em} <b>Deadline alert ({tier.upper()}) — {d['case_file']}</b>",
        f"<b>{title}</b>",
        line2,
    ]
    if d.get("description"):
        lines.append(f"<i>{d['description'][:300]}</i>")
    if tier in ("overdue", "t0", "t1", "t3") and bottlenecks:
        lines.append("")
        lines.append("<b>Blocking bottlenecks:</b>")
        for b in bottlenecks[:3]:
            lines.append(f"  • {b['description'][:200]} <i>(severity={b['severity']})</i>")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-tier", choices=list(REMINDER_COL.keys()),
                    help="re-send for this tier even if already sent")
    args = ap.parse_args()

    today = date.today()
    token = load_env_token()
    if not token and not args.dry_run:
        sys.exit("FATAL: TELEGRAM_BOT_TOKEN not found")

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, case_file, title, description, due_date, deadline_type, status,
               source_doc_id,
               reminder_t14_sent_at, reminder_t7_sent_at, reminder_t3_sent_at,
               reminder_t1_sent_at, reminder_t0_sent_at, reminder_dayof_sent_at,
               (SELECT max(sent_at) FROM deadline_alerts a
                 WHERE a.deadline_id = case_deadlines.id AND a.tier='overdue') AS last_overdue_alert
          FROM case_deadlines
         WHERE status = 'pending'
         ORDER BY due_date ASC NULLS LAST
    """)
    deadlines = cur.fetchall()
    print(f"  scanning {len(deadlines)} active deadlines (today={today})")

    sent_count = 0
    for d in deadlines:
        days = (d["due_date"] - today).days
        tier = args.force_tier or pick_tier(days)
        if tier is None:
            continue

        if tier == "overdue":
            # Pulse every OVERDUE_PULSE_HOURS hours
            last = d.get("last_overdue_alert")
            if last and (datetime.now(timezone.utc) - last) < timedelta(hours=OVERDUE_PULSE_HOURS):
                continue
        else:
            col = REMINDER_COL[tier]
            if d.get(col) and not args.force_tier:
                continue  # already sent for this tier

        # Pull bottlenecks for context
        cur.execute("""
            SELECT description, severity FROM bottlenecks
             WHERE case_file = %s AND status IN ('open','attempting')
             ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                                    WHEN 'medium' THEN 3 ELSE 4 END
             LIMIT 5
        """, (d["case_file"],))
        bn = cur.fetchall()

        text = compose_reminder(d, tier, days, bn)
        if args.dry_run:
            print(f"  → [DRY] would fire {tier.upper()} for deadline #{d['id']} ({d['title'][:60]})")
            print("    ---")
            print("    " + text.replace("\n", "\n    "))
            print("    ---")
            continue

        ok, info = tg_send(text, token)
        if ok:
            sent_count += 1
            if tier != "overdue":
                cur.execute(f"UPDATE case_deadlines SET {REMINDER_COL[tier]}=now() WHERE id=%s",
                            (d["id"],))
            cur.execute("""
                INSERT INTO deadline_alerts (deadline_id, tier, channel, message_text, delivery_ok)
                VALUES (%s,%s,'telegram',%s, true)
            """, (d["id"], tier, text[:2000]))
            print(f"  ✓ fired {tier.upper()} for deadline #{d['id']}: {d['title'][:70]}")
        else:
            cur.execute("""
                INSERT INTO deadline_alerts (deadline_id, tier, channel, message_text, delivery_ok)
                VALUES (%s,%s,'telegram',%s, false)
            """, (d["id"], tier, f"FAILED: {info}"[:2000]))
            print(f"  ✗ FAILED {tier.upper()} for deadline #{d['id']}: {info}")

    # Emit heartbeat
    try:
        cur.execute("""INSERT INTO system_heartbeat (source, status, metadata)
                       VALUES ('deadline-sentinel', 'ok', %s::jsonb)""",
                    (json.dumps({"sent": sent_count, "scanned": len(deadlines)}),))
    except Exception: pass

    print(f"\n  sent {sent_count} reminder(s)")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
