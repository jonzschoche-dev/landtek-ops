-- Universal comms-artifact intake ledger — makes "lossless intake" mechanically provable (T3).
-- Every inbound media artifact from any channel gets EXACTLY one row here: landed (has doc_id),
-- deduped (has doc_id of the pre-existing doc), held (A5 unresolved client — visible, never dropped),
-- or quarantined (processing error — visible, never dropped). A media message with NO row = a silent
-- drop = the failure this closes. Email is NOT a client of this sink (imap_ingest is lossless already).
--
-- Idempotent. Rollback: DROP TABLE comms_artifacts;

CREATE TABLE IF NOT EXISTS comms_artifacts (
  id                  bigserial PRIMARY KEY,
  channel             text NOT NULL,                 -- telegram | whatsapp | messenger | sms | ...
  channel_user_id     text,
  channel_message_id  bigint REFERENCES channel_messages(id) ON DELETE SET NULL,
  client_code         text,                          -- resolved via channel_users.mapped_client_code (A25)
  media_ref           text,                          -- platform media id / attachment URL (provenance)
  original_filename   text,
  mime_type           text,
  media_type          text,                          -- image | audio | video | document | text | unknown
  content_hash        text,
  doc_id              bigint REFERENCES documents(id) ON DELETE SET NULL,
  processing_state    text,                          -- ocr_pending | transcribe_pending | none
  status              text NOT NULL CHECK (status IN ('landed','deduped','held','quarantined')),
  reason              text,
  created_at          timestamptz DEFAULT now()
);

-- one ledger row per (message, artifact) — re-running the sink on the same artifact is a no-op
CREATE UNIQUE INDEX IF NOT EXISTS uq_comms_artifacts_msg_hash
  ON comms_artifacts (channel_message_id, content_hash)
  WHERE channel_message_id IS NOT NULL AND content_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_comms_artifacts_status ON comms_artifacts (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_comms_artifacts_client ON comms_artifacts (client_code);

SELECT 'comms_artifacts ready; rows='||count(*) FROM comms_artifacts;
