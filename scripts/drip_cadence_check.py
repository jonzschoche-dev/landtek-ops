#!/usr/bin/env python3
"""drip_cadence_check.py — run BEFORE drafting any outward message: has this address/office been touched recently?

Jonathan, 21 Oct 2026: "I think we sent too many emails about that make sure we dont do that again."
Rule: at most ONE message per office per 15 working days (~21 calendar days), unless the office has replied since
our last message. Corrections or extra asks wait for the office's reply, or go by phone/text instead.

  python3 scripts/drip_cadence_check.py smd.r5@denr.gov.ph [more addresses...]
Reads drip_event rows (kind 'sent'/'dispatched') whose detail mentions the address. Exit 1 = BLOCK (too soon).
"""
import os, sys, json, datetime
import psycopg2
DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WINDOW_DAYS = 21
def main(addrs):
    c = psycopg2.connect(DSN); cur = c.cursor()
    blocked = False
    for a in addrs:
        cur.execute("""SELECT created_at, detail FROM drip_event WHERE kind IN ('sent','dispatched')
                       AND detail::text ILIKE %s AND created_at > now() - interval '%s days' ORDER BY created_at DESC""",
                    (f"%{a}%", WINDOW_DAYS))
        rows = cur.fetchall()
        if rows:
            blocked = True
            print(f"BLOCK {a}: {len(rows)} message(s) in the last {WINDOW_DAYS} days; last {rows[0][0]:%d %b %Y %H:%M}. "
                  "Wait for their reply, or use phone/text.")
        else:
            print(f"OK    {a}: no message in the last {WINDOW_DAYS} days")
    return 1 if blocked else 0
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
