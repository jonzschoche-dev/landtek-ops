#!/usr/bin/env python3
"""deploy_352 — All sent/received emails logged + full-text searchable.

1. gmail_messages.search_vector (GIN) — subject + body_plain
2. v_gmail_mailbox — direction + citation for every row
3. Backfill client_history for rows missing from spine (via scan_gmail)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from landtek_core import db


def main():
    with db() as cur:
        cur.execute("""
            ALTER TABLE gmail_messages
              ADD COLUMN IF NOT EXISTS search_vector tsvector
        """)
        cur.execute("""
            CREATE OR REPLACE FUNCTION gmail_messages_search_vector_update()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              NEW.search_vector :=
                setweight(to_tsvector('english', coalesce(NEW.subject, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(left(NEW.body_plain, 200000), '')), 'B') ||
                setweight(to_tsvector('simple', coalesce(NEW.from_addr, '')), 'C');
              RETURN NEW;
            END;
            $$
        """)
        cur.execute("""
            DROP TRIGGER IF EXISTS gmail_messages_search_vector_trigger ON gmail_messages
        """)
        cur.execute("""
            CREATE TRIGGER gmail_messages_search_vector_trigger
              BEFORE INSERT OR UPDATE OF subject, body_plain, from_addr
              ON gmail_messages
              FOR EACH ROW EXECUTE FUNCTION gmail_messages_search_vector_update()
        """)
        cur.execute("""
            UPDATE gmail_messages SET search_vector =
              setweight(to_tsvector('english', coalesce(subject, '')), 'A') ||
              setweight(to_tsvector('english', coalesce(left(body_plain, 200000), '')), 'B') ||
              setweight(to_tsvector('simple', coalesce(from_addr, '')), 'C')
             WHERE search_vector IS NULL
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_gmail_search_vector
              ON gmail_messages USING gin(search_vector)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_gmail_received_desc
              ON gmail_messages (received_at DESC NULLS LAST)
        """)
        cur.execute("""
            CREATE OR REPLACE VIEW v_gmail_mailbox AS
            SELECT g.id AS gmail_id,
                   'gmail#' || g.id::text AS citation,
                   CASE WHEN 'SENT' = ANY(COALESCE(g.labels, '{}'::text[]))
                        THEN 'SENT' ELSE 'RECEIVED' END AS direction,
                   COALESCE(g.received_at, g.sent_at) AS mail_at,
                   g.from_addr,
                   g.to_addrs,
                   g.subject,
                   g.client_code,
                   g.case_file,
                   g.matter_codes,
                   g.relevance_status,
                   g.has_attachments,
                   (EXISTS (
                      SELECT 1 FROM client_history h
                       WHERE h.source_table = 'gmail_messages'
                         AND h.source_id = g.id::text
                   )) AS in_client_history
              FROM gmail_messages g
        """)
        cur.execute("""
            INSERT INTO deploy_log (deploy_id, summary) VALUES (
              'deploy_352',
              'Email log+search: search_vector GIN on gmail_messages; v_gmail_mailbox view; '
              'client_history_scan logs ALL sent/received (Owner fallback); search_emails.py + /api/email_search.'
            )
            ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
        """)

    root = "/root/landtek" if os.path.isdir("/root/landtek") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    subprocess.run(
        [sys.executable, os.path.join(root, "client_history_scan.py")],
        check=True, timeout=180,
    )
    print("✓ deploy_352: email search index + full mailbox log on spine")


if __name__ == "__main__":
    main()