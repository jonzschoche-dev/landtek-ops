#!/usr/bin/env bash
# deploy_131.sh — Leo calendar + notes backbone
# Creates calendar_events, chat_notes, related views.
# Must be run BEFORE Leo is re-published with the new prompt.

set -euo pipefail
DEPLOY="131"
echo "=== deploy_${DEPLOY} starting at $(date -u +%FT%TZ) ==="

cat > /tmp/deploy_131.sql <<'SQL'
-- ──────────────────────────────────────────────────────────────────────
-- calendar_events: Leo's calendar, written by Leo from Telegram conversations
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS calendar_events (
  id              SERIAL PRIMARY KEY,
  title           TEXT NOT NULL,
  description     TEXT,
  start_at        TIMESTAMPTZ NOT NULL,
  end_at          TIMESTAMPTZ,
  location        TEXT,
  attendees       TEXT[],           -- list of names / contacts
  related_tct     TEXT,             -- e.g. 'T-4497'
  related_case    TEXT,             -- e.g. 'Civil Case 26-360'
  source          TEXT DEFAULT 'telegram',  -- telegram | manual | email
  source_msg_id   TEXT,             -- telegram_message_id, gmail_message_id
  sender_id       TEXT,             -- who triggered the event creation
  status          TEXT DEFAULT 'scheduled'
                  CHECK (status IN ('scheduled','completed','cancelled','rescheduled')),
  remind_before   INTERVAL DEFAULT INTERVAL '1 day',
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_calendar_start  ON calendar_events(start_at);
CREATE INDEX IF NOT EXISTS idx_calendar_case   ON calendar_events(related_case);
CREATE INDEX IF NOT EXISTS idx_calendar_tct    ON calendar_events(related_tct);
CREATE INDEX IF NOT EXISTS idx_calendar_status ON calendar_events(status);

-- ──────────────────────────────────────────────────────────────────────
-- chat_notes: Leo's note-taking — persistent memory of chat decisions/facts
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_notes (
  id                SERIAL PRIMARY KEY,
  telegram_msg_id   TEXT,
  sender_id         TEXT,
  sender_name       TEXT,
  content           TEXT NOT NULL,
  summary           TEXT,             -- one-line gist
  topic             TEXT             -- legal_strategy | evidence | people | deadlines | communications | task | misc
                    CHECK (topic IN ('legal_strategy','evidence','people',
                                     'deadlines','communications','task','misc')),
  related_entity_id INT,              -- FK to entities table when applicable
  related_tct       TEXT,
  related_case      TEXT,
  related_event_id  INT REFERENCES calendar_events(id),
  importance        INT DEFAULT 3 CHECK (importance BETWEEN 1 AND 5),
  archived          BOOLEAN DEFAULT FALSE,
  created_at        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notes_created     ON chat_notes(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notes_topic       ON chat_notes(topic);
CREATE INDEX IF NOT EXISTS idx_notes_importance  ON chat_notes(importance DESC);
CREATE INDEX IF NOT EXISTS idx_notes_case        ON chat_notes(related_case);
CREATE INDEX IF NOT EXISTS idx_notes_tct         ON chat_notes(related_tct);
CREATE INDEX IF NOT EXISTS idx_notes_event       ON chat_notes(related_event_id);

-- text-search index for note retrieval
CREATE INDEX IF NOT EXISTS idx_notes_content_trgm ON chat_notes
  USING gin (content gin_trgm_ops);

-- ──────────────────────────────────────────────────────────────────────
-- VIEW: upcoming_events — next 30 days, sorted, formatted for Telegram reply
-- ──────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW upcoming_events AS
SELECT
  id,
  title,
  start_at,
  end_at,
  location,
  attendees,
  related_case,
  related_tct,
  status,
  remind_before,
  EXTRACT(EPOCH FROM (start_at - now())) / 3600 AS hours_until,
  CASE
    WHEN start_at < now() + INTERVAL '24 hours' THEN 'today_tomorrow'
    WHEN start_at < now() + INTERVAL '7 days'   THEN 'this_week'
    WHEN start_at < now() + INTERVAL '30 days'  THEN 'this_month'
    ELSE 'beyond'
  END AS time_bucket
FROM calendar_events
WHERE status = 'scheduled'
  AND start_at > now()
  AND start_at < now() + INTERVAL '60 days'
ORDER BY start_at;

-- ──────────────────────────────────────────────────────────────────────
-- VIEW: notes_recent — last 50 notes for quick recall
-- ──────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW notes_recent AS
SELECT id, created_at, sender_name, topic, importance, summary, content,
       related_case, related_tct, related_event_id
FROM chat_notes
WHERE archived = FALSE
ORDER BY created_at DESC
LIMIT 50;

-- ──────────────────────────────────────────────────────────────────────
-- VIEW: notes_critical — importance >= 4, unarchived
-- ──────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW notes_critical AS
SELECT id, created_at, sender_name, topic, importance, summary, content,
       related_case, related_tct
FROM chat_notes
WHERE archived = FALSE
  AND importance >= 4
ORDER BY created_at DESC;

-- ──────────────────────────────────────────────────────────────────────
-- trigger: keep calendar_events.updated_at fresh on any UPDATE
-- ──────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION touch_calendar_updated_at() RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_calendar_touch ON calendar_events;
CREATE TRIGGER trg_calendar_touch BEFORE UPDATE ON calendar_events
  FOR EACH ROW EXECUTE FUNCTION touch_calendar_updated_at();

-- Ensure pg_trgm extension is loaded (needed for the gin trgm index above)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

\echo === calendar_events ===
SELECT COUNT(*) AS rows, 'calendar_events' AS table_name FROM calendar_events;
\echo === chat_notes ===
SELECT COUNT(*) AS rows, 'chat_notes' AS table_name FROM chat_notes;
\echo === upcoming_events view rows ===
SELECT COUNT(*) AS upcoming FROM upcoming_events;

-- ──────────────────────────────────────────────────────────────────────
-- Seed: one starter event so Leo has something to show when asked
-- ──────────────────────────────────────────────────────────────────────
INSERT INTO calendar_events
  (title, description, start_at, related_tct, related_case, source, status)
VALUES
  ('Leo calendar online',
   'Calendar backbone deployed (deploy_131). Leo can now save and retrieve events.',
   now() + INTERVAL '1 minute',
   'T-4497',
   'Civil Case 26-360',
   'manual',
   'completed')
ON CONFLICT DO NOTHING;
SQL

docker cp /tmp/deploy_131.sql n8n-postgres-1:/tmp/deploy_131.sql
docker exec n8n-postgres-1 psql -U n8n -d n8n -f /tmp/deploy_131.sql

cd /root/landtek
git add -A
git commit -m "deploy_${DEPLOY}: calendar_events + chat_notes + upcoming_events + notes_recent + notes_critical" || true

echo "=== deploy_${DEPLOY} complete ==="
echo
echo "Next: Leo's system prompt needs updating in n8n UI to instruct him to use"
echo "      these tables. Run from Cowork session (Chrome MCP) — already in progress."
