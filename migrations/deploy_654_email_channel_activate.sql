-- deploy_654: activate the email channel (INBOUND live; OUTBOUND send HELD)
-- Part of the Platform Coordinator work. Email is the first pathway opened.
-- The channel bus + adapter (/api/channel/email) + bridge already existed (deploy_114);
-- this only flips the status flag so ops_dashboard tells the truth: email pathway is
-- live for inbound routing, while outbound send stays held behind the operator switch.
--
-- Run on the VPS:
--   docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/deploy_654_email_channel_activate.sql

INSERT INTO channels (name, provider, auth_secret_ref, active, notes)
VALUES ('email', 'gmail_api', 'GMAIL_REFRESH_TOKEN', true,
        'INBOUND live via landtek-email-bridge.timer (--inbound, 10 min). OUTBOUND send HELD — external switch; run email_channel_bridge.py --send manually until operator opens it.')
ON CONFLICT (name) DO UPDATE
   SET active = true,
       provider = EXCLUDED.provider,
       auth_secret_ref = EXCLUDED.auth_secret_ref,
       notes = EXCLUDED.notes;

SELECT name, provider, active, notes FROM channels WHERE name = 'email';
