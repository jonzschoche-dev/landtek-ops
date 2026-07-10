-- deploy_828: register the Messenger channel READY (adapter live, awaiting token) — no external exposure.
-- The /api/channel/messenger adapter (clone of the WhatsApp pattern) queues replies as
-- 'pending_no_credentials' until MESSENGER_PAGE_TOKEN + MESSENGER_VERIFY_TOKEN land in .env, and the
-- landtek-messenger-bridge.timer drains the backlog the moment they do. Token = the external switch (A26);
-- active stays FALSE until Jonathan provisions the Meta app + Page and flips it.
--
-- Run on the VPS:
--   docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/deploy_828_messenger_channel_ready.sql

INSERT INTO channels (name, provider, auth_secret_ref, webhook_url, active, notes)
VALUES ('messenger', 'meta_graph_api', 'MESSENGER_PAGE_TOKEN', '/api/channel/messenger', false,
        'READY, awaiting token. Adapter /api/channel/messenger live (Meta GET verify-challenge + Send API). Inbound sends inline once MESSENGER_PAGE_TOKEN + MESSENGER_VERIFY_TOKEN are in .env (read live, no restart). Backlog auto-drains via landtek-messenger-bridge.timer. Token = the external switch (A26); flip active=true when the Meta app + Page are provisioned. Same Meta app as WhatsApp where possible.')
ON CONFLICT (name) DO UPDATE
   SET provider = EXCLUDED.provider,
       auth_secret_ref = EXCLUDED.auth_secret_ref,
       webhook_url = EXCLUDED.webhook_url,
       notes = EXCLUDED.notes;

SELECT name, provider, active FROM channels WHERE name='messenger';
