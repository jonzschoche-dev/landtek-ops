#!/usr/bin/env python3
"""Build Jonathan's daily digest.

Runs via:
  - systemd timer at 9 AM Manila (1 AM UTC) — landtek-digest.timer
  - on-demand via /api/digest (Flask) — for /digest slash command

Output: structured Telegram message (or messages — chunked if >4096 chars).

Sections:
  - Overnight client activity (last 24h)
  - New uploads (last 24h)
  - Open inquiries / questions awaiting Jonathan
  - Open action items
  - Today's calendar events
  - Per-case 1-line status
  - Watchdog health
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
import psycopg2
import psycopg2.extras

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
JONATHAN_TG_ID = "6513067717"


def _tg_token():
    with open("/root/landtek/.env") as f:
        for line in f:
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.split("=", 1)[1].strip()
    return None


def tg_send(text, parse_mode="HTML"):
    tok = _tg_token()
    if not tok:
        return False
    data = {"chat_id": JONATHAN_TG_ID, "text": text[:4090]}
    if parse_mode:
        data["parse_mode"] = parse_mode
    try:
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            data=urllib.parse.urlencode(data).encode(),
            timeout=10,
        ).read()
        return True
    except Exception as e:
        print(f"  tg_send failed: {e}", file=sys.stderr)
        return False


def build_digest_sections():
    """Returns a dict of {section_name: text}."""
    conn = psycopg2.connect(**DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    sections = {}
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(hours=24)

    # 1. Overnight client activity
    cur.execute("""
        SELECT case_file, client_name, count(*) AS n_messages,
               max(timestamp) AS last_message
          FROM conversations
         WHERE timestamp > %s
           AND client_name NOT IN ('Jj Moreno', 'Jonathan')
         GROUP BY case_file, client_name
         ORDER BY count(*) DESC;
    """, (yesterday,))
    activity = cur.fetchall()
    if activity:
        lines = []
        for a in activity:
            lines.append(f"  • {a['client_name']} ({a['case_file']}): {a['n_messages']} msg, last {a['last_message'].strftime('%H:%M')}")
        sections["activity"] = "👥 <b>Client activity (last 24h)</b>\n" + "\n".join(lines)

    # 2. New uploads
    cur.execute("""
        SELECT id, case_file, original_filename, timestamp,
               length(coalesce(extracted_text,'')) AS chars
          FROM documents
         WHERE timestamp > %s
         ORDER BY id DESC
         LIMIT 15;
    """, (yesterday,))
    uploads = cur.fetchall()
    if uploads:
        lines = []
        for u in uploads:
            tag = "✓" if u["chars"] > 0 else "○"
            lines.append(f"  {tag} DOC {u['id']} ({u['case_file'] or 'Unclassified'}): {u['original_filename'][:50]}")
        sections["uploads"] = f"📥 <b>New uploads ({len(uploads)} in last 24h)</b>\n" + "\n".join(lines)

    # 3. Open inquiries
    cur.execute("""
        SELECT id, target_client_name, target_client_code, question_text, asked_at
          FROM pending_inquiries
         WHERE status = 'open'
           AND expires_at > now()
         ORDER BY asked_at ASC
         LIMIT 10;
    """)
    inquiries = cur.fetchall()
    if inquiries:
        lines = []
        for q in inquiries:
            age_h = (now - q["asked_at"]).total_seconds() / 3600
            lines.append(f"  • #{q['id']} to {q['target_client_name']} ({q['target_client_code']}, {age_h:.0f}h ago): {q['question_text'][:60]}")
        sections["inquiries"] = f"❓ <b>Open inquiries ({len(inquiries)})</b>\n" + "\n".join(lines)

    # 4. Open action items
    cur.execute("""
        SELECT id, case_file, description, due_date, priority
          FROM action_items
         WHERE status = 'Open'
         ORDER BY due_date ASC NULLS LAST, id DESC
         LIMIT 10;
    """)
    items = cur.fetchall()
    if items:
        lines = []
        for it in items:
            due = it["due_date"].strftime("%Y-%m-%d") if it["due_date"] else "no date"
            lines.append(f"  • [{it['priority'] or '?'}] {due} ({it['case_file'] or '?'}): {it['description'][:70]}")
        sections["action_items"] = f"📋 <b>Open action items ({len(items)})</b>\n" + "\n".join(lines)

    # 5. Today's calendar
    try:
        cur.execute("""
            SELECT id, title, start_at, location, related_case
              FROM calendar_events
             WHERE start_at::date = (now() AT TIME ZONE 'Asia/Manila')::date
             ORDER BY start_at;
        """)
        events = cur.fetchall()
        if events:
            lines = [f"  • {e['start_at'].strftime('%H:%M')} {e['title'][:60]} ({e['related_case'] or '?'})" for e in events]
            sections["calendar"] = f"📅 <b>Today's events</b>\n" + "\n".join(lines)
    except Exception:
        pass

    # 6. Per-case 1-line status
    cur.execute("""
        SELECT case_file, name, project_status, priority_level,
               (SELECT count(*) FROM documents d WHERE d.case_file = c.case_file) AS doc_count
          FROM clients c
         WHERE case_file IS NOT NULL AND case_file != ''
         ORDER BY priority_level DESC NULLS LAST, name;
    """)
    cases = cur.fetchall()
    if cases:
        lines = []
        for cs in cases:
            status = cs["project_status"] or "(no status set)"
            prio = (cs["priority_level"] or "")[:3].upper()
            lines.append(f"  • {cs['case_file']} [{prio}] ({cs['doc_count']} docs): {status[:80]}")
        sections["cases"] = f"🗂 <b>Cases</b>\n" + "\n".join(lines)

    # 7. Watchdog / system health
    try:
        cur.execute("""
            SELECT count(*) FILTER (WHERE state = 'unhealthy') AS unhealthy_count
              FROM (VALUES (1)) v(x)
        """)  # placeholder — actual watchdog state lives in /var/lib/landtek/watchdog_state.json
    except Exception:
        pass

    try:
        with open("/var/lib/landtek/watchdog_state.json") as f:
            wd = json.load(f)
        last_change = datetime.fromtimestamp(wd.get("last_state_change", 0))
        sections["health"] = f"⚙️ <b>System</b>: Leo state = <b>{wd.get('state','?').upper()}</b> (since {last_change.strftime('%Y-%m-%d %H:%M UTC')})"
    except Exception:
        sections["health"] = "⚙️ <b>System</b>: watchdog state file unavailable"

    cur.close(); conn.close()
    return sections


def render_digest_messages():
    """Render digest as a list of Telegram-ready messages (≤4090 chars each)."""
    sections = build_digest_sections()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header = f"📊 <b>LandTek Daily Digest — {today}</b>\n\n"

    order = ["activity", "uploads", "inquiries", "action_items", "calendar", "cases", "health"]
    msgs = []
    buf = header
    for k in order:
        text = sections.get(k)
        if not text:
            continue
        chunk = text + "\n\n"
        if len(buf) + len(chunk) > 4000:
            msgs.append(buf)
            buf = chunk
        else:
            buf += chunk
    if buf.strip():
        msgs.append(buf)
    if not msgs:
        msgs.append(header + "Nothing notable to report.")
    return msgs


def main():
    msgs = render_digest_messages()
    print(f"  digest built: {len(msgs)} message(s)")
    for m in msgs:
        ok = tg_send(m)
        print(f"  sent {'✓' if ok else '✗'} ({len(m)} chars)")


if __name__ == "__main__":
    main()
