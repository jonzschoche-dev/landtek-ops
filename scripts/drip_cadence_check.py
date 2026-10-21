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
# PG_DSN wins; otherwise try the VPS-native address, then the Mac tunnel (ssh -L 15432).
DSNS = [os.environ["PG_DSN"]] if os.environ.get("PG_DSN") else [
    "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n", "postgresql://n8n:n8npassword@127.0.0.1:15432/n8n"]
def connect():
    for d in DSNS:
        try:
            return psycopg2.connect(d, connect_timeout=5)
        except psycopg2.OperationalError:
            continue
    raise SystemExit("drip_cadence_check: database unreachable (VPS address and Mac tunnel both failed)")
WINDOW_DAYS = 21
def main(addrs):
    c = connect(); cur = c.cursor()
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
