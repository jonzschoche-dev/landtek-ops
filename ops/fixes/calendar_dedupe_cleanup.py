#!/usr/bin/env python3
"""One-off cleanup for the Agenda Engine duplicate bug (22 Oct 2026). Dry-run by default.
Targets ONLY calendar_sync_map rows with landtek_uid 'surfaced_deadlines:<id>' (old unstable key)
whose source row label matches --label (default: the DILG-supervision DRIP edition). Never touches
'event:*' rows (e.g. event:38, the 8:00 AM 'DRIP edition due' entry).
  python3 calendar_dedupe_cleanup.py --calendar jonathan@hayuma.org            # list only
  python3 calendar_dedupe_cleanup.py --calendar jonathan@hayuma.org --apply    # delete in GCal + mark map 'deleted'
  --all-stale  widens to every old-key surfaced_deadlines row (351 as of 22 Oct), still dry-run unless --apply.
"""
import argparse, sys
sys.path.insert(0, "/root/landtek/scripts")
import psycopg2
ap = argparse.ArgumentParser()
ap.add_argument("--calendar", required=True)
ap.add_argument("--label", default="DRIP edition: DILG-supervision schedule re-issue")
ap.add_argument("--all-stale", action="store_true")
ap.add_argument("--apply", action="store_true")
a = ap.parse_args()
conn = psycopg2.connect(""); cur = conn.cursor()
q = ("SELECT m.landtek_uid, m.gcal_event_id, s.due_date, s.label FROM calendar_sync_map m "
     "JOIN surfaced_deadlines s ON m.landtek_uid = 'surfaced_deadlines:' || s.id "
     "WHERE m.gcal_calendar_id=%s AND m.status='active' AND m.landtek_uid ~ '^surfaced_deadlines:[0-9]+$'")
args = [a.calendar]
if not a.all_stale:
    q += " AND s.label=%s"; args.append(a.label)
cur.execute(q + " ORDER BY s.id", args)
rows = cur.fetchall()
print(f"{len(rows)} target events ({'APPLY' if a.apply else 'dry-run'})")
for uid, gid, d, lbl in rows: print(f"  {uid}\t{d}\t{gid}\t{lbl[:70]}")
if not a.apply: sys.exit(0)
import calendar_sync as CS
svc = CS.get_service() if hasattr(CS, "get_service") else CS.build_service()
n = 0
for uid, gid, d, lbl in rows:
    try:
        svc.events().delete(calendarId=a.calendar, eventId=gid).execute()
    except Exception as e:
        if "410" not in str(e) and "404" not in str(e): print("  [ERR]", uid, e); continue
    cur.execute("UPDATE calendar_sync_map SET status='deleted', last_synced_at=now() WHERE landtek_uid=%s AND gcal_calendar_id=%s", (uid, a.calendar))
    conn.commit(); n += 1
print(f"removed {n}")
