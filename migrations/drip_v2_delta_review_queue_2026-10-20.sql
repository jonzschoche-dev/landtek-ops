-- APPLIED 2026-10-20 on the VPS (Jonathan: 'program constant movement'); dry-run first; drip_event logged.
-- DRAFT DELTA — CONSTANT MOVEMENT: the drip always has drafts waiting for Jonathan's comment (Jonathan, 20 Oct 2026:
-- "the drip should always be drafts for comment; program that into the system so there is constant movement").
-- Requires DRAFT_drip_v2_delta_baby_steps.sql (step_plan). Additive. Nothing here sends, stages or prints.
-- Flow:  step_plan → (fill) drip_instrument 'awaiting_comment' → Jonathan comments → 'revising' → re-lint →
--        'awaiting_comment' … → Jonathan: "make the draft" → 'ready_for_draft' → staged as an e-mail draft in the
--        thread's origin account (or printed for paper) only on that word → 'draft_staged' → his Send → 'served' path.
BEGIN;

ALTER TABLE drip_instrument
  ADD COLUMN IF NOT EXISTS step_plan_id   bigint REFERENCES step_plan(id),
  ADD COLUMN IF NOT EXISTS version        integer NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS body_md        text,            -- the exact text under review (what Jonathan reads)
  ADD COLUMN IF NOT EXISTS word_count     integer,
  ADD COLUMN IF NOT EXISTS send_account   text,            -- thread origin account, or 'paper'
  ADD COLUMN IF NOT EXISTS thread_ref     text,            -- Gmail thread/message id to reply in
  ADD COLUMN IF NOT EXISTS queued_at      timestamptz,
  ADD COLUMN IF NOT EXISTS shown_at       timestamptz;     -- last time it was put in front of Jonathan

DO $$
DECLARE c text;
BEGIN
  SELECT conname INTO c FROM pg_constraint
   WHERE conrelid = 'drip_instrument'::regclass AND contype = 'c'
     AND pg_get_constraintdef(oid) ILIKE '%status = ANY%' AND pg_get_constraintdef(oid) ILIKE '%refused_lint%';
  IF c IS NOT NULL AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = c AND pg_get_constraintdef(oid) ILIKE '%awaiting_comment%') THEN
    EXECUTE format('ALTER TABLE drip_instrument DROP CONSTRAINT %I', c);
    ALTER TABLE drip_instrument ADD CONSTRAINT drip_instrument_status_check CHECK (status IN (
      'awaiting_comment','revising','ready_for_draft','draft_staged',
      'draft','checked','corrected','approved','printed','served','superseded','refused_lint'));
  END IF;
END $$;

-- 'ready_for_draft' and 'draft_staged' need Jonathan's word on that item (same rule as approval)
DO $$ BEGIN
  ALTER TABLE drip_instrument ADD CONSTRAINT drip_ready_needs_word CHECK (
    status NOT IN ('ready_for_draft','draft_staged') OR approval_ref IS NOT NULL) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS drip_comment (
    id               bigserial PRIMARY KEY,
    instrument_id    bigint NOT NULL REFERENCES drip_instrument(id),
    on_version       integer NOT NULL,
    author           text NOT NULL DEFAULT 'jonathan',
    comment          text NOT NULL,
    resolved_in_version integer,                       -- set when a revision addresses it
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS drip_queue_config (
    key    text PRIMARY KEY,
    value  text NOT NULL,
    note   text
);
INSERT INTO drip_queue_config VALUES
 ('min_awaiting_comment','3','Always keep at least this many drafts waiting for Jonathan''s comment'),
 ('show_one_at_a_time','true','Jonathan reviews drafts one at a time (20 Oct 2026)'),
 ('max_new_per_cluster_per_week','1','Stagger: one new step per office cluster per week'),
 ('min_working_days_between_steps','15','Per office, from proven receipt')
ON CONFLICT (key) DO NOTHING;

-- What Jonathan sees next: revisions first (his own comments, answered), then the oldest waiting, in pick order
CREATE OR REPLACE VIEW v_review_queue AS
SELECT i.id, i.status, i.version, i.client_code, sp.matter_code, sp.ladder, sp.seq, sp.step_kind, sp.addressee,
       sp.goal_kind, i.word_count, i.send_account, i.thread_ref, i.file_path, i.queued_at, i.shown_at,
       (SELECT count(*) FROM drip_comment c WHERE c.instrument_id = i.id AND c.resolved_in_version IS NULL) AS open_comments
  FROM drip_instrument i
  LEFT JOIN step_plan sp ON sp.id = i.step_plan_id
 WHERE i.status IN ('awaiting_comment','revising')
 ORDER BY (i.status = 'revising') DESC, i.shown_at NULLS FIRST, i.queued_at;

COMMIT;
