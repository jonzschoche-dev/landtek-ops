-- deploy_619 — agent_audit: the unified decision log for the resident agents (the blueprint's central
-- table). Every agent that surfaces something for the operator logs it here: who (agent_name) / what
-- (event_type + summary) / when / grounding (cite) / confidence / severity / operator_action. This is
-- the agent→Leo glue substrate — agents propose into this log, the operator disposes, the digest reads
-- it, and (when LANDTEK_AGENT_ALERTS_LIVE=1) HIGH rows fire an immediate S14-gated Telegram.
CREATE TABLE IF NOT EXISTS agent_audit (
    id              bigserial PRIMARY KEY,
    agent_name      text NOT NULL,
    matter_code     text,
    event_type      text NOT NULL,                    -- new_filing | deadline | execution | narrative | ...
    severity        text NOT NULL DEFAULT 'medium'
                      CHECK (severity IN ('high','medium','low')),
    summary         text NOT NULL,                    -- the operator-facing one-liner
    grounding       text,                             -- cite(s) / basis
    confidence      real,
    dedup_key       text,                             -- idempotency: one row per logical event/state
    operator_action text,                             -- approved | rejected | modified | NULL=pending
    created_at      timestamptz NOT NULL DEFAULT now(),
    delivered_at    timestamptz,                      -- when an immediate alert was sent
    ack_at          timestamptz                       -- when the operator acknowledged
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_audit_dedup ON agent_audit(dedup_key) WHERE dedup_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_audit_created  ON agent_audit(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_audit_severity ON agent_audit(severity, created_at DESC);
