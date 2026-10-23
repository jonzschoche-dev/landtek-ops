-- drip_core_2026-10-23.sql — the drip runs on five fed tables (Jonathan, 23 Oct 2026: "take ownership …
-- five-table consolidation and the single logging step"). Additive and idempotent; nothing dropped.
--   step_plan (ladders) · drip_event (log, append-only) · office_obligation (clocks) ·
--   drip_feedback (rules) · drip_ui_draft (drafts awaiting Jonathan)
-- Written to by ONE command: scripts/drip_log.py. Read by drip_board.py, drip_sweep.py, the Drip UI.

-- 1. Clocks know their ladder (the UI and board join on it).
ALTER TABLE office_obligation ADD COLUMN IF NOT EXISTS ladder text;
CREATE INDEX IF NOT EXISTS office_obligation_ladder_idx ON office_obligation (ladder);

-- 2. drip_event is append-only (trigger), so its ladder tag is exposed through a view, not backfilled.
CREATE OR REPLACE VIEW drip_event_v AS
SELECT e.*,
       coalesce(e.detail->>'ladder', e.detail->>'track') AS ladder,
       nullif(substring(coalesce(e.detail->>'at','') from '^\d{4}-\d{2}-\d{2}'), '')::date AS event_date
  FROM drip_event e;

-- 3. One row per ladder for the board/UI: latest step state + live clock.
CREATE OR REPLACE VIEW drip_ladder_status AS
SELECT l.ladder,
       (SELECT max(event_date) FROM drip_event_v v WHERE v.ladder = l.ladder AND v.kind IN ('sent','dispatched')) AS last_sent,
       (SELECT max(event_date) FROM drip_event_v v WHERE v.ladder = l.ladder AND v.kind = 'reply') AS last_reply,
       o.id AS obligation_id, o.state AS clock_state, o.served_at, o.due_at, o.service_proof_doc_id
  FROM (SELECT DISTINCT ladder FROM drip_event_v WHERE ladder IS NOT NULL
        UNION SELECT DISTINCT ladder FROM step_plan) l
  LEFT JOIN LATERAL (SELECT * FROM office_obligation ob WHERE ob.ladder = l.ladder
                      ORDER BY ob.served_at DESC NULLS LAST, ob.id DESC LIMIT 1) o ON true;
