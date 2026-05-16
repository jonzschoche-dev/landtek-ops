#!/usr/bin/env python3
"""Proactive deadline surfacing — deploy_096.

Cron every 6h (or via /api/deadlines). Pulls:
  - action_items.due_date within next 7 days, status='Open'
  - calendar_events.start_at within next 7 days
  - pending_inquiries open longer than 48h
DMs Jonathan a prioritized "heads-up" list.

Idempotent: tracks last-notified in /var/lib/landtek/proactive_state.json
so we don't spam the same items every run.
"""
import json, os, sys, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
import psycopg2, psycopg2.extras

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
JONATHAN_TG_ID = "6513067717"
STATE_PATH = "/var/lib/landtek/proactive_state.json"


def _token():
    for l in open("/root/landtek/.env"):
        if l.startswith("TELEGRAM_BOT_TOKEN="):
            return l.split("=", 1)[1].strip()


def tg_send(text, parse_mode="HTML"):
    tok = _token()
    if not tok: return False
    data = {"chat_id": JONATHAN_TG_ID, "text": text[:4090], "parse_mode": parse_mode}
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage",
                               data=urllib.parse.urlencode(data).encode(), timeout=10).read()
        return True
    except Exception as e:
        print(f"tg fail: {e}", file=sys.stderr); return False


def load_state():
    try:
        with open(STATE_PATH) as f: return json.load(f)
    except: return {"notified_ids": {}}


def save_state(s):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f: json.dump(s, f)


def main():
    state = load_state()
    notified = set(state.get("notified_ids", {}).get("today", []))
    now = datetime.now(timezone.utc)
    today_key = now.strftime("%Y-%m-%d")
    # Reset notified set if it's a new day
    if state.get("notified_ids", {}).get("date") != today_key:
        notified = set()
        state["notified_ids"] = {"date": today_key, "today": []}

    conn = psycopg2.connect(**DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cutoff = now + timedelta(days=7)

    cur.execute("""
        SELECT id, case_file, description, due_date, priority
          FROM action_items
         WHERE status = 'Open' AND due_date IS NOT NULL AND due_date <= %s::date
         ORDER BY due_date ASC, CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END
         LIMIT 20;
    """, (cutoff.date(),))
    actions = [r for r in cur.fetchall() if f"a{r['id']}" not in notified]

    try:
        cur.execute("""
            SELECT id, title, start_at, related_case, location
              FROM calendar_events
             WHERE start_at::date <= %s::date AND start_at >= now() - interval '4 hours'
             ORDER BY start_at ASC LIMIT 20;
        """, (cutoff.date(),))
        events = [r for r in cur.fetchall() if f"e{r['id']}" not in notified]
    except Exception:
        events = []

    cur.execute("""
        SELECT id, target_client_name, target_client_code, question_text, asked_at
          FROM pending_inquiries
         WHERE status = 'open'
           AND asked_at < now() - interval '48 hours'
           AND expires_at > now()
         ORDER BY asked_at ASC LIMIT 10;
    """)
    stale = [r for r in cur.fetchall() if f"i{r['id']}" not in notified]

    if not (actions or events or stale):
        print("  nothing new to surface")
        return

    lines = [f"⏰ <b>Proactive heads-up ({now.strftime('%H:%M UTC')})</b>", ""]
    if events:
        lines.append(f"📅 <b>Calendar (next 7d)</b>")
        for e in events:
            lines.append(f"  • <b>{e['start_at'].strftime('%a %m/%d %H:%M')}</b> — {e['title'][:60]} ({e['related_case'] or '?'})")
            notified.add(f"e{e['id']}")
        lines.append("")
    if actions:
        lines.append(f"📋 <b>Action items due (next 7d)</b>")
        for a in actions:
            lines.append(f"  • <b>{a['due_date']}</b> [{a['priority'] or '?'}] {a['case_file'] or '?'}: {a['description'][:80]}")
            notified.add(f"a{a['id']}")
        lines.append("")
    if stale:
        lines.append(f"⚠️ <b>Inquiries open &gt;48h</b>")
        for s in stale:
            age_h = (now - s["asked_at"]).total_seconds() / 3600
            lines.append(f"  • #{s['id']} to {s['target_client_name']} ({age_h:.0f}h): {s['question_text'][:60]}")
            notified.add(f"i{s['id']}")
        lines.append("")

    tg_send("\n".join(lines))
    state["notified_ids"]["today"] = list(notified)
    save_state(state)
    print(f"  sent: {len(actions)} actions / {len(events)} events / {len(stale)} stale")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
