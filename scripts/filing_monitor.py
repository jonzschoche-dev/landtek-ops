#!/usr/bin/env python3
"""filing_monitor.py — resident agent (Discovery): watch email for incoming filings & alert. $0.

Watches the ingested gmail feed for NEW filing-related messages tied to a matter — court orders,
resolutions, opposing motions/comments/oppositions, agency notices/referrals — from senders OTHER than
the operator, and records them in `filing_alerts` so nothing slips past before a deadline. Each new
filing triggers ONE plain Telegram line to the operator via tg_send (which enforces the S14
one-message / no-double-tap rules). It never acts on a filing — it surfaces it for the operator +
counsel. This is the 'opponent/court files → Discovery alerts Leo' step. Matter-classified + legal
sender is the filter, so Amazon/newsletter 'order' noise is excluded.

  python3 scripts/filing_monitor.py            # scan -> new filing_alerts (+ notify)
  python3 scripts/filing_monitor.py --report
"""
import argparse
import subprocess

import psycopg2

from agent_alert import emit  # unified decision log (scripts/ is on sys.path when run as a script)

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
TG_SEND = "/root/landtek/scripts/tg_send.py"
KW = r"order|motion|resolution|notice of|hearing|summons|opposition|comment|manifestation|decision|writ|referral|subpoena"


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True
    return c


def scan(cur, notify):
    cur.execute("""CREATE TABLE IF NOT EXISTS filing_alerts (
        message_id text PRIMARY KEY, matter_code text, subject text, sender text,
        received date, alerted_at timestamptz DEFAULT now(), notified bool DEFAULT false)""")
    cur.execute(f"""
        SELECT message_id, array_to_string(matter_codes,',') mc, subject,
               coalesce(from_name,from_addr) sender, coalesce(sent_at,received_at,ingested_at)::date d
        FROM gmail_messages g
        WHERE coalesce(array_length(matter_codes,1),0) >= 1
          AND subject ~* %s
          AND coalesce(from_addr,'') !~* 'jonzschoche|jonathan|hayuma'
          AND coalesce(sent_at,received_at,ingested_at) > now() - interval '90 days'
          AND NOT EXISTS (SELECT 1 FROM filing_alerts f WHERE f.message_id = g.message_id)
        ORDER BY coalesce(sent_at,received_at,ingested_at)
    """, (KW,))
    new = cur.fetchall()
    for mid, mc, subj, sender, d in new:
        cur.execute("""INSERT INTO filing_alerts (message_id,matter_code,subject,sender,received)
                       VALUES (%s,%s,%s,%s,%s) ON CONFLICT (message_id) DO NOTHING""",
                    (mid, mc, (subj or "")[:200], (sender or "")[:120], d))
        emit("filing_monitor", "new_filing",
             f"New filing in {mc}: {(subj or '').strip()[:120]} (from {sender})",
             matter=((mc or "").split(",")[0] or None), severity="high", dedup_key=f"filing:{mid}")
    notified = 0
    if notify:
        for mid, mc, subj, sender, d in new:
            msg = f"New filing in {mc}: {(subj or '').strip()[:140]} (from {sender})"
            try:
                # tg_send.py <chat_id> <source> <text>; 6513067717 = operator; it self-enforces S14
                r = subprocess.run(["python3", TG_SEND, "6513067717", "filing_monitor", msg],
                                   capture_output=True, timeout=30)
                ok = r.returncode == 0
            except Exception:
                ok = False
            cur.execute("UPDATE filing_alerts SET notified=%s WHERE message_id=%s", (ok, mid))
            notified += 1 if ok else 0
    return len(new), notified


def report(cur):
    cur.execute("""SELECT matter_code, received, left(subject,56), notified FROM filing_alerts
                   ORDER BY received DESC NULLS LAST LIMIT 15""")
    rows = cur.fetchall()
    print("=" * 72); print(f"FILING MONITOR — recent incoming filings ({len(rows)} shown)"); print("=" * 72)
    for mc, d, subj, notif in rows:
        print(f"  {str(d):12} [{mc}] {subj}  {'🔔' if notif else '·'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--no-notify", action="store_true")
    a = ap.parse_args()
    c = _conn(); cur = c.cursor()
    if not a.report:
        n, notified = scan(cur, notify=not a.no_notify)
        print(f"[filing-monitor] {n} new filing(s) recorded · {notified} operator-notified")
    report(c.cursor())


if __name__ == "__main__":
    main()
