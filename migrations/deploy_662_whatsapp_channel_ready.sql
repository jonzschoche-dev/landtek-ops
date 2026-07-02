-- deploy_662: mark the WhatsApp channel READY (code wired, awaiting token) — no external exposure yet.
-- Ensures the 'whatsapp' channel row exists (the drain bridge's subquery depends on it) and records
-- the true state: adapter live, backlog drain armed via landtek-whatsapp-bridge.timer, sending gated
-- on the token. For WhatsApp the token IS the external switch, so active stays FALSE until provisioned.
--
-- Run on the VPS:
--   docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/deploy_662_whatsapp_channel_ready.sql

INSERT INTO channels (name, provider, auth_secret_ref, active, notes)
VALUES ('whatsapp', 'meta_cloud_api', 'WHATSAPP_API_TOKEN', false,
        'READY, awaiting token. Adapter /api/channel/whatsapp live (incl. Meta GET verify-challenge). Inbound sends inline once WHATSAPP_API_TOKEN + WHATSAPP_PHONE_NUMBER_ID are in .env (read live, no restart). Backlog auto-drains via landtek-whatsapp-bridge.timer. Token = the external switch; flip active=true when provisioned.')
ON CONFLICT (name) DO UPDATE
   SET provider = EXCLUDED.provider,
       auth_secret_ref = EXCLUDED.auth_secret_ref,
       notes = EXCLUDED.notes;

SELECT name, provider, active, notes FROM channels WHERE name = 'whatsapp';
