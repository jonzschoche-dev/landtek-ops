-- deploy_938: Agentic inquiry stack
--
-- Flow:
--   inquiry → scrutinize COMPLETE stack → answer from hits
--         → write-back structured results into pertinent tables
--         → enqueue agents whose mandates own tables that care about the new data
--
-- This is the opposite of per-question English routers: the stack is the brain;
-- agents are compelled by their tables.
--
--   docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/deploy_938_inquiry_agentic_stack.sql

BEGIN;

-- ── 1. Agent mandate registry: what tables compel each agent ───────────────
CREATE TABLE IF NOT EXISTS agent_mandates (
    agent_key           text PRIMARY KEY,
    mandate             text NOT NULL,
    owns_tables         text[] NOT NULL DEFAULT '{}',   -- tables it must keep healthy
    reads_tables        text[] NOT NULL DEFAULT '{}',
    trigger_on          text[] NOT NULL DEFAULT '{}',   -- events: new_document_field, new_matter_fact, inquiry_answer, ...
    compel_sql          text,   -- optional: returns rows that mean "work pending"
    active              boolean NOT NULL DEFAULT true,
    notes               text,
    updated_at          timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE agent_mandates IS
  'Each agent is agentic because it owns tables and reacts when those tables (or trigger events) change.';

-- ── 2. Inquiry run (one human/machine ask) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS inquiry_runs (
    id                  bigserial PRIMARY KEY,
    created_at          timestamptz NOT NULL DEFAULT now(),
    channel             text,
    channel_user_id     text,
    client_code         text,
    principal_role      text,
    message             text NOT NULL,
    message_norm        text,
    status              text NOT NULL DEFAULT 'open',  -- open|answered|held|error
    answer_text         text,
    answer_via          text,   -- stack_hit|stack_partial|held_unclear|error
    source_refs         jsonb NOT NULL DEFAULT '[]'::jsonb,
    writeback_summary   jsonb NOT NULL DEFAULT '{}'::jsonb,
    duration_ms         int
);

CREATE INDEX IF NOT EXISTS inquiry_runs_client_idx ON inquiry_runs (client_code, created_at DESC);
CREATE INDEX IF NOT EXISTS inquiry_runs_status_idx ON inquiry_runs (status);

-- ── 3. Per-layer scrutiny log (complete stack check) ───────────────────────
CREATE TABLE IF NOT EXISTS inquiry_scrutiny (
    id                  bigserial PRIMARY KEY,
    inquiry_id          bigint NOT NULL REFERENCES inquiry_runs(id) ON DELETE CASCADE,
    layer               text NOT NULL,   -- role|matters|matter_brief|document_fields|matter_facts|title_brief|filings_proxy|holes
    status              text NOT NULL,   -- hit|miss|empty|error|skip
    hit_count           int NOT NULL DEFAULT 0,
    payload             jsonb NOT NULL DEFAULT '{}'::jsonb,
    notes               text
);

CREATE INDEX IF NOT EXISTS inquiry_scrutiny_inq_idx ON inquiry_scrutiny (inquiry_id);

-- ── 4. Structured answer atoms (written back into living DB) ───────────────
CREATE TABLE IF NOT EXISTS inquiry_answer_atoms (
    id                  bigserial PRIMARY KEY,
    inquiry_id          bigint NOT NULL REFERENCES inquiry_runs(id) ON DELETE CASCADE,
    atom_kind           text NOT NULL,   -- mro_ref|ctn|docket|tct|party|date|statement|...
    value_norm          text NOT NULL,
    value_raw           text,
    matter_code         text,
    doc_id              int,
    provenance_level    text NOT NULL DEFAULT 'inferred_strong',
    written_to          text[] NOT NULL DEFAULT '{}',  -- which tables received writeback
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS inquiry_atoms_kind_idx ON inquiry_answer_atoms (atom_kind, value_norm);

-- ── 5. Agent work queue (table-compelled agency) ───────────────────────────
CREATE TABLE IF NOT EXISTS agent_work_queue (
    id                  bigserial PRIMARY KEY,
    created_at          timestamptz NOT NULL DEFAULT now(),
    agent_key           text NOT NULL,
    event_type          text NOT NULL,
    payload             jsonb NOT NULL DEFAULT '{}'::jsonb,
    inquiry_id          bigint REFERENCES inquiry_runs(id) ON DELETE SET NULL,
    status              text NOT NULL DEFAULT 'pending',  -- pending|claimed|done|skipped
    claimed_at          timestamptz,
    done_at             timestamptz,
    result_note         text
);

CREATE INDEX IF NOT EXISTS agent_work_queue_pending_idx
  ON agent_work_queue (agent_key, status, created_at)
  WHERE status = 'pending';

-- ── 6. Seed mandates (live agents we already run) ──────────────────────────
INSERT INTO agent_mandates (agent_key, mandate, owns_tables, reads_tables, trigger_on, notes) VALUES
(
  'doc_populate',
  'Turn every document with text into typed rows',
  ARRAY['document_fields','table_populate_log'],
  ARRAY['documents','document_matter_links'],
  ARRAY['new_document','inquiry_gap_doc'],
  'Agent 001 — bulk loader'
),
(
  'verify_worker',
  'Upgrade grounded claims to verified with verbatim excerpt',
  ARRAY['matter_facts','proposed_facts','verify_worker_log'],
  ARRAY['documents','document_fields'],
  ARRAY['new_matter_fact','inquiry_answer_atom'],
  'Only verified tier via gate'
),
(
  'matter_brief_materializer',
  'Keep one digested row per matter for inquiry',
  ARRAY['matter_brief'],
  ARRAY['matter_facts','fact_fields','matter_parties'],
  ARRAY['new_matter_fact','inquiry_answer_atom','fact_fields_changed'],
  'Lookup surface for matters'
),
(
  'title_brief_materializer',
  'Keep one digested card per title for property UI',
  ARRAY['title_brief'],
  ARRAY['titles','document_fields','document_titles','property_assets'],
  ARRAY['new_document_field','new_title_mention'],
  'Property classification substrate'
),
(
  'fact_field_extractor',
  'Decompose matter_facts prose into typed fact_fields',
  ARRAY['fact_fields'],
  ARRAY['matter_facts'],
  ARRAY['new_matter_fact','inquiry_answer_atom'],
  'Typed findability layer'
),
(
  'inquiry_stack',
  'Scrutinize full stack for an ask, answer, write back, trigger agents',
  ARRAY['inquiry_runs','inquiry_scrutiny','inquiry_answer_atoms','agent_work_queue'],
  ARRAY['document_fields','matter_facts','matter_brief','title_brief','v_inquiry_principal'],
  ARRAY['inbound_message'],
  'The inquiry agent — closes the loop'
)
ON CONFLICT (agent_key) DO UPDATE SET
  mandate = EXCLUDED.mandate,
  owns_tables = EXCLUDED.owns_tables,
  reads_tables = EXCLUDED.reads_tables,
  trigger_on = EXCLUDED.trigger_on,
  notes = EXCLUDED.notes,
  updated_at = now();

COMMIT;

SELECT 'agent_mandates: ' || count(*)::text FROM agent_mandates;
SELECT 'inquiry_runs ready: ' || to_regclass('inquiry_runs')::text;
SELECT 'agent_work_queue ready: ' || to_regclass('agent_work_queue')::text;
