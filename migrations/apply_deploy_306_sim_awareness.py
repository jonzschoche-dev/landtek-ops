#!/usr/bin/env python3
"""apply_deploy_306_sim_awareness.py — emergency memory-corruption fix.

Incident: between simulator start (deploy_298c, ~00:08 UTC 2026-06-04) and
deploy_306 patch landing (~03:05 UTC), Leo's AI Agent wrote 287 chat_notes
attributing sim-simulator activity to real clients (Allan, Kristyle). Three
distinct corruption modes were observed:

  Mode A — sim sender_id with client-identifying content (recoverable, just
           archive).
  Mode B — identity substitution: Leo replaced the sim sender_id (999000xxx)
           with the real telegram_id of someone the prompt mentioned by name.
           Example: sender_id='8352343888' (Allan's REAL id) on a note about
           a sim sender's prompt mentioning Allan. These were the most
           dangerous because future context queries against Allan's real id
           would surface them as if they were Allan's own activity.
  Mode C — Leo fabricated incident counts and note IDs ("for the NINTH
           recorded time", "see notes 289, 300, 330, 371") that did not
           exist in chat_notes.

Recovery: 287 polluted chat_notes were marked archived=true (kept for
forensics; never returned by Context Builder queries which filter
archived=false).

Prevention: AI Agent systemMessage extended with three hard rules:
  S1 - Sim recognition: sender_id starting with '999000' → reply only, no
       write tools (chat_note, calendar_event, landscape_update, etc.) fire.
  S2 - Identity integrity: tool-call sender_id MUST equal
       $('Telegram Trigger').first().json.message.from.id — never
       substitute with a name-mentioned third party's real id.
  S3 - No fabricated history: never write "for the Nth recorded time" or
       "see notes …" unless backed by a chat_notes query against the EXACT
       sender_id with confirmed matching rows.

Snapshot taken before patch: see leo_workflow_snapshots row #1
(reason='pre-deploy_306 emergency sim-awareness patch').
"""
from __future__ import annotations
import os
import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deploy_log (
            deploy_id text PRIMARY KEY,
            summary   text NOT NULL,
            applied_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    cur.execute("""
        INSERT INTO deploy_log (deploy_id, summary)
        VALUES (
            'deploy_306',
            'EMERGENCY memory-corruption fix: 287 sim-induced chat_notes archived (3h pollution from simulator start); AI Agent systemMessage extended with sim recognition (S1), identity integrity (S2), no-fabricated-history (S3) rules. Stops Leo from substituting a name-mentioned clients real telegram_id into sim-exec tool calls, and from inventing incident counts.'
        ) ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
    """)
    cur.execute("SELECT deploy_id, applied_at FROM deploy_log WHERE deploy_id='deploy_306'")
    r = cur.fetchone()
    print(f"deploy_log: {r[0]} applied_at {r[1]}")

    # Sanity check: patch present, snapshot exists.
    cur.execute("SELECT nodes::text LIKE '%deploy_306%' FROM workflow_entity WHERE id='vSDQv1vfn6627bnA'")
    in_workflow = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM leo_workflow_snapshots WHERE reason LIKE '%deploy_306%'")
    snaps = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chat_notes WHERE archived=true AND created_at > '2026-06-04 00:00 UTC' AND (sender_id LIKE '999000%' OR sender_name LIKE 'Sim%')")
    archived = cur.fetchone()[0]
    print(f"patch in workflow: {in_workflow}")
    print(f"pre-patch snapshots: {snaps}")
    print(f"sim chat_notes archived: {archived}")


if __name__ == "__main__":
    main()
