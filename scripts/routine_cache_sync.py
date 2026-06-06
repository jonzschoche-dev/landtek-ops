#!/usr/bin/env python3
"""routine_cache_sync.py — deploy_340 companion.

Reconciles drift between `documents` (source of truth) and `client_history`
(read-cache the bible queries). Today's session surfaced the pattern:
documents.case_file or documents.doc_date got UPDATED, but client_history
rows still cached the old values, so the bible kept showing wrong data.

Algorithm (every 5 min via systemd):
  1. Find client_history rows where source_table = 'documents' and the
     cached case_file / event_date doesn't match the live documents row.
  2. For each, UPDATE client_history to match documents — preserve other
     enrichment fields (matter_codes, title_refs, party_refs, etc.).
  3. Log delta. Emit strict-rails Telegram alert if drift count > THRESHOLD.

Idempotent. Pure SQL. $0 LLM cost.

Pairs with the existing source-of-truth design: documents is canonical;
client_history is a denormalized read cache. Drift = bug.

Usage:
    python3 scripts/routine_cache_sync.py
    python3 scripts/routine_cache_sync.py --dry-run
    python3 scripts/routine_cache_sync.py --since 2026-06-06   # only docs touched after
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ALERT_THRESHOLD = 20  # if more than this many fixes in one run, ping Jonathan


def find_drift(cur, since: str | None):
    """Returns list of dicts with client_history.id + the live document state."""
    where_extra = "AND d.updated_at >= %s" if since else ""
    params = (since,) if since else ()
    # documents.doc_date is TEXT (legacy). Cast safely: only well-formed
    # YYYY-MM-DD strings → date; anything else (NULL, '?', 'NO_DATE', empty) → NULL.
    cur.execute(f"""
        SELECT ch.id AS ch_id,
               ch.case_file AS ch_case_file,
               ch.event_date AS ch_event_date,
               ch.client_code AS ch_client_code,
               d.id AS doc_id,
               d.case_file AS live_case_file,
               CASE
                 WHEN d.doc_date ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}$' THEN d.doc_date::date
                 ELSE NULL
               END AS live_doc_date,
               d.classification
          FROM client_history ch
          JOIN documents d ON d.id::text = ch.source_id
         WHERE ch.source_table = 'documents'
           AND (
                  ch.case_file IS DISTINCT FROM d.case_file
               OR ch.event_date IS DISTINCT FROM (
                    CASE
                      WHEN d.doc_date ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}$' THEN d.doc_date::date
                      ELSE NULL
                    END
                  )
           )
           {where_extra}
         ORDER BY ch.id
    """, params)
    return cur.fetchall()


def apply_fix(cur, row: dict, dry_run: bool) -> bool:
    if dry_run:
        return True
    cur.execute("""
        UPDATE client_history
           SET case_file = %s,
               client_code = COALESCE(%s, client_code),
               event_date = %s,
               event_datetime = CASE WHEN %s IS NULL THEN NULL
                                     ELSE event_datetime END
         WHERE id = %s
    """, (row["live_case_file"], row["live_case_file"],
          row["live_doc_date"], row["live_doc_date"], row["ch_id"]))
    return cur.rowcount > 0


def push_alert(count: int):
    try:
        sys.path.insert(0, "/root/landtek/scripts")
        from report_publisher import push_strict
        push_strict(
            headline=f"⚠ cache_sync drift: {count} client_history rows fixed",
            body_md=(f"## Cache drift alert\n\n"
                     f"`routine_cache_sync.py` reconciled **{count}** drifted "
                     f"`client_history` rows against live `documents`. "
                     f"Threshold = {ALERT_THRESHOLD}.\n\n"
                     f"If this number stays high run-over-run, an ingestion "
                     f"trigger is missing — investigate the writer that's not "
                     f"updating client_history when documents change."),
            source="watchdog",
            slug=f"cache-sync-{datetime.now(timezone.utc):%Y%m%d-%H%M}",
        )
    except Exception as e:
        print(f"  alert push failed: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="only docs updated_at >= this date")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[cache_sync] {started} dry_run={args.dry_run} since={args.since}")
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    drift = find_drift(cur, args.since)
    if not drift:
        print("  ✓ no drift detected — caches are in sync")
        return

    fixed = 0
    samples = []
    for row in drift:
        if apply_fix(cur, row, args.dry_run):
            fixed += 1
            if len(samples) < 6:
                samples.append(
                    f"ch#{row['ch_id']} doc#{row['doc_id']}: "
                    f"case_file {row['ch_case_file']!r}→{row['live_case_file']!r} "
                    f"event_date {row['ch_event_date']}→{row['live_doc_date']}"
                )

    print(f"[cache_sync] fixed={fixed} (of {len(drift)} drift rows)")
    for s in samples:
        print(f"  · {s}")

    if fixed >= ALERT_THRESHOLD and not args.dry_run:
        push_alert(fixed)

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
