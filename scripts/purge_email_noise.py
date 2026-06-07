#!/usr/bin/env python3
"""purge_email_noise.py — archive promotional/system mail out of the active KB.

Moves polluting rows from gmail_messages → gmail_messages_archived, deletes
client_history + correspondence_links for those rows. Idempotent.

Usage:
  python3 scripts/purge_email_noise.py           # scan all active mail
  python3 scripts/purge_email_noise.py --dry-run
  python3 scripts/purge_email_noise.py --hours 72 # recent only
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from correspondence_spine import archive_gmail_noise, is_kb_pollution_email  # noqa: E402
from landtek_core import db  # noqa: E402


def _raw_category(row: dict) -> str | None:
    raw = row.get("raw_payload") or {}
    return raw.get("category") if isinstance(raw, dict) else None


def purge(*, dry_run: bool = False, hours: int | None = None) -> dict:
    stats = {"scanned": 0, "archived": 0, "history_deleted": 0, "links_deleted": 0}
    with db() as cur:
        if hours:
            cur.execute(
                """
                SELECT * FROM gmail_messages
                 WHERE COALESCE(received_at, sent_at, ingested_at)
                       > now() - (%s || ' hours')::interval
                 ORDER BY id
                """,
                (str(hours),),
            )
        else:
            cur.execute("SELECT * FROM gmail_messages ORDER BY id")
        rows = cur.fetchall()

        for row in rows:
            stats["scanned"] += 1
            if not is_kb_pollution_email(
                from_addr=row.get("from_addr"),
                subject=row.get("subject"),
                body_plain=row.get("body_plain"),
                relevance_status=row.get("relevance_status"),
                matter_codes=list(row.get("matter_codes") or []),
                raw_category=_raw_category(row),
            ):
                continue

            if dry_run:
                print(
                    f"  [DRY] gmail#{row['id']} "
                    f"{(row.get('from_addr') or '')[:40]} "
                    f"{(row.get('subject') or '')[:60]}"
                )
                stats["archived"] += 1
                continue

            gid = row["id"]
            cur.execute(
                "SELECT COUNT(*) AS n FROM client_history "
                "WHERE source_table = 'gmail_messages' AND source_id = %s",
                (str(gid),),
            )
            stats["history_deleted"] += cur.fetchone()["n"] or 0
            cur.execute(
                "SELECT COUNT(*) AS n FROM correspondence_links WHERE gmail_id = %s",
                (gid,),
            )
            stats["links_deleted"] += cur.fetchone()["n"] or 0
            archive_gmail_noise(
                cur, row,
                reason="kb_pollution_purge",
                archived_by="purge_email_noise",
            )
            stats["archived"] += 1

    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--hours", type=int, default=None, help="limit to recent mail")
    args = ap.parse_args()
    stats = purge(dry_run=args.dry_run, hours=args.hours)
    label = "would archive" if args.dry_run else "archived"
    print(
        f"✓ purge_email_noise: scanned={stats['scanned']} {label}={stats['archived']} "
        f"history_deleted={stats['history_deleted']} links_deleted={stats['links_deleted']}"
    )


if __name__ == "__main__":
    main()