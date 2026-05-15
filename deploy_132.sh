#!/usr/bin/env bash
# deploy_132.sh — leo_handle_output() SQL function
# One function call handles all calendar/notes ops Leo emits in his JSON output.
# Single n8n node consumes this — collapses 4 IF/Postgres pairs into 1 node.
# Run AFTER deploy_131 (which creates calendar_events and chat_notes tables).

set -euo pipefail
DEPLOY="132"
echo "=== deploy_${DEPLOY} starting at $(date -u +%FT%TZ) ==="

cat > /tmp/deploy_132.sql <<'SQL'
-- Ensure prereqs from deploy_131 exist; bail with clear error if not.
DO $check$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                 WHERE table_name = 'calendar_events') THEN
    RAISE EXCEPTION 'calendar_events table missing — run deploy_131 first.';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                 WHERE table_name = 'chat_notes') THEN
    RAISE EXCEPTION 'chat_notes table missing — run deploy_131 first.';
  END IF;
END
$check$;

-- ──────────────────────────────────────────────────────────────────────
-- leo_handle_output(jsonb) — single entry point for Leo's calendar/notes
-- Input: Leo's JSON output object (whole thing — function picks out fields)
-- Output: JSON with new_event_id, new_note_id, upcoming, matching_notes
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
  src_msg_id     TEXT := COALESCE(payload->>'telegram_message_id',
                                   payload->>'message_id', '');
  sender_id      TEXT := COALESCE(payload->>'sender_id',
                                   payload->>'telegram_id', '');
  sender_name    TEXT := COALESCE(payload->>'sender_name', '');
BEGIN
  -- ── INSERT calendar event ─────────────────────────────────────────
  IF cal IS NOT NULL
     AND COALESCE(cal->>'title', '') <> ''
     AND COALESCE(cal->>'start_at', '') <> '' THEN

    INSERT INTO calendar_events
      (title, description, start_at, end_at, location, attendees,
       related_tct, related_case, source, source_msg_id, sender_id)
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
       NULLIF(sender_id, ''))
    RETURNING id INTO new_event_id;
  END IF;

  -- ── INSERT chat note ──────────────────────────────────────────────
  IF note IS NOT NULL
     AND COALESCE(note->>'content', '') <> '' THEN

    INSERT INTO chat_notes
      (telegram_msg_id, sender_id, sender_name, content, summary,
       topic, related_tct, related_case, importance, related_event_id)
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
       new_event_id)
    RETURNING id INTO new_note_id;
  END IF;

  -- ── SELECT upcoming events ────────────────────────────────────────
  IF cal_q IS NOT NULL
     AND COALESCE(cal_q->>'type', '') <> '' THEN

    SELECT COALESCE(jsonb_agg(row_to_json(t)::jsonb), '[]'::jsonb)
      INTO upcoming_json
    FROM (
      SELECT id, title, start_at, end_at, location,
             related_case, related_tct, time_bucket, hours_until
      FROM upcoming_events
      WHERE start_at < now() + (COALESCE((cal_q->>'window_days')::int, 30)
                                || ' days')::interval
      ORDER BY start_at
      LIMIT 20
    ) t;
  END IF;

  -- ── SELECT matching notes ─────────────────────────────────────────
  IF note_q IS NOT NULL
     AND COALESCE(note_q->>'search_term', '') <> '' THEN

    SELECT COALESCE(jsonb_agg(row_to_json(t)::jsonb), '[]'::jsonb)
      INTO notes_json
    FROM (
      SELECT id, created_at, sender_name, topic, importance,
             summary, content, related_case, related_tct
      FROM chat_notes
      WHERE archived = FALSE
        AND (content  ILIKE '%' || (note_q->>'search_term') || '%'
          OR summary  ILIKE '%' || (note_q->>'search_term') || '%')
      ORDER BY created_at DESC
      LIMIT COALESCE((note_q->>'limit')::int, 20)
    ) t;
  END IF;

  RETURN jsonb_build_object(
    'new_event_id', new_event_id,
    'new_note_id',  new_note_id,
    'upcoming',     upcoming_json,
    'matching_notes', notes_json,
    'handled_at',   now()
  );
END
$body$;

GRANT EXECUTE ON FUNCTION leo_handle_output(jsonb) TO n8n;

-- ──────────────────────────────────────────────────────────────────────
-- Smoke tests
-- ──────────────────────────────────────────────────────────────────────
\echo === smoke test 1: save a note ===
SELECT leo_handle_output('{
  "chat_note_to_save": {
    "content":     "Strategy: focus on chain-of-title verification before discovery.",
    "summary":     "chain-of-title is the spine of the case",
    "topic":       "legal_strategy",
    "importance":  5,
    "related_tct": "T-4497",
    "related_case":"Civil Case 26-360"
  },
  "sender_id":   "test-jonathan",
  "sender_name": "Jonathan (smoke test)"
}'::jsonb);

\echo === smoke test 2: save a calendar event ===
SELECT leo_handle_output('{
  "calendar_event_to_save": {
    "title":         "Pre-trial conference, Civil Case 26-360",
    "description":   "Naga City RTC — Branch confirmed pre-trial date",
    "start_at":      "2026-06-30T09:00:00+08:00",
    "end_at":        "2026-06-30T11:00:00+08:00",
    "location":      "Naga City RTC",
    "attendees":     ["Jonathan Zschoche","Atty. Counsel"],
    "related_tct":   "T-4497",
    "related_case":  "Civil Case 26-360"
  },
  "sender_id":   "test-jonathan",
  "sender_name": "Jonathan (smoke test)"
}'::jsonb);

\echo === smoke test 3: query upcoming events ===
SELECT leo_handle_output('{
  "calendar_query": {
    "type":         "upcoming",
    "window_days":  60
  }
}'::jsonb);

\echo === smoke test 4: query notes ===
SELECT leo_handle_output('{
  "notes_query": {
    "search_term": "chain-of-title",
    "limit":       10
  }
}'::jsonb);

\echo === final state ===
SELECT 'calendar_events' AS tbl, COUNT(*) AS rows FROM calendar_events
UNION ALL
SELECT 'chat_notes',    COUNT(*) FROM chat_notes
UNION ALL
SELECT 'upcoming_events (view)', COUNT(*) FROM upcoming_events;
SQL

docker cp /tmp/deploy_132.sql n8n-postgres-1:/tmp/deploy_132.sql
docker exec n8n-postgres-1 psql -U n8n -d n8n -f /tmp/deploy_132.sql

cd /root/landtek
git add -A
git commit -m "deploy_${DEPLOY}: leo_handle_output(jsonb) — single SQL entry point for Leo's calendar/notes ops" || true

echo
echo "=== deploy_${DEPLOY} complete ==="
echo
echo "Next: one n8n node needs adding to Leo's workflow."
echo "Add a Postgres node after Parse Agent1 named 'Handle Calendar/Notes'."
echo "Operation: Execute query."
echo "Query:"
echo "  SELECT leo_handle_output(\$1::jsonb) AS leo_handle_result;"
echo "Parameter \$1: the JSON string from Parse Agent1 output."
echo "Wire its output back into the reply-building flow so upcoming_events"
echo "and matching_notes can be injected into the Telegram reply."
