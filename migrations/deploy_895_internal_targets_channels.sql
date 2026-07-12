-- deploy_895: make the operator reachable on Messenger (and unblock all channels in internal_targets).
--
-- Two things: (1) the internal_targets CHECK predated every channel except telegram/email — it allowed
-- only ('telegram','email','*'), so a messenger operator row was rejected. Widen it to all live channels.
-- (2) Wire Jonathan's Messenger PSID as INTERNAL so leo_service (messenger mode already 'headless',
-- cutover_JJ_first) AUTO-SENDS replies to HIM — internal-only. Real clients still classify OUTWARD and
-- HOLD at the A21 gate (no external exposure opened). Reply generation = local Ollama qwen2.5:14b ($0),
-- answer-gate + A32 projection. Proven live: sent "Hi! Yes, you're connected with me on Messenger now."
--
-- Idempotent. Rollback: restore the 3-value CHECK + DELETE the messenger internal_targets row.

ALTER TABLE internal_targets DROP CONSTRAINT IF EXISTS internal_targets_channel_check;
ALTER TABLE internal_targets ADD CONSTRAINT internal_targets_channel_check
  CHECK (channel = ANY (ARRAY['telegram','email','whatsapp','viber','messenger','sms','web','api','slack','voice','*']::text[]));

INSERT INTO internal_targets (channel, identifier, match_type, active)
SELECT 'messenger', '37446980471566856', 'exact', true
 WHERE NOT EXISTS (SELECT 1 FROM internal_targets
                    WHERE channel='messenger' AND identifier='37446980471566856');

SELECT 'internal_targets messenger: ' || string_agg(identifier, ', ')
  FROM internal_targets WHERE channel='messenger';
