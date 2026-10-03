-- deploy_980: CoS↔VPS awareness bridge — extend agent_registry.layer for Grok Bot + Claude seats.
--
-- Principle 10: cos_bridge owns grok_bot + claude_subagent upserts; fleet_registry keeps owning
-- systemd/cron/catalog. No second registry table. Equilibrium hook: cos_bridge --pulse writes a
-- shadow fleet_change row into propagation_log (deploy_881) + a note into equilibrium_coverage_log
-- (deploy_934) so the A76 reactive spine can see roster perturbations — reuse, don't fork.
--
-- Additive / idempotent. Prefer reusing layer + note (+ external UUID in note); no new columns.
-- Apply (VPS):
--   docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/deploy_980_cos_awareness_bridge.sql

BEGIN;

-- Postgres names inline CHECKs {table}_{column}_check
ALTER TABLE agent_registry DROP CONSTRAINT IF EXISTS agent_registry_layer_check;
ALTER TABLE agent_registry ADD CONSTRAINT agent_registry_layer_check
  CHECK (layer IN (
    'systemd','cron','cron-child','catalog-only',
    'grok_bot','claude_subagent'
  ));

COMMENT ON COLUMN agent_registry.layer IS
  'Enumeration surface: systemd|cron|cron-child|catalog-only (fleet_registry) · grok_bot|claude_subagent (cos_bridge).';

COMMIT;

SELECT 'deploy_980: agent_registry.layer accepts grok_bot + claude_subagent' AS status;
