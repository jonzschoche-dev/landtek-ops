#!/usr/bin/env python3
"""deploy_368 — Eradicate KB-polluting email from active tables.

1. Purge noise from gmail_messages → gmail_messages_archived
2. Scrub client_history + correspondence_links for archived noise
3. Tighten v_correspondence_triage to exclude noise status
4. Re-run client_history_scan (spine gate now blocks mis-tagged promos)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from landtek_core import db


def main():
    root = (
        "/root/landtek"
        if os.path.isdir("/root/landtek")
        else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    purge = os.path.join(root, "scripts", "purge_email_noise.py")
    subprocess.run([sys.executable, purge], check=True, timeout=300)

    with db() as cur:
        cur.execute("""
            CREATE OR REPLACE VIEW v_correspondence_triage AS
            SELECT g.id AS gmail_id,
                   g.client_code,
                   g.case_file,
                   g.matter_codes,
                   g.relevance_status,
                   g.from_addr,
                   LEFT(g.subject, 120) AS subject_short,
                   g.sent_at,
                   g.received_at,
                   (SELECT COUNT(*) FROM correspondence_links cl WHERE cl.gmail_id = g.id) AS link_count
              FROM gmail_messages g
             WHERE g.relevance_status NOT IN ('noise')
               AND (
                 g.relevance_status IN ('unlinked','client_only','matter_linked')
                 OR g.client_code IS NULL
                 OR (cardinality(COALESCE(g.matter_codes, '{}'::text[])) = 0
                     AND g.relevance_status NOT IN ('goal_linked','assessed'))
               )
             ORDER BY COALESCE(g.received_at, g.sent_at) DESC NULLS LAST
        """)

        cur.execute("""
            DELETE FROM client_history h
             WHERE h.source_table = 'gmail_messages'
               AND NOT EXISTS (
                 SELECT 1 FROM gmail_messages g
                  WHERE g.id::text = h.source_id
               )
        """)
        orphan_history = cur.rowcount

        cur.execute("""
            INSERT INTO deploy_log (deploy_id, summary) VALUES (
              'deploy_368',
              'KB pollution eradication: purge_email_noise archives promos/system mail '
              'out of gmail_messages; scrub spine/links; tighten triage view; '
              'is_kb_pollution_email gate blocks mis-tagged promos at ingest+spine.'
            )
            ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
        """)

        cur.execute("SELECT COUNT(*) AS n FROM gmail_messages")
        active = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM v_correspondence_triage")
        triage = cur.fetchone()["n"]
        cur.execute("""
            SELECT COUNT(*) AS n FROM client_history
             WHERE source_table = 'gmail_messages'
        """)
        spine_gmail = cur.fetchone()["n"]

    subprocess.run(
        [sys.executable, os.path.join(root, "client_history_scan.py")],
        check=True,
        timeout=180,
    )

    print(
        f"✓ deploy_368: active_gmail={active} triage={triage} "
        f"spine_gmail={spine_gmail} orphan_history_purged={orphan_history}"
    )


if __name__ == "__main__":
    main()