#!/usr/bin/env python3
"""deploy_354 — Canonical history = legal-event emails only.

Jonathan 2026-06-06: an email is a legal event — an action which may require
a reaction or to be noted for further development of a situation.

1. Purge gmail rows from client_history (352/353 logged all mail + archived noise)
2. Re-scan via is_legal_event_email() in correspondence_spine
3. v_gmail_relevant — searchable legal events on spine (active mailbox)
4. v_gmail_canonical unchanged — full audit corpus with --all-mail
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from landtek_core import db


def main():
    with db() as cur:
        cur.execute("""
            SELECT COUNT(*) AS n FROM client_history
             WHERE source_table IN ('gmail_messages', 'gmail_messages_archived')
        """)
        before = cur.fetchone()["n"]

        cur.execute("""
            DELETE FROM client_history
             WHERE source_table IN ('gmail_messages', 'gmail_messages_archived')
        """)
        purged = cur.rowcount

        cur.execute("""
            CREATE OR REPLACE VIEW v_gmail_relevant AS
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
             WHERE EXISTS (
                   SELECT 1 FROM client_history h
                    WHERE h.source_table = 'gmail_messages'
                      AND h.source_id = g.id::text
               )
        """)
        cur.execute("""
            INSERT INTO deploy_log (deploy_id, summary) VALUES (
              'deploy_354',
              'Legal-event email policy: client_history = reaction/note-worthy mail only '
              '(matter-linked, agency/counsel, filings/orders/hearings). Archived promos '
              'stay in gmail_messages_archived + v_gmail_canonical; v_gmail_relevant = spine.'
            )
            ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
        """)

    root = (
        "/root/landtek"
        if os.path.isdir("/root/landtek")
        else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    subprocess.run(
        [sys.executable, os.path.join(root, "client_history_scan.py")],
        check=True,
        timeout=180,
    )

    with db() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM gmail_messages")
        active = cur.fetchone()["n"]
        cur.execute("""
            SELECT COUNT(*) AS n FROM client_history
             WHERE source_table = 'gmail_messages'
        """)
        logged = cur.fetchone()["n"]
        cur.execute("""
            SELECT COUNT(*) AS n FROM client_history
             WHERE source_table = 'gmail_messages_archived'
        """)
        archived_logged = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM v_gmail_relevant")
        relevant_view = cur.fetchone()["n"]

    print(
        f"✓ deploy_354: legal-event email policy "
        f"purged={purged} (was {before}) "
        f"active_mailbox={active} spine={logged} "
        f"archived_on_spine={archived_logged} v_gmail_relevant={relevant_view}"
    )


if __name__ == "__main__":
    main()