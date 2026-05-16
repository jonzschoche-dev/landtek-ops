#!/usr/bin/env python3
"""deploy_122 — drive_duplicates persistent dedup tracking.

Adds:
  • drive_duplicates table — remembers Drive file IDs proven to be content
    duplicates of an existing doc. Lets drive_backfill skip them every cycle.
  • documents.drive_md5_checksum column — Drive's native MD5 (we get for free
    in metadata; lets us avoid downloading new files entirely if md5 matches
    an existing doc's md5).
"""
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SQL = """
CREATE TABLE IF NOT EXISTS drive_duplicates (
  drive_file_id     text PRIMARY KEY,
  canonical_doc_id  integer REFERENCES documents(id) ON DELETE SET NULL,
  drive_md5         text,
  drive_filename    text,
  detected_at       timestamptz DEFAULT now(),
  notes             text
);

CREATE INDEX IF NOT EXISTS idx_drive_dupes_doc ON drive_duplicates(canonical_doc_id);
CREATE INDEX IF NOT EXISTS idx_drive_dupes_md5 ON drive_duplicates(drive_md5);

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS drive_md5_checksum text;

CREATE INDEX IF NOT EXISTS idx_documents_drive_md5 ON documents(drive_md5_checksum);
"""

if __name__ == "__main__":
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SQL)
    cur.execute("SELECT COUNT(*) FROM drive_duplicates")
    n = cur.fetchone()[0]
    print(f"deploy_122: drive_duplicates ready ({n} rows) + documents.drive_md5_checksum column added")
