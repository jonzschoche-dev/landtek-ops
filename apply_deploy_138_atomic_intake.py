#!/usr/bin/env python3
"""deploy_138 — atomic intake schema additions.

Per [[feedback_atomic_inquiry_with_followups]]: each intake-item is its own
tg_inquiry_queue row; follow-ups link via parent_id; satisfaction tracked
per atomic question.
"""
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SQL = """
ALTER TABLE tg_inquiry_queue
  ADD COLUMN IF NOT EXISTS parent_id            bigint REFERENCES tg_inquiry_queue(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS intake_response_id   integer REFERENCES stage_intake_response(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS item_index           integer,
  ADD COLUMN IF NOT EXISTS is_followup          boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS satisfaction_verdict text,
  ADD COLUMN IF NOT EXISTS satisfaction_reason  text;

CREATE INDEX IF NOT EXISTS idx_inquiry_intake ON tg_inquiry_queue(intake_response_id, item_index)
  WHERE intake_response_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_inquiry_parent ON tg_inquiry_queue(parent_id)
  WHERE parent_id IS NOT NULL;

-- stage_intake_response gets per-item completion tracking
ALTER TABLE stage_intake_response
  ADD COLUMN IF NOT EXISTS item_status jsonb DEFAULT '{}'::jsonb;
"""

if __name__ == "__main__":
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SQL)
    print("deploy_138: tg_inquiry_queue + stage_intake_response extended for atomic intake")
