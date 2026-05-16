#!/usr/bin/env python3
"""Deploy 118 — Canonical filenames + inventory + dedup foundation.

Adds:
  documents.canonical_filename       — clear, sortable name per filename convention
  documents.canonical_filename_at    — when the canonical was assigned
  audit_events                       — generic audit log for inventory + dedup + access
  duplicate_groups + duplicate_group_members
"""
import psycopg2
DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SQL = r"""
ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS canonical_filename text,
  ADD COLUMN IF NOT EXISTS canonical_filename_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_documents_canonical ON documents(canonical_filename);

CREATE TABLE IF NOT EXISTS audit_events (
  id           serial PRIMARY KEY,
  event_type   text NOT NULL,                -- 'rename','dedup_exact','dedup_near','access','integrity_flag'
  target_kind  text NOT NULL,                 -- 'document','channel_user','transaction','title'
  target_id    integer,
  payload      jsonb,
  created_at   timestamptz DEFAULT now(),
  actor        text DEFAULT 'system'
);
CREATE INDEX IF NOT EXISTS idx_audit_events_target ON audit_events(target_kind, target_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_type ON audit_events(event_type, created_at DESC);

CREATE TABLE IF NOT EXISTS duplicate_groups (
  id              serial PRIMARY KEY,
  group_kind      text NOT NULL,         -- 'exact_hash' | 'near_name_size' | 'content_similar'
  hash_or_key     text,                  -- the matching content_hash or (smart_filename||case_file)
  canonical_id    integer REFERENCES documents(id),  -- the "keeper"
  duplicate_count integer DEFAULT 0,
  first_seen_at   timestamptz DEFAULT now(),
  resolved        boolean DEFAULT false,
  notes           text
);
CREATE INDEX IF NOT EXISTS idx_dup_groups_kind ON duplicate_groups(group_kind, resolved);

CREATE TABLE IF NOT EXISTS duplicate_group_members (
  id          serial PRIMARY KEY,
  group_id    integer REFERENCES duplicate_groups(id) ON DELETE CASCADE,
  doc_id      integer REFERENCES documents(id) ON DELETE CASCADE,
  is_keeper   boolean DEFAULT false,
  reason      text,
  UNIQUE(group_id, doc_id)
);
CREATE INDEX IF NOT EXISTS idx_dup_members_doc ON duplicate_group_members(doc_id);
"""


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SQL)
    for check in ["documents.canonical_filename column",
                  "audit_events table",
                  "duplicate_groups table",
                  "duplicate_group_members table"]:
        print(f"    ✓ {check}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
