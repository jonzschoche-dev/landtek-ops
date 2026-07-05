-- deploy_699_constitution_regen_log.sql
-- Governance visibility (GOVERNED_ACTIONS.md §3 item 5): capture a coarse diff-summary each time
-- the auto-regenerated SYSTEM_CONSTITUTION.md actually changes (content-hash delta), so a silent
-- shift in the system's knowledge boundary is surfaced in the daily digest. Visibility only, no gating.
-- Idempotent.

CREATE TABLE IF NOT EXISTS constitution_regen_log (
  id           bigserial PRIMARY KEY,
  ts           timestamptz NOT NULL DEFAULT now(),
  content_hash text,
  n_facts      integer,
  n_keystones  integer,
  changed      boolean NOT NULL DEFAULT false
);
