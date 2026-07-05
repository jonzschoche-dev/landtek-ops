-- deploy_703_work_orders.sql — Supervisor v1 Phase 1 foundation.
-- A Postgres-native work-order state machine: one row per multi-step unit of work, steps as JSONB,
-- append-only audit. NOT a framework — a table + scripts/supervisor.py loop (same primitives as the
-- rest of the stack). Additive; reversible with DROP TABLE. Zero production effect until an order is
-- enqueued and the (Phase 2) timer is enabled.

CREATE TABLE IF NOT EXISTS work_orders (
  id           bigserial PRIMARY KEY,
  kind         text NOT NULL,                         -- routing key into supervisor.KINDS
  matter_code  text,
  title        text,
  status       text NOT NULL DEFAULT 'queued'
               CHECK (status IN ('queued','in_progress','awaiting_handoff',
                                 'blocked_governance','done','failed')),
  steps        jsonb NOT NULL DEFAULT '[]'::jsonb,     -- [{name,agent,mode,tier,status,result}]
  current_step integer NOT NULL DEFAULT 0,
  governed     boolean NOT NULL DEFAULT true,
  created_by   text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  audit        jsonb NOT NULL DEFAULT '[]'::jsonb      -- append-only transition log
);

CREATE INDEX IF NOT EXISTS idx_work_orders_status ON work_orders (status);
CREATE INDEX IF NOT EXISTS idx_work_orders_kind   ON work_orders (kind);
CREATE INDEX IF NOT EXISTS idx_work_orders_matter ON work_orders (matter_code);
