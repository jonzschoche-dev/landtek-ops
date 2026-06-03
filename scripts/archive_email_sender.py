#!/usr/bin/env python3
"""archive_email_sender.py — one-command "stop showing me emails from X."

Usage:
  archive_email_sender.py listings@redfin.com       # exact address
  archive_email_sender.py @redfin.com               # whole domain (@ prefix)
  archive_email_sender.py redfin.com                # also whole domain (no @)
  archive_email_sender.py --show jbaris@unconnected.org  # whitelist (always surface)

If you don't pass --show, the default disposition is 'archive' (suppress from
digest)."""
from __future__ import annotations
import argparse
import os
import sys
import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sender")
    ap.add_argument("--show", action="store_true", help="set to disposition='show' (whitelist)")
    ap.add_argument("--critical-only", action="store_true", help="set to disposition='critical_only'")
    ap.add_argument("--reason", default="manual via archive_email_sender.py")
    args = ap.parse_args()

    s = args.sender.strip()
    is_domain = "@" in s and s.startswith("@") or ("@" not in s and "." in s)
    if is_domain:
        domain = s.lstrip("@")
        addr = None
    else:
        addr = s
        domain = None

    disposition = "show" if args.show else ("critical_only" if args.critical_only else "archive")

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'archive_email_sender.py'")
    cur.execute(
        """
        INSERT INTO email_sender_disposition (sender_address, sender_domain, disposition, reason, added_by)
        VALUES (%s, %s, %s, %s, 'jonathan')
        ON CONFLICT DO NOTHING
        RETURNING id, sender_address, sender_domain, disposition
        """,
        (addr, domain, disposition, args.reason),
    )
    r = cur.fetchone()
    conn.commit()
    if r:
        target = r["sender_address"] or "@" + r["sender_domain"]
        print(f"✓ #{r['id']}  {target}  → disposition={r['disposition']}")
    else:
        print(f"· already exists: {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
