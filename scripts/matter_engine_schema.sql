-- Grounded Matter Engine — the spine (creditless schema).
-- Per matter: a web of provenance-stamped facts, grounded in versioned legal authorities,
-- kept current by an event-driven freshness layer. Generation/synthesis sits ON TOP (credit-gated);
-- this schema is the durable, source-agnostic foundation.
-- Invariant: every fact + authority carries provenance_level + an as_of date. Nothing asserted blind.

-- ── Layer 3: law-currency — versioned legal authorities (AnyCase / lawphil / counsel-curated) ──
CREATE TABLE IF NOT EXISTS legal_authorities (
    id serial PRIMARY KEY,
    citation text NOT NULL,                          -- "G.R. No. 215454 (2019)" | "PD 1529 §53" | "NIRC §24(D)"
    authority_type text NOT NULL DEFAULT 'case',     -- case | statute | issuance | rule
    title text,
    holding text,                                    -- the controlling rule/holding (summary)
    full_text text,
    effective_date date,                             -- promulgation / effectivity
    jurisdiction text DEFAULT 'PH',
    source text DEFAULT 'anycase',                   -- anycase | lawphil | sc_elibrary | curated
    source_url text,
    as_of_checked date,                              -- when we last confirmed this is still controlling
    superseded_by int REFERENCES legal_authorities(id),  -- set if overturned / amended / repealed
    provenance_level text DEFAULT 'inferred_strong', -- verified | inferred_strong | inferred_weak
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    UNIQUE (citation, source)
);
CREATE INDEX IF NOT EXISTS idx_legal_authorities_type ON legal_authorities(authority_type);

-- which authority governs which matter (and which element of it)
CREATE TABLE IF NOT EXISTS matter_authorities (
    id serial PRIMARY KEY,
    matter_code text NOT NULL,
    authority_id int NOT NULL REFERENCES legal_authorities(id) ON DELETE CASCADE,
    element_code text,                               -- the element this authority grounds (e.g. 'ownership')
    relevance text DEFAULT 'element',               -- element | defense | procedure | penalty
    note text,
    provenance_level text DEFAULT 'inferred_strong',
    created_at timestamptz DEFAULT now(),
    UNIQUE (matter_code, authority_id, element_code)
);
CREATE INDEX IF NOT EXISTS idx_matter_authorities_matter ON matter_authorities(matter_code);

-- ── Layers 1+2: the web of facts — atomic, provenance-stamped nodes + typed edges ──
CREATE TABLE IF NOT EXISTS matter_facts (
    id serial PRIMARY KEY,
    matter_code text NOT NULL,
    statement text NOT NULL,                         -- the fact in one sentence
    fact_kind text DEFAULT 'fact',                  -- fact | element | event | issue | conclusion
    element_code text,                              -- ties the fact to a claim element
    claim_id int,                                   -- optional link to claims.id
    source_kind text,                               -- doc | email | telegram | authority | testimonial
    source_id text,                                 -- doc_id / gmail msg id / authority id
    excerpt text,                                    -- the quoted grounding excerpt
    as_of date,                                      -- the fact's effective/event date
    provenance_level text DEFAULT 'inferred_strong',
    confidence real,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_matter_facts_matter ON matter_facts(matter_code);

CREATE TABLE IF NOT EXISTS fact_edges (
    id serial PRIMARY KEY,
    from_fact int NOT NULL REFERENCES matter_facts(id) ON DELETE CASCADE,
    to_fact int NOT NULL REFERENCES matter_facts(id) ON DELETE CASCADE,
    edge_kind text NOT NULL DEFAULT 'supports',     -- supports | contradicts | derives_from | rebuts
    note text,
    created_at timestamptz DEFAULT now(),
    UNIQUE (from_fact, to_fact, edge_kind)
);

-- ── Layer 4: freshness — per-matter currency vs its live inputs (the "up to the minute" core) ──
CREATE TABLE IF NOT EXISTS matter_state (
    matter_code text PRIMARY KEY,
    input_fingerprint text,                          -- hash of CURRENT inputs (docs + authorities + matter row)
    inputs_snapshot jsonb,                           -- the current input set (for diffing "what changed")
    last_synthesized_fingerprint text,               -- fingerprint at last synthesis
    last_synth_snapshot jsonb,
    last_synthesized_at timestamptz,
    is_stale boolean DEFAULT true,                   -- current inputs differ from last synthesis
    staleness_reason text,                           -- human-readable: what changed since last synthesis
    last_change_at timestamptz,
    n_docs int DEFAULT 0,
    n_authorities int DEFAULT 0,
    n_facts int DEFAULT 0,
    updated_at timestamptz DEFAULT now()
);
