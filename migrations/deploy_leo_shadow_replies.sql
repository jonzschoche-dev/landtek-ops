-- leo_service shadow ledger — the headless Leo brain runs the full spine but SENDS NOTHING;
-- it records the candidate reply, the answer-gate verdict, and what it WOULD send. Mirrors the
-- outward_guard shadow-log / comms_artifacts ledger pattern. This is the T2 proof surface.
-- Idempotent. Rollback: DROP TABLE leo_shadow_replies;

CREATE TABLE IF NOT EXISTS leo_shadow_replies (
  id                bigserial PRIMARY KEY,
  inbound_msg_id    bigint REFERENCES channel_messages(id) ON DELETE SET NULL,
  channel           text,
  channel_user_id   text,
  client_code       text,                 -- resolved via A25; NULL when action='held'
  candidate_internal text,                -- the gated internal form (may carry doc:N grounding handles)
  verdict           text,                 -- pass | fail (from leo_answer_gate.gate)
  fails             jsonb,                -- the gate's fail reasons
  warns_n           integer,
  remediated        boolean DEFAULT false,-- true when a fail was rewritten grounded-only
  would_send_human  text,                 -- the A32 human-form projection that WOULD be sent (never sent here)
  guard_class       text,                 -- outward_guard classification (internal|outward|...)
  model             text,                 -- local Ollama model used ($0)
  action            text NOT NULL,        -- shadow_logged | held | ollama_unreachable | error
  reason            text,
  created_at        timestamptz DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_leo_shadow_inbound ON leo_shadow_replies (inbound_msg_id)
  WHERE inbound_msg_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_leo_shadow_action ON leo_shadow_replies (action, created_at DESC);

SELECT 'leo_shadow_replies ready; rows='||count(*) FROM leo_shadow_replies;
