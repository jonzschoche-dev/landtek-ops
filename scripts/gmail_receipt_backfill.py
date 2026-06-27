#!/usr/bin/env python3
"""gmail_receipt_backfill.py — capture the TRUE Gmail receipt timestamp (internalDate) as received_at.

FORENSIC DATE INTEGRITY. Ingestion set both `sent_at` and `received_at` to the email's `Date:` header
(the SENDER'S CLAIMED send time), so "when we received it" was fiction — `sent_at == received_at` in all
570 rows, and Gmail's real receipt time was never stored (`raw_payload` has no `internalDate`). This
re-fetches each message's Gmail `internalDate` (when Gmail actually received it) and stores it as the true
`received_at`, leaving `sent_at` = the claimed `Date:` header. Now claimed-send and actual-receipt are
SEPARATE facts — the distinction a forensic corpus turns on (a letter's borne/sent date ≠ when it was
received; the AO-22 clock + the phantom-resolution arguments live here). Idempotent; re-runnable.

  python3 scripts/gmail_receipt_backfill.py --dry   [--limit N]   # fetch + show the gaps, NO write
  python3 scripts/gmail_receipt_backfill.py --apply [--limit N]   # set received_at = Gmail internalDate
"""
import argparse
import datetime
import email.utils
import sys
import time

sys.path.insert(0, "/root/landtek")
import psycopg2

from gmail_watcher import gmail_client

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--limit", type=int, default=10000)
    a = ap.parse_args()
    if not (a.apply or a.dry):
        print("pass --dry or --apply"); return

    svc = gmail_client()
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor()
    cur.execute("SELECT id, message_id, sent_at FROM gmail_messages "
                "WHERE message_id IS NOT NULL ORDER BY id LIMIT %s", (a.limit,))
    rows = cur.fetchall()
    updated = failed = 0
    diffs = []
    for did, mid, sent in rows:
        try:
            r = svc.users().messages().get(userId="me", id=mid, format="metadata",
                                           metadataHeaders=["Date"]).execute()
            internal_ms = int(r["internalDate"])
            hdr_date = next((h["value"] for h in r.get("payload", {}).get("headers", [])
                             if h.get("name", "").lower() == "date"), None)
        except Exception as e:
            failed += 1
            if a.dry:
                print(f"  ✗ {mid[:16]}: {type(e).__name__} {str(e)[:70]}")
            continue
        recv = datetime.datetime.fromtimestamp(internal_ms / 1000, datetime.timezone.utc)
        claimed = None
        if hdr_date:
            try:
                claimed = email.utils.parsedate_to_datetime(hdr_date)
            except Exception:
                claimed = None
        if a.apply:
            # received_at = TRUE Gmail receipt (internalDate); sent_at = the sender's CLAIMED send (Date: header)
            if claimed is not None:
                cur.execute("UPDATE gmail_messages SET received_at = to_timestamp(%s/1000.0), sent_at = %s WHERE id=%s",
                            (internal_ms, claimed, did))
            else:
                cur.execute("UPDATE gmail_messages SET received_at = to_timestamp(%s/1000.0) WHERE id=%s",
                            (internal_ms, did))
            updated += 1
            if updated % 100 == 0:
                print(f"  ...{updated} corrected")
        elif claimed is not None:
            gap_min = (recv - claimed).total_seconds() / 60
            if abs(gap_min) >= 1:
                diffs.append((mid, claimed, recv, gap_min))
        time.sleep(0.02)  # gentle on the Gmail API
    if a.dry:
        print(f"\n  sampled {len(rows)}: {len(diffs)} where Gmail-receipt ≠ claimed-send (≥1 min apart), "
              f"{failed} fetch-fail")
        for mid, claimed, recv, gap in diffs[:12]:
            print(f"    {mid[:16]}  claimed_send={claimed}  gmail_received={recv}  ({gap:+.0f}m)")
    else:
        print(f"\n  received_at corrected to Gmail internalDate: {updated} updated, {failed} failed "
              f"(sent_at left = the claimed Date: header)")


if __name__ == "__main__":
    main()
