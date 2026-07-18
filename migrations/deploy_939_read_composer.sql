-- deploy_939_read_composer.sql — Read Composer P0 substrate (docs/READ_CONSENSUS_DIRECTIVE.md §3/§4)
--
-- Two tables, both DERIVED-layer (A50: the composer owns no truth):
--   consensus_registry — the executable authority order (ONTOLOGY §2 made runtime; diffable, never per-surface)
--   composer_audit     — every envelope logged (the emission-audit half of the directive §10.1)
-- Idempotent by construction (IF NOT EXISTS + ON CONFLICT); safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS consensus_registry (
    concept        text PRIMARY KEY,
    store_rank     jsonb NOT NULL,      -- ordered [{store, role, rank}]; role ∈ answer|cache|support|mention_only
    reconcile_rule text  NOT NULL,      -- authority | latest_verified | corroboration_n | operator_wins
    staleness_h    integer,             -- cache-freshness horizon (hours) for rank-2 cards
    notes          text,
    updated_at     timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS composer_audit (
    id           bigserial PRIMARY KEY,
    ts           timestamptz DEFAULT now(),
    intent       text NOT NULL,
    params       jsonb,
    client_code  text,
    role         text,
    status       text NOT NULL,          -- hit | partial | miss | hold
    n_claims     integer,
    confidence   real,
    gaps         jsonb,
    dissent      jsonb,
    envelope     jsonb,
    caller       text
);
CREATE INDEX IF NOT EXISTS idx_composer_audit_ts     ON composer_audit (ts);
CREATE INDEX IF NOT EXISTS idx_composer_audit_intent ON composer_audit (intent, status);

-- Seed the four P0 concepts. Rank semantics per directive §4:
--   0 operator corrections (locked rows)  1 SoR verified/operator  2 fresh derived cards
--   3 support/corroborate  4 inferred_* (labeled)  5 mention_only (leads/gaps, NEVER answer values)
INSERT INTO consensus_registry (concept, store_rank, reconcile_rule, staleness_h, notes) VALUES
('matter_status',
 '[{"store":"matters","role":"answer","rank":1},
   {"store":"matter_brief","role":"cache","rank":2},
   {"store":"matter_facts","role":"support","rank":3},
   {"store":"proposed_facts","role":"mention_only","rank":5}]',
 'authority', 26,
 'status/stage/forum/next_deadline from the SoR row; fresh brief headline as cache; proposed_facts contributes ONLY the pending_adjudication gap'),
('title',
 '[{"store":"titles","role":"answer","rank":1},
   {"store":"title_brief","role":"cache","rank":2},
   {"store":"title_chain","role":"support","rank":3},
   {"store":"instruments_on_title","role":"support","rank":3},
   {"store":"document_titles","role":"mention_only","rank":5}]',
 'authority', 26,
 'chain-cancellation outranks a clean face-read (the T-52540 trap): losing value goes to dissent, never dropped; document_titles = leads only (mention is not membership)'),
('deadlines',
 '[{"store":"matters.next_deadline","role":"answer","rank":1},
   {"store":"surfaced_deadlines","role":"answer","rank":1},
   {"store":"calendar_events","role":"answer","rank":1},
   {"store":"fact_fields.date","role":"mention_only","rank":5}]',
 'latest_verified', NULL,
 'three governed homes composed to one dated list (A68: all three are already source-gated); prose dates never promoted; undated matters reported honestly (A57)'),
('facts',
 '[{"store":"matter_facts","role":"answer","rank":1},
   {"store":"fact_fields","role":"support","rank":3},
   {"store":"field_consensus","role":"support","rank":3},
   {"store":"proposed_facts","role":"mention_only","rank":5}]',
 'authority', NULL,
 'verified first; inferred_* emitted only labeled (external dose is A79/A75 downstream); raw proposed_facts NEVER asserted truth')
ON CONFLICT (concept) DO UPDATE
   SET store_rank = EXCLUDED.store_rank,
       reconcile_rule = EXCLUDED.reconcile_rule,
       staleness_h = EXCLUDED.staleness_h,
       notes = EXCLUDED.notes,
       updated_at = now();

COMMIT;
