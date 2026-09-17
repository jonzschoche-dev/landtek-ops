-- deploy_934: Reasoning-equilibrium spine (finally the durable tables)
--
-- Why past attempts stalled: role lived in channel_users + policy in comms_role_policy +
-- projection only in Python code; facts stayed prose; no typed fields; no per-matter brief.
-- This migration does NOT replace those SoR pieces — it binds them into one spine.
--
-- Layer 0 (FIRST READ on any inquiry): v_inquiry_principal
--   channel_users.role → comms_role_policy (dose / gate / disclosure)
-- Layer 1: matter_facts (existing SoR — untouched write path)
-- Layer 2: fact_fields (derived, rebuildable, tier-inherited, span-grounded)
-- Layer 3: matter_brief (derived one-row-per-matter snapshot)
--
-- Idempotent. Derived tables may be TRUNCATE + rebuild; channel_users / matter_facts may not.
-- Apply:
--   docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/deploy_934_equilibrium_spine.sql

BEGIN;

-- ─── 0. Role policy already exists (deploy_879). Ensure unknown is safe. ───
INSERT INTO comms_role_policy (role, disclosure_ceiling, gate_default, dose_ceiling, cadence, projection_profile, notes)
VALUES
  ('unknown',  'none', 'hold',   0, 'gentle',   'human_safe',
   'Unresolved identity — hold, never guess (A5/A77).'),
  ('operator', 'full', 'allow', 20, 'standard', 'machine_typed',
   'Jonathan / firm operator — full internal slice.')
ON CONFLICT (role) DO NOTHING;

-- ─── 1. FIRST TABLE (view): who is inquiring + what their role allows ───
-- channel_users is the live identity ledger; this view is the equilibrium front door.
CREATE OR REPLACE VIEW v_inquiry_principal AS
SELECT
    cu.id                          AS principal_id,
    cu.channel_id,
    cu.channel_user_id,
    cu.display_name,
    lower(coalesce(nullif(trim(cu.approved_role), ''),
                   nullif(trim(cu.role), ''),
                   'unknown'))     AS role,
    cu.mapped_client_code          AS client_code,
    cu.mapped_operator,
    cu.authorized,
    cu.bind_confidence,
    cu.entity_id,
    cu.onboarding_state,
    cu.approved_scope_case         AS matter_scope_hint,
    p.disclosure_ceiling,
    p.gate_default,
    p.dose_ceiling,
    p.cadence,
    p.projection_profile,
    p.notes                        AS role_policy_notes,
    cu.last_seen_at,
    cu.first_seen_at
FROM channel_users cu
LEFT JOIN comms_role_policy p
  ON p.role = lower(coalesce(nullif(trim(cu.approved_role), ''),
                             nullif(trim(cu.role), ''),
                             'unknown'));

COMMENT ON VIEW v_inquiry_principal IS
  'Equilibrium front door: every inquiry resolves here first (who + role + dose/gate/scope). '
  'SoR remains channel_users + comms_role_policy; this view never invents identity.';

-- ─── 2. fact_fields — typed decomposition of matter_facts prose (DERIVED) ───
CREATE TABLE IF NOT EXISTS fact_fields (
    id                bigserial PRIMARY KEY,
    fact_id           int NOT NULL REFERENCES matter_facts(id) ON DELETE CASCADE,
    matter_code       text NOT NULL,
    field_kind        text NOT NULL,   -- ctn|tct|docket|date|amount|party|doc_ref|forum|arp|other
    value_raw         text NOT NULL,
    value_norm        text NOT NULL,
    provenance_level  text NOT NULL,   -- INHERITED from parent fact; never promoted here
    extraction_method text NOT NULL DEFAULT 'regex',  -- regex | llm
    char_start        int,
    char_end          int,
    source_span       text NOT NULL,   -- verbatim substring of statement|excerpt
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (fact_id, field_kind, value_norm)
);

CREATE INDEX IF NOT EXISTS fact_fields_matter_kind_idx
  ON fact_fields (matter_code, field_kind);
CREATE INDEX IF NOT EXISTS fact_fields_kind_norm_idx
  ON fact_fields (field_kind, value_norm);
CREATE INDEX IF NOT EXISTS fact_fields_prov_idx
  ON fact_fields (provenance_level);

COMMENT ON TABLE fact_fields IS
  'DERIVED projection of matter_facts. Rebuildable. value must be verbatim span of parent. '
  'provenance_level is inherited — decomposition never launders tiers.';

-- ─── 3. matter_brief — one digested row per matter (DERIVED) ───
CREATE TABLE IF NOT EXISTS matter_brief (
    matter_code            text PRIMARY KEY,
    status                 text,
    stage                  text,
    forum                  text,
    n_facts_verified       int NOT NULL DEFAULT 0,
    n_facts_provisional    int NOT NULL DEFAULT 0,
    n_fields_total         int NOT NULL DEFAULT 0,
    n_fields_verified      int NOT NULL DEFAULT 0,
    ctns                   text[] NOT NULL DEFAULT '{}',
    tcts                   text[] NOT NULL DEFAULT '{}',
    dockets                text[] NOT NULL DEFAULT '{}',
    parties                text[] NOT NULL DEFAULT '{}',
    key_dates              jsonb NOT NULL DEFAULT '[]'::jsonb,
    amounts                jsonb NOT NULL DEFAULT '[]'::jsonb,
    next_deadline          date,
    n_open_contradictions  int NOT NULL DEFAULT 0,
    top_doc_ids            int[] NOT NULL DEFAULT '{}',
    readiness              jsonb NOT NULL DEFAULT '{}'::jsonb,
    headline               text NOT NULL DEFAULT '',
    angle_status           jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_fingerprint     text,
    computed_at            timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE matter_brief IS
  'DERIVED one-row-per-matter snapshot for inquiry lookup. Deterministic headline. '
  'Stale when computed_at < max(matter_facts.created_at/updated) for that matter.';

-- ─── 4. Coverage meter (for continuous health, not LLM judgment) ───
CREATE TABLE IF NOT EXISTS equilibrium_coverage_log (
    id              bigserial PRIMARY KEY,
    logged_at       timestamptz NOT NULL DEFAULT now(),
    n_facts         int,
    n_facts_verified int,
    n_facts_with_fields int,
    typed_coverage_pct numeric(6,2),
    n_briefs        int,
    n_briefs_stale  int,
    notes           text
);

-- ─── 5. Staleness helper view ───
CREATE OR REPLACE VIEW v_matter_brief_staleness AS
SELECT
    m.matter_code,
    b.computed_at,
    f.max_fact_at,
    (b.matter_code IS NULL) AS missing_brief,
    (b.computed_at IS NULL OR f.max_fact_at IS NULL OR b.computed_at < f.max_fact_at) AS is_stale
FROM matters m
LEFT JOIN matter_brief b ON b.matter_code = m.matter_code
LEFT JOIN LATERAL (
    SELECT max(coalesce(mf.created_at, now())) AS max_fact_at
    FROM matter_facts mf
    WHERE mf.matter_code = m.matter_code
) f ON true
WHERE coalesce(m.status, '') NOT IN ('archived');

COMMIT;

-- smoke
SELECT 'v_inquiry_principal rows: ' || count(*)::text FROM v_inquiry_principal;
SELECT 'comms_role_policy roles: ' || string_agg(role, ',' ORDER BY role) FROM comms_role_policy;
SELECT 'fact_fields ready: ' || to_regclass('fact_fields')::text;
SELECT 'matter_brief ready: ' || to_regclass('matter_brief')::text;
