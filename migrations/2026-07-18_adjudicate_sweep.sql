-- 2026-07-18_adjudicate_sweep.sql — adjudication ledger columns on proposed_facts
-- (Read Composer P2, docs/READ_CONSENSUS_DIRECTIVE.md §6 — the drain-or-funeral DECISION GATE's
--  measurement substrate). Additive + idempotent; no existing writer changes behavior.
--
-- Status vocabulary stays INSIDE the existing filters (pending = status NOT IN
-- ('accepted','rejected','promoted')): the sweep writes 'promoted' or 'rejected', with the
-- REASON in adjudication_note ('duplicate_of:<fact_id>' · 'quarantined_source' · ...).
-- A proposal is NEVER deleted — adjudication is a status transition with a ledger, so the
-- 261-baseline closure rate is measurable forever.

BEGIN;

ALTER TABLE proposed_facts ADD COLUMN IF NOT EXISTS adjudicated_at    timestamptz;
ALTER TABLE proposed_facts ADD COLUMN IF NOT EXISTS adjudication_note text;
ALTER TABLE proposed_facts ADD COLUMN IF NOT EXISTS promoted_fact_id  integer
    REFERENCES matter_facts(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_pf_status ON proposed_facts (status);

COMMIT;
