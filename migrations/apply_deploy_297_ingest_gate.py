#!/usr/bin/env python3
"""Deploy 297 — refuse noise at the ingestion gate, retroactively purge.

Jonathan: 'this Redfin should have never made it into the DB.'

Current architecture (wrong):
  gmail_watcher → gmail_messages (everything) → email_briefer post-filters

New architecture (right):
  gmail_watcher → check email_sender_disposition → if 'archive' → write
    a stub row to gmail_messages_archived (audit only); skip gmail_messages.
  → if 'show'/NULL/'critical_only' → write to gmail_messages as normal.

This deploy:

  A. SCHEMA — gmail_messages_archived audit table (LIKE gmail_messages, with
     archived_at + archived_reason).

  B. RETROACTIVE — move existing noise rows from gmail_messages →
     gmail_messages_archived. Today that's ~27 Redfin/etc. rows from the last
     24h plus any older noise that matches the disposition table.

  C. INGESTION GATE — patch gmail_watcher.py to consult the disposition table
     BEFORE inserting. If archive: insert into gmail_messages_archived only.
     The autolink trigger therefore never fires for noise; the digest never
     sees it; downstream queries are clean.

  D. RESTORE HELPER — scripts/restore_email_message.py for the rare case
     ("oh wait, that one was actually relevant"): moves the row back from
     archived → main and re-triggers autolink.

Idempotent."""
from __future__ import annotations
import os
import sys
import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ACTOR = "jonathan_deploy_297"

SCHEMA_SQL = """
-- A. gmail_messages_archived: same shape as gmail_messages + provenance fields.
-- Using LIKE INCLUDING ALL copies columns, defaults, NOT NULL, and indexes
-- (but not foreign keys — we explicitly skip those, archived stays a leaf).
CREATE TABLE IF NOT EXISTS gmail_messages_archived (
    LIKE gmail_messages INCLUDING DEFAULTS INCLUDING CONSTRAINTS
);
ALTER TABLE gmail_messages_archived ADD COLUMN IF NOT EXISTS archived_at     timestamptz NOT NULL DEFAULT now();
ALTER TABLE gmail_messages_archived ADD COLUMN IF NOT EXISTS archived_reason text;
ALTER TABLE gmail_messages_archived ADD COLUMN IF NOT EXISTS archived_by     text;

-- LIKE INCLUDING CONSTRAINTS does NOT copy UNIQUE constraints in PG (they're
-- expressed as indexes). Add it explicitly so the gate's ON CONFLICT works.
DO $$ BEGIN
  ALTER TABLE gmail_messages_archived ADD CONSTRAINT gma_message_id_uniq UNIQUE (message_id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS idx_gma_from_addr  ON gmail_messages_archived(from_addr);
CREATE INDEX IF NOT EXISTS idx_gma_archived_at ON gmail_messages_archived(archived_at DESC);

-- A helper view: see what got suppressed in the last 7 days
CREATE OR REPLACE VIEW gmail_ingest_skipped_7d AS
  SELECT archived_at::date AS day,
         COUNT(*) AS skipped,
         COUNT(DISTINCT from_addr) AS unique_senders,
         STRING_AGG(DISTINCT SPLIT_PART(LOWER(COALESCE((regexp_match(from_addr, '<([^>]+)>'))[1], from_addr)), '@', 2), ', ') AS sample_domains
    FROM gmail_messages_archived
   WHERE archived_at > now() - INTERVAL '7 days'
   GROUP BY 1
   ORDER BY 1 DESC;
"""


def main() -> int:
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = %s", (ACTOR,))

    print("Deploy 297 — ingestion gate + retroactive purge")
    print("=" * 52)

    print("\n  A) Schema")
    cur.execute(SCHEMA_SQL)
    print("    ✓ gmail_messages_archived + gmail_ingest_skipped_7d view")

    # B. Retroactive purge — move existing noise rows over.
    # Match by bare_address OR bare_domain against email_sender_disposition.
    print("\n  B) Retroactive purge — move existing noise rows")
    cur.execute(
        """
        WITH targets AS (
          SELECT g.id
            FROM gmail_messages g
            JOIN email_sender_disposition d
              ON d.disposition = 'archive'
             AND (
                  d.sender_address = LOWER(COALESCE((regexp_match(g.from_addr, '<([^>]+)>'))[1], g.from_addr))
               OR d.sender_domain  = LOWER(SPLIT_PART(COALESCE((regexp_match(g.from_addr, '<([^>]+)>'))[1], g.from_addr), '@', 2))
             )
        ),
        moved AS (
          DELETE FROM gmail_messages g
           USING targets t WHERE g.id = t.id
          RETURNING g.*
        )
        INSERT INTO gmail_messages_archived
          SELECT m.*, now() AS archived_at,
                 'retroactive_purge_deploy_297' AS archived_reason,
                 'jonathan' AS archived_by
            FROM moved m
        RETURNING id, from_addr, subject
        """
    )
    rows = cur.fetchall()
    print(f"    ✓ moved {len(rows)} row(s) to gmail_messages_archived")
    if rows:
        for r in rows[:8]:
            print(f"      • #{r['id']}  {(r['from_addr'] or '?')[:50]}  {(r['subject'] or '')[:60]}")
        if len(rows) > 8:
            print(f"      … +{len(rows) - 8} more")

    conn.commit()

    # C. Verify what's left in gmail_messages
    print("\n  C) Verify gmail_messages now clean")
    cur.execute("SELECT COUNT(*) AS n FROM gmail_messages WHERE ingested_at > now() - INTERVAL '24 hours'")
    n = cur.fetchone()["n"]
    print(f"    gmail_messages last 24h: {n}")
    cur.execute("SELECT COUNT(*) AS n FROM gmail_messages_archived WHERE archived_at > now() - INTERVAL '24 hours'")
    arc = cur.fetchone()["n"]
    print(f"    gmail_messages_archived last 24h: {arc}")

    print("\n  ✓ COMMITTED")
    cur.close()
    conn.close()

    print("\n  Next step: patch gmail_watcher.py to refuse archive-disposition senders at ingestion.")
    print("  That happens in a sibling commit; this migration handles schema + retro purge.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
