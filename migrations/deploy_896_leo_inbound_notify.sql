-- deploy_896: instant-reply signal — a trigger that pg_notify's on every new INBOUND channel_message so
-- the leo_instant daemon can answer in real time instead of waiting for the 4-min leo-service timer.
-- The daemon gates hard (TEST_IDENTITIES + headless channel + internal-send only), so this NOTIFY firing
-- on all channels is harmless — outward/real-client inbound is ignored or held. Idempotent.
-- Rollback: DROP TRIGGER trg_notify_leo_inbound ON channel_messages; DROP FUNCTION notify_leo_inbound();

CREATE OR REPLACE FUNCTION notify_leo_inbound() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.direction = 'inbound' THEN
    PERFORM pg_notify('leo_inbound', NEW.id::text);
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_notify_leo_inbound ON channel_messages;
CREATE TRIGGER trg_notify_leo_inbound
  AFTER INSERT ON channel_messages
  FOR EACH ROW EXECUTE FUNCTION notify_leo_inbound();

SELECT 'leo_inbound NOTIFY trigger installed' AS status;
