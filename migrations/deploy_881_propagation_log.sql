-- deploy_881: A76 P2 — propagation_log, the SHADOW ledger for reactive ego-network recompute.
-- Internal-plane only: equilibrium_propagate.py reads v_relationship_graph, runs the equilibrium checks,
-- and records what it computed here. It emits NOTHING (the emission plane is the A79 gate). This is a
-- LEDGER, not a graph store — fact_edges stays DRIFT (V1-blocked), the graph stays the view.
-- Idempotent. Rollback: DROP TABLE propagation_log;

CREATE TABLE IF NOT EXISTS propagation_log (
  id                   bigserial PRIMARY KEY,
  interaction_ref      text,                 -- what perturbed the graph (channel_message id / fact id / …)
  seed_type            text,
  seed_id              text,
  client_code          text,                 -- the A5 scope of the whole recompute
  ego_hops             int,
  ego_nodes            int,                  -- ego-network size (same-client only)
  contradictions_found int  DEFAULT 0,       -- surfaced to the A65 register, never silently resolved
  cascades_touched     int  DEFAULT 0,       -- keystones in the ego
  cross_client_refused int  DEFAULT 0,       -- edges the per-hop A5 guard dropped (proves it bit)
  mode                 text DEFAULT 'shadow',
  detail               jsonb,
  created_at           timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_propagation_log_seed ON propagation_log (seed_type, seed_id, created_at DESC);

SELECT 'propagation_log ready' AS status;
