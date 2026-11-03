-- deploy_1324: officer -> Jonathan relay. Kristyle, 3 Nov 2026: "Check it for me" / "Notify Jonathan to check" —
-- the bot could not pass it on. Relays are logged as staff_question outcome 'relay' (shown under Needs you on
-- /ops/now) and pushed to Jonathan's Telegram through tg_send (S14 pacing; Messenger cannot reach him outside
-- its 24h window). Idempotent.
ALTER TABLE staff_question DROP CONSTRAINT IF EXISTS staff_question_outcome_check;
ALTER TABLE staff_question ADD CONSTRAINT staff_question_outcome_check
    CHECK (outcome IN ('answered', 'not_in_sources', 'rejected_unsupported', 'error', 'relay'));
ALTER TABLE staff_question ADD COLUMN IF NOT EXISTS relayed_via text;
