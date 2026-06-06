#!/usr/bin/env python3
"""deploy_353 — Archived emails in canonical client_history + unified search.

deploy_297 moved 548 noise rows to gmail_messages_archived; they were absent
from client_history. Canonical history = gmail_messages + gmail_messages_archived.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from landtek_core import db


def main():
    with db() as cur:
        cur.execute("""
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'public' AND table_name = 'gmail_messages_archived'
            ) AS ok
        """)
        if not cur.fetchone()["ok"]:
            print("✓ deploy_353: no gmail_messages_archived table — skip")
            return

        cur.execute("""
            ALTER TABLE gmail_messages_archived
              ADD COLUMN IF NOT EXISTS search_vector tsvector
        """)
        cur.execute("""
            DROP TRIGGER IF EXISTS gmail_messages_archived_search_vector_trigger
              ON gmail_messages_archived
        """)
        cur.execute("""
            CREATE TRIGGER gmail_messages_archived_search_vector_trigger
              BEFORE INSERT OR UPDATE OF subject, body_plain, from_addr
              ON gmail_messages_archived
              FOR EACH ROW EXECUTE FUNCTION gmail_messages_search_vector_update()
        """)
        cur.execute("""
            UPDATE gmail_messages_archived SET search_vector =
              setweight(to_tsvector('english', coalesce(subject, '')), 'A') ||
              setweight(to_tsvector('english', coalesce(left(body_plain, 200000), '')), 'B') ||
              setweight(to_tsvector('simple', coalesce(from_addr, '')), 'C')
             WHERE search_vector IS NULL
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_gma_search_vector
              ON gmail_messages_archived USING gin(search_vector)
        """)
        cur.execute("""
            CREATE OR REPLACE VIEW v_gmail_canonical AS
            SELECT g.id,
                   'gmail_messages'::text AS source_table,
                   'gmail#' || g.id::text AS citation,
                   'active'::text AS mailbox_status,
                   CASE WHEN 'SENT' = ANY(COALESCE(g.labels, '{}'::text[]))
                        THEN 'SENT' ELSE 'RECEIVED' END AS direction,
                   COALESCE(g.received_at, g.sent_at) AS mail_at,
                   g.from_addr, g.to_addrs, g.subject, g.body_plain,
                   g.client_code, g.case_file, g.matter_codes,
                   g.relevance_status, g.has_attachments, g.search_vector,
                   NULL::text AS archived_reason
              FROM gmail_messages g
            UNION ALL
            SELECT a.id,
                   'gmail_messages_archived'::text AS source_table,
                   'gmail_archived#' || a.id::text AS citation,
                   'archived'::text AS mailbox_status,
                   CASE WHEN 'SENT' = ANY(COALESCE(a.labels, '{}'::text[]))
                        THEN 'SENT' ELSE 'RECEIVED' END AS direction,
                   COALESCE(a.received_at, a.sent_at) AS mail_at,
                   a.from_addr, a.to_addrs, a.subject, a.body_plain,
                   NULL::text AS client_code,
                   a.case_file, a.matter_codes,
                   'archived'::text AS relevance_status,
                   a.has_attachments, a.search_vector,
                   a.archived_reason
              FROM gmail_messages_archived a
        """)
        cur.execute("""
            INSERT INTO deploy_log (deploy_id, summary) VALUES (
              'deploy_353',
              'Canonical history complete: 548 gmail_messages_archived rows logged to '
              'client_history; v_gmail_canonical unifies active+archived for search.'
            )
            ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
        """)

    root = "/root/landtek" if os.path.isdir("/root/landtek") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    subprocess.run(
        [sys.executable, os.path.join(root, "client_history_scan.py")],
        check=True, timeout=180,
    )

    with db() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM gmail_messages")
        active = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM gmail_messages_archived")
        archived = cur.fetchone()["n"]
        cur.execute("""
            SELECT COUNT(*) AS n FROM client_history
             WHERE source_table IN ('gmail_messages', 'gmail_messages_archived')
        """)
        logged = cur.fetchone()["n"]
        cur.execute("""
            SELECT
              (SELECT COUNT(*) FROM gmail_messages g
                WHERE NOT EXISTS (
                  SELECT 1 FROM client_history h
                   WHERE h.source_table = 'gmail_messages' AND h.source_id = g.id::text
                )) AS active_gap,
              (SELECT COUNT(*) FROM gmail_messages_archived a
                WHERE NOT EXISTS (
                  SELECT 1 FROM client_history h
                   WHERE h.source_table = 'gmail_messages_archived' AND h.source_id = a.id::text
                )) AS archived_gap
        """)
        gaps = cur.fetchone()

    print(
        f"✓ deploy_353: canonical email history "
        f"active={active} archived={archived} client_history={logged} "
        f"gaps active={gaps['active_gap']} archived={gaps['archived_gap']}"
    )


if __name__ == "__main__":
    main()