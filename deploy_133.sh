#!/usr/bin/env bash
# deploy_133.sh — per-client journaling: client linkage + journal view + auto-resolution
# Run AFTER deploy_131 (tables) and deploy_132 (leo_handle_output function).

set -euo pipefail
DEPLOY="133"
echo "=== deploy_${DEPLOY} starting at $(date -u +%FT%TZ) ==="

cat > /tmp/deploy_133.sql <<'SQL'
-- ──────────────────────────────────────────────────────────────────────
-- 1. Identify the clients table (may be named differently in different installs)
--    Probe: look for a table that holds telegram_id + name + case_file.
-- ──────────────────────────────────────────────────────────────────────
DO $probe$
DECLARE
  found_table TEXT;
BEGIN
  SELECT table_name INTO found_table
  FROM information_schema.columns
  WHERE column_name = 'telegram_id'
    AND table_schema = 'public'
    AND table_name IN (
      SELECT table_name FROM information_schema.columns
      WHERE column_name = 'case_file' AND table_schema = 'public'
    )
  LIMIT 1;
  IF found_table IS NULL THEN
    RAISE EXCEPTION 'Could not find a clients-like table with telegram_id + case_file. Adjust deploy_133 manually.';
  END IF;
  RAISE NOTICE 'Detected clients table: %', found_table;
END
$probe$;

-- Use a hard-coded `clients` table name for the rest of this script.
-- If the actual table name differs, edit below.

-- ──────────────────────────────────────────────────────────────────────
-- 2. Add client_id FK to calendar_events and chat_notes (idempotent)
-- ──────────────────────────────────────────────────────────────────────
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name='calendar_events' AND column_name='client_id') THEN
    ALTER TABLE calendar_events ADD COLUMN client_id INT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name='chat_notes' AND column_name='client_id') THEN
    ALTER TABLE chat_notes ADD COLUMN client_id INT;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_calendar_client ON calendar_events(client_id);
CREATE INDEX IF NOT EXISTS idx_notes_client    ON chat_notes(client_id);

-- ──────────────────────────────────────────────────────────────────────
-- 3. resolve_client_by_telegram_id(text) — find a client row by Telegram ID
-- ──────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION resolve_client_by_telegram_id(tg_id TEXT)
RETURNS INT
LANGUAGE plpgsql
AS $body$
DECLARE
  cid INT;
BEGIN
  IF tg_id IS NULL OR tg_id = '' THEN RETURN NULL; END IF;
  SELECT id INTO cid FROM clients WHERE telegram_id = tg_id LIMIT 1;
  RETURN cid;
END
$body$;

-- ──────────────────────────────────────────────────────────────────────
-- 4. resolve_client_by_name(text) — fuzzy match by name (uses pg_trgm)
-- ──────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION resolve_client_by_name(client_name TEXT)
RETURNS INT
LANGUAGE plpgsql
AS $body$
DECLARE
  cid INT;
BEGIN
  IF client_name IS NULL OR client_name = '' THEN RETURN NULL; END IF;
  SELECT id INTO cid
  FROM clients
  WHERE name ILIKE '%' || client_name || '%'
     OR similarity(name, client_name) > 0.4
  ORDER BY similarity(name, client_name) DESC
  LIMIT 1;
  RETURN cid;
END
$body$;

-- ──────────────────────────────────────────────────────────────────────
-- 5. Upgrade leo_handle_output to auto-fill client_id and accept client_name
-- ──────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION leo_handle_output(payload jsonb)
RETURNS jsonb
LANGUAGE plpgsql
AS $body$
DECLARE
  cal      jsonb := payload->'calendar_event_to_save';
  note     jsonb := payload->'chat_note_to_save';
  cal_q    jsonb := payload->'calendar_query';
  note_q   jsonb := payload->'notes_query';
  new_event_id   INT;
  new_note_id    INT;
  upcoming_json  jsonb := '[]'::jsonb;
  notes_json     jsonb := '[]'::jsonb;
  journal_json   jsonb := '[]'::jsonb;
  src_msg_id     TEXT := COALESCE(payload->>'telegram_message_id',
                                   payload->>'message_id', '');
  sender_id      TEXT := COALESCE(payload->>'sender_id',
                                   payload->>'telegram_id', '');
  sender_name    TEXT := COALESCE(payload->>'sender_name', '');
  cal_client_id  INT;
  note_client_id INT;
  query_client_id INT;
BEGIN
  -- ── INSERT calendar event ─────────────────────────────────────────
  IF cal IS NOT NULL
     AND COALESCE(cal->>'title', '') <> ''
     AND COALESCE(cal->>'start_at', '') <> '' THEN

    cal_client_id := COALESCE(
      resolve_client_by_telegram_id(sender_id),
      resolve_client_by_name(cal->>'client_name')
    );

    INSERT INTO calendar_events
      (title, description, start_at, end_at, location, attendees,
       related_tct, related_case, source, source_msg_id, sender_id, client_id)
    VALUES
      (cal->>'title',
       NULLIF(cal->>'description', ''),
       (cal->>'start_at')::timestamptz,
       NULLIF(cal->>'end_at', '')::timestamptz,
       NULLIF(cal->>'location', ''),
       CASE
         WHEN cal->'attendees' IS NULL OR jsonb_typeof(cal->'attendees') <> 'array' THEN NULL
         ELSE ARRAY(SELECT jsonb_array_elements_text(cal->'attendees'))
       END,
       NULLIF(cal->>'related_tct', ''),
       NULLIF(cal->>'related_case', ''),
       'telegram',
       NULLIF(src_msg_id, ''),
       NULLIF(sender_id, ''),
       cal_client_id)
    RETURNING id INTO new_event_id;
  END IF;

  -- ── INSERT chat note ──────────────────────────────────────────────
  IF note IS NOT NULL
     AND COALESCE(note->>'content', '') <> '' THEN

    note_client_id := COALESCE(
      resolve_client_by_telegram_id(sender_id),
      resolve_client_by_name(note->>'client_name')
    );

    INSERT INTO chat_notes
      (telegram_msg_id, sender_id, sender_name, content, summary,
       topic, related_tct, related_case, importance, related_event_id, client_id)
    VALUES
      (NULLIF(src_msg_id, ''),
       NULLIF(sender_id, ''),
       NULLIF(sender_name, ''),
       note->>'content',
       NULLIF(note->>'summary', ''),
       COALESCE(NULLIF(note->>'topic', ''), 'misc'),
       NULLIF(note->>'related_tct', ''),
       NULLIF(note->>'related_case', ''),
       COALESCE((note->>'importance')::int, 3),
       new_event_id,
       note_client_id)
    RETURNING id INTO new_note_id;
  END IF;

  -- ── SELECT upcoming events (optionally filtered by client) ────────
  IF cal_q IS NOT NULL
     AND COALESCE(cal_q->>'type', '') <> '' THEN
    query_client_id := COALESCE(
      resolve_client_by_telegram_id(sender_id),
      resolve_client_by_name(cal_q->>'client_name')
    );

    SELECT COALESCE(jsonb_agg(row_to_json(t)::jsonb), '[]'::jsonb)
      INTO upcoming_json
    FROM (
      SELECT ce.id, ce.title, ce.start_at, ce.end_at, ce.location,
             ce.related_case, ce.related_tct,
             c.name AS client_name
      FROM calendar_events ce
      LEFT JOIN clients c ON ce.client_id = c.id
      WHERE ce.status = 'scheduled'
        AND ce.start_at > now()
        AND ce.start_at < now() + (COALESCE((cal_q->>'window_days')::int, 30)
                                    || ' days')::interval
        AND (query_client_id IS NULL OR ce.client_id = query_client_id)
      ORDER BY ce.start_at
      LIMIT 20
    ) t;
  END IF;

  -- ── SELECT matching notes ─────────────────────────────────────────
  IF note_q IS NOT NULL
     AND COALESCE(note_q->>'search_term', '') <> '' THEN

    SELECT COALESCE(jsonb_agg(row_to_json(t)::jsonb), '[]'::jsonb)
      INTO notes_json
    FROM (
      SELECT n.id, n.created_at, n.sender_name, n.topic, n.importance,
             n.summary, n.content, n.related_case, n.related_tct,
             c.name AS client_name
      FROM chat_notes n
      LEFT JOIN clients c ON n.client_id = c.id
      WHERE n.archived = FALSE
        AND (n.content ILIKE '%' || (note_q->>'search_term') || '%'
          OR n.summary ILIKE '%' || (note_q->>'search_term') || '%')
      ORDER BY n.created_at DESC
      LIMIT COALESCE((note_q->>'limit')::int, 20)
    ) t;
  END IF;

  -- ── client_journal: chronological view if client_journal_query present ──
  IF payload ? 'client_journal_query' THEN
    DECLARE jq jsonb := payload->'client_journal_query';
            jq_client_id INT;
    BEGIN
      jq_client_id := COALESCE(
        (jq->>'client_id')::int,
        resolve_client_by_telegram_id(jq->>'telegram_id'),
        resolve_client_by_name(jq->>'client_name')
      );
      IF jq_client_id IS NOT NULL THEN
        SELECT COALESCE(jsonb_agg(row_to_json(t)::jsonb), '[]'::jsonb)
          INTO journal_json
        FROM (
          SELECT * FROM client_journal
          WHERE client_id = jq_client_id
          ORDER BY ts DESC
          LIMIT COALESCE((jq->>'limit')::int, 50)
        ) t;
      END IF;
    END;
  END IF;

  RETURN jsonb_build_object(
    'new_event_id',   new_event_id,
    'new_note_id',    new_note_id,
    'upcoming',       upcoming_json,
    'matching_notes', notes_json,
    'journal',        journal_json,
    'handled_at',     now()
  );
END
$body$;

GRANT EXECUTE ON FUNCTION leo_handle_output(jsonb)              TO n8n;
GRANT EXECUTE ON FUNCTION resolve_client_by_telegram_id(text)   TO n8n;
GRANT EXECUTE ON FUNCTION resolve_client_by_name(text)          TO n8n;

-- ──────────────────────────────────────────────────────────────────────
-- 6. client_journal view — chronological mix of events + notes per client
-- ──────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW client_journal AS
SELECT
  ce.client_id,
  ce.start_at AS ts,
  'event'::TEXT AS kind,
  ce.id AS source_id,
  ce.title AS title,
  ce.description AS body,
  ce.related_tct,
  ce.related_case,
  ce.location,
  NULL::INT AS importance,
  NULL::TEXT AS topic,
  ce.status
FROM calendar_events ce
WHERE ce.client_id IS NOT NULL

UNION ALL

SELECT
  cn.client_id,
  cn.created_at AS ts,
  'note'::TEXT AS kind,
  cn.id AS source_id,
  COALESCE(cn.summary, LEFT(cn.content, 80)) AS title,
  cn.content AS body,
  cn.related_tct,
  cn.related_case,
  NULL AS location,
  cn.importance,
  cn.topic,
  CASE WHEN cn.archived THEN 'archived' ELSE 'active' END AS status
FROM chat_notes cn
WHERE cn.client_id IS NOT NULL
  AND cn.archived = FALSE;

-- Backfill: link existing telegram-sourced calendar/notes rows to clients
UPDATE calendar_events ce
SET client_id = c.id
FROM clients c
WHERE ce.sender_id IS NOT NULL
  AND ce.client_id IS NULL
  AND c.telegram_id = ce.sender_id;

UPDATE chat_notes cn
SET client_id = c.id
FROM clients c
WHERE cn.sender_id IS NOT NULL
  AND cn.client_id IS NULL
  AND c.telegram_id = cn.sender_id;

\echo === client_journal rows ===
SELECT COUNT(*) AS rows FROM client_journal;

\echo === smoke: journal for any client_id present ===
SELECT * FROM client_journal LIMIT 5;

\echo === clients lookup test ===
SELECT id, name, telegram_id, case_file FROM clients LIMIT 5;
SQL

docker cp /tmp/deploy_133.sql n8n-postgres-1:/tmp/deploy_133.sql
docker exec n8n-postgres-1 psql -U n8n -d n8n -f /tmp/deploy_133.sql

cd /root/landtek
git add -A
git commit -m "deploy_${DEPLOY}: per-client journaling — client_id FKs + client_journal view + resolve_client_by_* + leo_handle_output v2 with client linkage" || true

echo
echo "=== deploy_${DEPLOY} complete ==="
echo
echo "Leo's calendar/notes are now per-client. Next:"
echo "  1. Update Leo's prompt to capture client_name in calendar_event_to_save / chat_note_to_save (Cowork Chrome session)."
echo "  2. Add the 'Handle Calendar/Notes' Postgres node in Leo's workflow (one node) wired to call:"
echo "       SELECT leo_handle_output(\$1::jsonb) AS leo_handle_result;"
echo "  3. Re-publish Leo."
echo "  4. Smoke test via Telegram."
