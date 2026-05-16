#!/usr/bin/env python3
"""deploy_124 — Telegram inquiry queue.

Per [[feedback_telegram_inquiry_queue]]: at most ONE open inquiry at a time.
The next queued inquiry waits until the active one is answered/skipped/expired.
A partial unique index on (status) WHERE status='active' enforces the rule structurally.
"""
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SQL = """
CREATE TABLE IF NOT EXISTS tg_inquiry_queue (
  id              bigserial PRIMARY KEY,
  kind            text NOT NULL CHECK (kind IN ('intake','brief','clarification','escalation','gap_alert','status')),
  priority        integer NOT NULL DEFAULT 30,  -- 0=P0 jump, 10=P1, 20=P2, 30=P3, 40=P4
  source_table    text,
  source_id       integer,
  matter_code     text,
  composed_html   text NOT NULL,
  composed_at     timestamptz NOT NULL DEFAULT now(),
  sent_at         timestamptz,
  sent_message_id bigint,
  status          text NOT NULL DEFAULT 'queued'
                  CHECK (status IN ('queued','active','answered','skipped','superseded','expired')),
  response_text   text,
  responded_at    timestamptz,
  expires_at      timestamptz DEFAULT now() + INTERVAL '48 hours',
  notes           text
);

-- Structural enforcement: at most one row globally at status='active'.
CREATE UNIQUE INDEX IF NOT EXISTS one_active_inquiry ON tg_inquiry_queue (status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_inquiry_queue_status_priority ON tg_inquiry_queue (status, priority, composed_at);
CREATE INDEX IF NOT EXISTS idx_inquiry_queue_matter ON tg_inquiry_queue (matter_code, status);
CREATE INDEX IF NOT EXISTS idx_inquiry_queue_source ON tg_inquiry_queue (source_table, source_id);

-- For incoming Telegram updates we track last processed update_id
CREATE TABLE IF NOT EXISTS tg_update_cursor (
  id integer PRIMARY KEY DEFAULT 1,
  last_update_id bigint DEFAULT 0,
  updated_at timestamptz DEFAULT now()
);
INSERT INTO tg_update_cursor (id, last_update_id) VALUES (1, 0)
ON CONFLICT (id) DO NOTHING;
"""

if __name__ == "__main__":
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SQL)
    cur.execute("SELECT COUNT(*) FROM tg_inquiry_queue")
    n = cur.fetchone()[0]
    print(f"deploy_124: tg_inquiry_queue + tg_update_cursor ready ({n} rows in queue)")
    cur.close(); conn.close()
