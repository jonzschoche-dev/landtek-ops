-- Per-channel cutover switch (the rollback flag) + link the shadow ledger to its approval order.
-- leo_service SENDS only on a channel whose mode='headless'; on 'n8n' it stays shadow (logs, no send).
-- Default EVERY channel to 'n8n' so deploying the send path changes NOTHING for live users until a
-- channel is explicitly flipped. Telegram is retired LAST (kept 'n8n').
-- Idempotent. Rollback: UPDATE leo_channel_mode SET mode='n8n';  (or DROP TABLE leo_channel_mode;)

CREATE TABLE IF NOT EXISTS leo_channel_mode (
  channel     text PRIMARY KEY,
  mode        text NOT NULL DEFAULT 'n8n' CHECK (mode IN ('n8n','headless')),
  updated_at  timestamptz DEFAULT now(),
  updated_by  text
);

-- seed every known live/armed channel to the SAFE default (n8n = shadow, no headless send)
INSERT INTO leo_channel_mode (channel, mode)
SELECT name, 'n8n' FROM channels
ON CONFLICT (channel) DO NOTHING;

-- link a held reply to the outward_action order that gates its send
ALTER TABLE leo_shadow_replies ADD COLUMN IF NOT EXISTS order_id bigint;

SELECT channel, mode FROM leo_channel_mode ORDER BY channel;
