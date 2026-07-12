-- deploy: convergence shadow-diff ledger. leo_instant runs the LIVE path (leo_service.process) and the
-- equilibrium-aligned ORCHESTRATOR (comm_agent_max.handle_chat_event, force_shadow) side-by-side and
-- records the comparison here — so we can prove the orchestrator is at least as strict as the current
-- blunt classify before cutover (Step 4). Idempotent. Rollback: DROP TABLE comm_agent_convergence_diff;

CREATE TABLE IF NOT EXISTS comm_agent_convergence_diff (
  id                    bigserial PRIMARY KEY,
  inbound_msg_id        bigint,
  channel               text,
  live_action           text,       -- leo_service.process: sent | held | held(a25) | send_error | …
  orch_next_action      text,       -- orchestrator: would_send | hold_for_operator | held_a25 | onboarding_flow
  orch_would_clamp      boolean,
  orch_disclosure_tier  text,
  orch_contradictions   int,        -- A76 equilibrium now visible in the live loop
  agree_send_hold       boolean,    -- do live & orchestrator agree on send-vs-hold?
  orch_at_least_as_strict boolean,  -- orchestrator sends ONLY where the live path also sends (safety floor)
  orch_latency_ms       int,
  created_at            timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_convergence_diff_created ON comm_agent_convergence_diff (created_at DESC);

SELECT 'comm_agent_convergence_diff ready' AS status;
