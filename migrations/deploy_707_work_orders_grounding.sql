-- deploy_707_work_orders_grounding.sql — Supervisor grounding + cancel.
-- Adds 'cancelled' to the work_orders status set (an order created on a false premise is CANCELLED,
-- not done/failed). Supports the new 'ground' first-step (corpus-existence check) that must clear
-- before a gap order reaches a human — the check that was missing when #4/#5 were created.
-- Idempotent.

ALTER TABLE work_orders DROP CONSTRAINT IF EXISTS work_orders_status_check;
ALTER TABLE work_orders ADD CONSTRAINT work_orders_status_check
  CHECK (status IN ('queued','in_progress','awaiting_handoff','blocked_governance',
                    'done','failed','cancelled'));
