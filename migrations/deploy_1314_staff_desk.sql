-- deploy_1314: staff desk (field officer on Messenger) + one-at-a-time operator approvals.
-- Product interview 2026-11-02/03 (case_work/PRODUCT_INTERVIEW_2026-11/INTERVIEW_LOG.md):
--   first daily user = Kristyle on Messenger; Jonathan approves on Messenger too;
--   EARNED autonomy = every yes/no is recorded per action pattern; a pattern runs alone only after
--   Jonathan promotes it on its record (promotion is his decision, never automatic).
-- Idempotent. The switch is staff_desk_members.active (seeded FALSE: nothing reaches Kristyle until go).

CREATE TABLE IF NOT EXISTS staff_desk_members (
    channel          text        NOT NULL,
    channel_user_id  text        NOT NULL,
    name             text        NOT NULL,
    assignee_key     text        NOT NULL,              -- matches drip_service_task.assignee
    active           boolean     NOT NULL DEFAULT false, -- THE SWITCH (Jonathan's go)
    voice            jsonb       NOT NULL DEFAULT '{}'::jsonb,  -- how they asked to be talked to, in their words
    state            jsonb       NOT NULL DEFAULT '{}'::jsonb,  -- conversation state (awaiting_voice, pending media)
    last_brief_on    date,                               -- Manila date of the last morning task brief
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (channel, channel_user_id)
);

CREATE TABLE IF NOT EXISTS approval_asks (
    id           bigserial   PRIMARY KEY,
    kind         text        NOT NULL CHECK (kind IN ('service_proof', 'task_assign')),
    ref_id       bigint      NOT NULL,                  -- drip_service_task.id (service_proof) / drip_instrument.id (task_assign)
    pattern_key  text        NOT NULL,                  -- e.g. 'task_assign:hand' / 'service_proof:hand' (the autonomy unit)
    prompt       text        NOT NULL,                  -- exactly what Jonathan was shown
    payload      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    state        text        NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'asked', 'yes', 'no', 'withdrawn')),
    asked_via    text,
    asked_at     timestamptz,
    decided_at   timestamptz,
    decided_by   text,
    decision_text text,                                 -- his reply, verbatim
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_approval_asks_open ON approval_asks (kind, ref_id) WHERE state IN ('queued', 'asked');
CREATE UNIQUE INDEX IF NOT EXISTS uq_approval_asks_one_asked ON approval_asks ((true)) WHERE state = 'asked';

-- The earned-autonomy record: per action pattern, how Jonathan has decided. Read-only evidence for HIS promotion call.
CREATE OR REPLACE VIEW v_autonomy_record AS
SELECT pattern_key,
       count(*) FILTER (WHERE state IN ('yes', 'no'))                         AS decided,
       count(*) FILTER (WHERE state = 'yes')                                  AS yes,
       count(*) FILTER (WHERE state = 'no')                                   AS no,
       count(*) FILTER (WHERE state = 'yes' AND decided_at > coalesce(
           (SELECT max(b.decided_at) FROM approval_asks b WHERE b.pattern_key = a.pattern_key AND b.state = 'no'),
           '-infinity'))                                                      AS clean_streak,
       max(decided_at)                                                        AS last_decided
  FROM approval_asks a
 GROUP BY pattern_key;

-- Kristyle (channel_users #80, approved filing_assistant 2026-07-16). Seeded INACTIVE.
INSERT INTO staff_desk_members (channel, channel_user_id, name, assignee_key, active)
VALUES ('messenger', '27492707613755423', 'Kristyle', 'kristyle', false)
ON CONFLICT (channel, channel_user_id) DO NOTHING;
