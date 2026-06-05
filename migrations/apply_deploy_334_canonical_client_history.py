#!/usr/bin/env python3
"""apply_deploy_334_canonical_client_history.py — surface what's already built.

The client_history table exists with 1,275 events across 9 source tables.
Leo just can't see it per-turn. This deploy:

  (1) Cleans casing duplicates: 'mwk' → 'MWK-001' (10 events),
      'paracale' → 'Paracale-001' (1).
  (2) Fixes 1 future-dated event (2029-10-23 → NULL with note).
  (3) Adds v_client_recent_history view (last 30d, ordered).
  (4) Adds v_client_history_summary view (counts by kind for scale).
  (5) Leo's Context Builder is updated by refresh_client_history.py
      (companion script — 10-min cron, SQL-only, $0 token cost).

No LLM calls in this deploy. Pure SQL.
"""
from __future__ import annotations
import os, psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()

    # ── (1) canonical casing fixes ────────────────────────────────────
    cur.execute("UPDATE client_history SET client_code='MWK-001' WHERE client_code='mwk'")
    print(f"  fixed 'mwk' → 'MWK-001': {cur.rowcount} rows")
    cur.execute("UPDATE client_history SET client_code='Paracale-001' WHERE client_code='paracale'")
    print(f"  fixed 'paracale' → 'Paracale-001': {cur.rowcount} rows")

    # ── (2) bad future date → NULL with note ──────────────────────────
    cur.execute("""
        UPDATE client_history
           SET event_date = NULL,
               what_summary = what_summary || ' [date scrubbed — was 2029-10-23, likely OCR/transcription error]'
         WHERE event_date = DATE '2029-10-23'
           AND NOT what_summary LIKE '%date scrubbed%'
    """)
    print(f"  scrubbed 2029-10-23 future date: {cur.rowcount} rows")

    # ── (3) per-client recent timeline view ───────────────────────────
    cur.execute("""
        CREATE OR REPLACE VIEW v_client_recent_history AS
        SELECT id, client_code, case_file, matter_code,
               event_date, event_datetime, event_kind, event_kind_canonical,
               source_table, source_id, who_from, who_to,
               LEFT(what_summary, 200) AS what_short,
               what_summary AS what_full,
               provenance, citation_ref
          FROM client_history
         WHERE COALESCE(event_date, event_datetime::date) > current_date - interval '30 days'
            OR ingested_at > now() - interval '30 days'
         ORDER BY COALESCE(event_datetime, event_date::timestamptz) DESC NULLS LAST
    """)
    print("  ✓ v_client_recent_history (last 30 days)")

    # ── (4) per-client SUMMARY view (for scale — drop into prompt cheaply) ──
    cur.execute("""
        CREATE OR REPLACE VIEW v_client_history_summary AS
        SELECT client_code,
               COUNT(*) AS total_events_lifetime,
               COUNT(*) FILTER (WHERE COALESCE(event_date, event_datetime::date) > current_date - interval '30 days') AS events_30d,
               COUNT(*) FILTER (WHERE COALESCE(event_date, event_datetime::date) > current_date - interval '7 days')  AS events_7d,
               MAX(COALESCE(event_datetime, event_date::timestamptz)) AS most_recent_event,
               -- Compact breakdown by canonical kind in last 30 days
               json_object_agg(
                 event_kind_canonical,
                 events_by_kind
               ) FILTER (WHERE event_kind_canonical IS NOT NULL) AS kind_30d_breakdown
          FROM (
            SELECT client_code,
                   event_date, event_datetime, event_kind_canonical, ingested_at,
                   COUNT(*) OVER (PARTITION BY client_code, event_kind_canonical) AS events_by_kind
              FROM client_history
             WHERE COALESCE(event_date, event_datetime::date) > current_date - interval '30 days'
                OR ingested_at > now() - interval '30 days'
          ) sub
         GROUP BY client_code
         ORDER BY events_30d DESC NULLS LAST
    """)
    print("  ✓ v_client_history_summary (per-client counts, scale-safe)")

    cur.execute("""
        INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_334',
         'Canonical client_history surfaced to Leo. Casing fixes (mwk → MWK-001, paracale → Paracale-001), future-date scrub, v_client_recent_history + v_client_history_summary views. Zero LLM calls — pure SQL. Companion refresh_client_history.py wires it into Context Builder.')
        ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary
    """)
    cur.execute("SELECT client_code, total_events_lifetime, events_30d, events_7d, most_recent_event::date FROM v_client_history_summary")
    print("\n=== client_history summary (post-cleanup) ===")
    for r in cur.fetchall():
        print(f"  {r[0]:20s} lifetime={r[1]:5d}  30d={r[2]:3d}  7d={r[3]:3d}  latest={r[4]}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
