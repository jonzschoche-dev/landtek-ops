#!/usr/bin/env python3
"""deploy_134 — client_history table.

Per Jonathan 2026-05-17: "our system should be able to output every fact for
each client, every sale, transaction, correspondence should be in a client
history output constantly added onto for each scan. Each input should be
line by line carry all pertinent information about the event whether it was
a letter received or sent out."

Append-only ledger:
  • One row per event (doc filed, email sent/received, tx paid, title
    annotation, deadline created/completed, intake fired, etc.)
  • Unique on (source_table, source_id) so re-scans skip existing rows.
  • Carries enough fields to fully describe the event in one line.
"""
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SQL = """
CREATE TABLE IF NOT EXISTS client_history (
  id              bigserial PRIMARY KEY,
  client_code     text NOT NULL,
  case_file       text,
  matter_code     text,
  event_date      date,
  event_datetime  timestamptz,
  event_kind      text NOT NULL,
  source_table    text NOT NULL,
  source_id       text NOT NULL,
  who_from        text,
  who_to          text,
  what_summary    text NOT NULL,
  citation_ref    text,
  attachments     text,
  provenance      text DEFAULT 'inferred_strong',
  ingested_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_table, source_id)
);

CREATE INDEX IF NOT EXISTS idx_chist_client_date ON client_history(client_code, event_date DESC);
CREATE INDEX IF NOT EXISTS idx_chist_kind ON client_history(event_kind);
CREATE INDEX IF NOT EXISTS idx_chist_matter ON client_history(matter_code) WHERE matter_code IS NOT NULL;
"""

if __name__ == "__main__":
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SQL)
    cur.execute("SELECT COUNT(*) FROM client_history")
    print(f"deploy_134: client_history table ready ({cur.fetchone()[0]} rows)")
    cur.close(); conn.close()
