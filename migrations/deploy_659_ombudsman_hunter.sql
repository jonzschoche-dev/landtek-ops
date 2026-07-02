-- deploy_NN_ombudsman_hunter.sql
-- The accretion layer for OMBUDSMAN HUNTER (scripts/ombudsman_hunter.py).
--
-- One row per (public official x violation theory) the hunter has assembled from the
-- verified corpus. These are LEADS, not asserted facts: every candidate carries evidence
-- HANDLES (matter_fact ids / doc ids) so nothing is a naked assertion, and provenance is
-- inference-grade by construction. The engine NEVER sets status='filed' — filing against a
-- named public officer is a held, human-approved decision (like leo_improvement_proposals).
--
-- Reuses (does not duplicate): play_engine.ombudsman_3e readiness, legal_authority OMBUDSMAN
-- law library, case_synthesizer playbook renderer, matter_facts / matters as the source rows.

CREATE TABLE IF NOT EXISTS ombudsman_candidates (
    id              serial PRIMARY KEY,
    official        text NOT NULL,                 -- respondent public officer (as named in the record)
    office          text,                          -- e.g. "Office of the Municipal Assessor, Mercedes"
    capacity        text,                          -- elective | appointive | career  (drives forum route)
    matters         text[] DEFAULT '{}',           -- matter_codes the official appears in
    violation_code  text NOT NULL,                 -- ra3019_3e | ra3019_3f | ra6713_5a | rpc_171 | grave_misconduct ...
    statute         text,                          -- human cite, e.g. "R.A. 3019, Sec. 3(e)"
    forum           text,                          -- OMBUDSMAN | CSC | SANDIGANBAYAN (routed, not filed)
    elements        jsonb DEFAULT '{}'::jsonb,     -- {element_key: {state: have|thin|missing, handle: [...]}}
    signals         jsonb DEFAULT '{}'::jsonb,     -- {signal_key: [fact_id|doc:NNN, ...]}  -- the evidence handles
    prescription    text,                          -- prescription posture / clock note (NEEDS-COUNSEL-VERIFICATION)
    status          text DEFAULT 'seed',           -- seed | building | ripe | held_for_filing   (NEVER 'filed')
    strength        numeric DEFAULT 0,             -- proven-elements / needed-elements (0..1)
    leverage        int DEFAULT 3,                 -- 1..5 toward the north-star (strategy_engine Ombudsman lever)
    score           numeric DEFAULT 0,             -- strength x leverage x forum_fit  (ranking key)
    gaps            jsonb DEFAULT '[]'::jsonb,      -- what must be pinned before this graduates to a filing
    rationale       text,                          -- one-line why this is (or isn't) ripe
    provenance      text DEFAULT 'inferred_strong',-- candidates are leads, never verified facts
    updated_at      timestamptz DEFAULT now(),
    UNIQUE (official, violation_code)
);

CREATE INDEX IF NOT EXISTS idx_ombuds_status ON ombudsman_candidates(status);
CREATE INDEX IF NOT EXISTS idx_ombuds_score  ON ombudsman_candidates(score DESC);

COMMENT ON TABLE ombudsman_candidates IS
  'OMBUDSMAN HUNTER leads: (official x violation) with evidence handles. Inference-grade; filing is human-gated.';
