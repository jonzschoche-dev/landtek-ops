-- deploy: the first LIVING ORGAN — relationship_profile. Per verified comms line, an evolving record of
-- "how this exact person wants to be spoken to and what they need right now." NOT a static policy: it
-- grows from every exchange (append-only signal_log preserves the arc; profile is the living summary) and
-- feeds the next generation. Minimal + alive — no rigid taxonomy that would freeze the intelligence.
-- Idempotent. Rollback: DROP TABLE relationship_profile;

CREATE TABLE IF NOT EXISTS relationship_profile (
  id              bigserial PRIMARY KEY,
  channel         text NOT NULL,
  channel_user_id text NOT NULL,
  client_code     text,
  entity_id       integer,
  profile         jsonb NOT NULL DEFAULT '{}'::jsonb,    -- living summary (evolving; dominant lang, themes, tone…)
  signal_log      jsonb NOT NULL DEFAULT '[]'::jsonb,    -- append-only arc of per-exchange signals (last 50)
  exchanges       integer NOT NULL DEFAULT 0,
  last_inbound_id bigint,                                 -- idempotency guard (don't double-count a message)
  created_at      timestamptz DEFAULT now(),
  updated_at      timestamptz DEFAULT now(),
  UNIQUE (channel, channel_user_id)
);
CREATE INDEX IF NOT EXISTS idx_relprofile_client ON relationship_profile (client_code);

SELECT 'relationship_profile ready' AS status;
