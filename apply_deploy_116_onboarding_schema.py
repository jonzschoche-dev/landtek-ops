#!/usr/bin/env python3
"""Deploy 116 — Onboarding state machine schema.

Adds onboarding workflow to channel_users so unknown senders are
guided through a Q&A and routed to Jonathan for approval, instead of
being silently rejected.
"""
import psycopg2
DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SQL = r"""
ALTER TABLE channel_users
  ADD COLUMN IF NOT EXISTS onboarding_state text DEFAULT 'awaiting_intro',
  -- 'awaiting_intro' | 'awaiting_classification' | 'awaiting_details'
  -- | 'awaiting_jonathan_approval' | 'approved' | 'declined' | 'blocked'
  ADD COLUMN IF NOT EXISTS onboarding_responses jsonb DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS onboarding_started_at timestamptz,
  ADD COLUMN IF NOT EXISTS onboarding_completed_at timestamptz,
  ADD COLUMN IF NOT EXISTS approved_role text,         -- 'client' | 'prospect' | 'counsel' | 'counterparty' | 'partner'
  ADD COLUMN IF NOT EXISTS approved_by text,            -- jonathan
  ADD COLUMN IF NOT EXISTS approved_scope_case text,    -- e.g., 'MWK-001' if scoped
  ADD COLUMN IF NOT EXISTS pending_approval_msg_id integer;

-- Operator Jonathan: mark as approved (already authorized)
UPDATE channel_users
   SET onboarding_state = 'approved',
       approved_role = 'operator',
       approved_by = 'system_seed',
       approved_scope_case = NULL,
       onboarding_completed_at = now()
 WHERE mapped_operator = 'jonathan';

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_chu_onboarding_state ON channel_users(onboarding_state);
CREATE INDEX IF NOT EXISTS idx_chu_pending_approval ON channel_users(onboarding_state) WHERE onboarding_state = 'awaiting_jonathan_approval';
"""


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    print("  → applying onboarding schema …")
    cur.execute(SQL)
    cur.execute("SELECT onboarding_state, count(*) FROM channel_users GROUP BY onboarding_state")
    print("  channel_users by state:")
    for state, n in cur.fetchall():
        print(f"    {state}: {n}")
    cur.close(); conn.close()
    print("  ✓ deploy_116 schema complete")


if __name__ == "__main__":
    main()
