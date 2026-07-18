-- 2026-07-18_adjudicate_queue.sql — Option A substrate: the dose-capped operator batch queue
-- (Read Composer P2 §6 Option A, chosen by the operator 2026-07-18 on the 7%-mechanical evidence).
-- Additive + idempotent. Offer tracking on proposed_facts + the queue view.
--
-- Status vocabulary DELIBERATE extension: 'expired' (terminal) — an item offered
-- ADJ_MAX_OFFERS times without operator action expires to a LABELED inferred_* fact
-- (knowledge enters the graph at an honest tier instead of rotting in an inbox — never
-- silently dropped, never upgraded). Filters updated in the same deploy:
-- leo_tools/consensus.py pending-counts + truth_tests/test_adjudication_ledger.py vocabulary.

BEGIN;

ALTER TABLE proposed_facts ADD COLUMN IF NOT EXISTS offered_at  timestamptz;
ALTER TABLE proposed_facts ADD COLUMN IF NOT EXISTS offer_count integer NOT NULL DEFAULT 0;

-- Today's live batch — what the operator sees on --list / in the digest line
CREATE OR REPLACE VIEW v_adjudication_queue AS
SELECT id, matter_code, statement, excerpt, source_doc_id, confidence,
       offer_count, offered_at, created_at
FROM proposed_facts
WHERE status = 'pending' AND offered_at::date = CURRENT_DATE
ORDER BY matter_code, id;

COMMIT;
