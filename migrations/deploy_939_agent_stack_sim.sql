-- deploy_939: Agent-stack simulator (grounded, mechanical)
--
-- Companion to deploy_938 (agentic inquiry stack). The simulator drives the
-- REAL pipeline — inquiry → writeback → agent_work_queue → drain — so agents
-- populate their own tables through their compelled hooks.
--
-- Anti-trap doctrine (P0): NO synthetic facts. Every probe is seeded from
-- rows already in the DB and its expected answer IS those rows' values.
-- Grading is mechanical (substring / status / leak) — no LLM judge.
--
--   docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/deploy_939_agent_stack_sim.sql

BEGIN;

-- ── 1. One row per simulator cycle ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_sim_cycles (
    id                  bigserial PRIMARY KEY,
    started_at          timestamptz NOT NULL DEFAULT now(),
    finished_at         timestamptz,
    n_probes            int NOT NULL DEFAULT 0,
    n_hit               int NOT NULL DEFAULT 0,
    n_answered_miss     int NOT NULL DEFAULT 0,   -- answered but expected value absent
    n_held              int NOT NULL DEFAULT 0,   -- fail-closed (held_ok + held_miss)
    n_leak              int NOT NULL DEFAULT 0,   -- forbidden substring surfaced (P0)
    n_error             int NOT NULL DEFAULT 0,
    suppressed_notifies int NOT NULL DEFAULT 0,   -- operator pings the sim swallowed
    table_deltas        jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {table: {before,after,delta}}
    drain_notes         jsonb NOT NULL DEFAULT '[]'::jsonb,  -- per-agent drain results
    notes               text
);

COMMENT ON TABLE agent_sim_cycles IS
  'agent_stack_sim.py cycles: grounded probes through the live inquiry stack + agent drains. table_deltas shows what the agents populated.';

-- ── 2. One row per probe ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_sim_probes (
    id                  bigserial PRIMARY KEY,
    cycle_id            bigint NOT NULL REFERENCES agent_sim_cycles(id) ON DELETE CASCADE,
    probe_kind          text NOT NULL,   -- arta_ctn|op_docket|title_status|title_inventory|who_is|separation_guard
    message             text NOT NULL,
    client_code         text NOT NULL,
    expected            text[] NOT NULL DEFAULT '{}',  -- values the DB says exist (grounded)
    forbidden           text[] NOT NULL DEFAULT '{}',  -- cross-client leak tripwires
    seed                jsonb NOT NULL DEFAULT '{}'::jsonb,  -- where the probe came from
    inquiry_id          bigint,          -- FK-loose: inquiry_runs row this probe created
    answer_via          text,            -- stack_hit|held_unclear|pass_to_human|error
    grade               text,            -- hit|answered_miss|emission_miss|held_ok|held_miss|leak|error
    missing             text[] NOT NULL DEFAULT '{}',
    leaked              text[] NOT NULL DEFAULT '{}',
    duration_ms         int,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS agent_sim_probes_cycle_idx ON agent_sim_probes (cycle_id);
CREATE INDEX IF NOT EXISTS agent_sim_probes_grade_idx ON agent_sim_probes (grade);

-- ── 3. Phone-friendly rollup ────────────────────────────────────────────────
CREATE OR REPLACE VIEW agent_sim_recent AS
SELECT c.id, c.started_at, c.n_probes, c.n_hit, c.n_answered_miss,
       c.n_held, c.n_leak, c.n_error,
       round(100.0 * c.n_hit / nullif(c.n_probes, 0), 1) AS hit_pct,
       (SELECT sum((v.value ->> 'delta')::bigint)
          FROM jsonb_each(c.table_deltas) v)             AS rows_populated,
       c.finished_at - c.started_at                      AS took
FROM agent_sim_cycles c
ORDER BY c.id DESC
LIMIT 20;

COMMIT;

SELECT 'agent_sim_cycles ready: '  || to_regclass('agent_sim_cycles')::text;
SELECT 'agent_sim_probes ready: '  || to_regclass('agent_sim_probes')::text;
