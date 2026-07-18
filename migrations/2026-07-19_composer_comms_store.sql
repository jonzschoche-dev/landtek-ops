-- 2026-07-19_composer_comms_store.sql — correspondence enters the composer's registry
-- (the Botor/CV6839 miss: counsel/engagement questions are CORRESPONDENCE questions, and the
-- one reader had no comms store — ABLAW's engagement sat matter-tagged in gmail_messages while
-- the fact layer said "no counsel"). gmail_messages joins matter_status as rank-3 SUPPORT:
-- existence/recency/subject surface in the frame; email CONTENT stays support-grade (a mention
-- in an email is not a verified fact — harvest lifts content to facts through the gates).

BEGIN;

UPDATE consensus_registry SET
  store_rank = '[{"store":"matters","role":"answer","rank":1},
                 {"store":"matter_brief","role":"cache","rank":2},
                 {"store":"matter_facts","role":"support","rank":3},
                 {"store":"gmail_messages","role":"support","rank":3},
                 {"store":"proposed_facts","role":"mention_only","rank":5}]',
  notes = coalesce(notes,'') || ' | 2026-07-19: gmail_messages added as rank-3 support (matter-tagged correspondence count/recency/subject in the frame) — counsel questions are correspondence questions (the Botor/CV6839 lesson)',
  updated_at = now()
WHERE concept = 'matter_status';

COMMIT;
