#!/usr/bin/env python3
"""Deploy 111+112 schema migration.

Adds:
  - documents.execution_status / .execution_metadata (already exist — backfill ready)
  - matters.{current_stage,next_event,next_deadline,next_event_owner,stage_updated_at}
  - case_stage_transitions table
  - truth_negotiations table (audit trail for every verification pass)
  - firm_goals table (Landtek-level agenda)
  - proposed_actions table (goal_accelerator output)
  - deadline_alerts table (sentinel audit trail)
  - case_deadlines.reminder_t14_sent_at (extend ladder)
  - Indexes for hot-paths

Idempotent. Safe to re-run.
"""
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SQL = r"""
-- ============================================================
-- A. matters: case-stage tracking
-- ============================================================
ALTER TABLE matters
  ADD COLUMN IF NOT EXISTS current_stage    text,
  ADD COLUMN IF NOT EXISTS next_event       text,
  ADD COLUMN IF NOT EXISTS next_deadline    date,
  ADD COLUMN IF NOT EXISTS next_event_owner text,
  ADD COLUMN IF NOT EXISTS stage_updated_at timestamptz DEFAULT now(),
  ADD COLUMN IF NOT EXISTS stage_notes      text;

CREATE TABLE IF NOT EXISTS case_stage_transitions (
  id                serial PRIMARY KEY,
  matter_code       text NOT NULL REFERENCES matters(matter_code),
  case_file         text,
  from_stage        text,
  to_stage          text NOT NULL,
  transition_doc_id integer REFERENCES documents(id) ON DELETE SET NULL,
  transitioned_at   timestamptz DEFAULT now(),
  notes             text,
  confidence        real DEFAULT 1.0,
  detected_by       text DEFAULT 'manual'  -- 'classifier' | 'manual' | 'system'
);
CREATE INDEX IF NOT EXISTS idx_stage_trans_matter ON case_stage_transitions(matter_code, transitioned_at DESC);

-- ============================================================
-- B. truth_negotiations: every verification pass
-- ============================================================
CREATE TABLE IF NOT EXISTS truth_negotiations (
  id              serial PRIMARY KEY,
  claim_text      text NOT NULL,
  claim_hash      text,
  atom_text       text,
  case_file       text,
  asked_by        text,  -- 'workflow' | 'cli' | 'slash' | 'system'
  verdict         text,  -- 'verified' | 'uncertain' | 'refuted' | 'unsourced' | 'uncitable_draft'
  evidence_doc_ids integer[],
  evidence_quotes  jsonb,
  challenger_disagrees boolean,
  challenger_reason    text,
  citation_tag    text,  -- e.g. [V·N 614]
  execution_statuses jsonb,  -- {614:'executed_notarized',423:'executed_filed'}
  created_at      timestamptz DEFAULT now(),
  duration_ms     integer
);
CREATE INDEX IF NOT EXISTS idx_truth_case_created ON truth_negotiations(case_file, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_truth_verdict ON truth_negotiations(verdict);

-- ============================================================
-- C. firm_goals: Landtek-level agenda
-- ============================================================
CREATE TABLE IF NOT EXISTS firm_goals (
  id            serial PRIMARY KEY,
  goal_text     text NOT NULL,
  goal_category text,         -- 'market' | 'capability' | 'reputation' | 'flagship_case' | 'product'
  priority      text DEFAULT 'medium',  -- 'critical' | 'high' | 'medium' | 'low'
  status        text DEFAULT 'active',  -- 'active' | 'achieved' | 'on_hold' | 'abandoned'
  progress_pct  integer DEFAULT 0,
  target_date   date,
  owner         text DEFAULT 'jonathan',
  notes         text,
  created_at    timestamptz DEFAULT now(),
  updated_at    timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_firm_goals_status ON firm_goals(status, priority);

-- ============================================================
-- D. proposed_actions: goal_accelerator output
-- ============================================================
CREATE TABLE IF NOT EXISTS proposed_actions (
  id              serial PRIMARY KEY,
  case_file       text,
  firm_goal_id    integer REFERENCES firm_goals(id) ON DELETE SET NULL,
  client_goal_id  integer REFERENCES client_goals(id) ON DELETE SET NULL,
  action_text     text NOT NULL,
  rationale       text,        -- why this action accelerates the goal
  impact_score    real,        -- 0..1, accelerator-estimated impact
  evidence_doc_ids integer[],  -- backing documents
  truth_negotiation_id integer REFERENCES truth_negotiations(id),
  status          text DEFAULT 'proposed',  -- 'proposed' | 'accepted' | 'declined' | 'done' | 'expired'
  proposed_at     timestamptz DEFAULT now(),
  decided_at      timestamptz,
  decided_by      text,
  outcome_notes   text,
  expires_at      timestamptz DEFAULT (now() + interval '7 days')
);
CREATE INDEX IF NOT EXISTS idx_proposed_status ON proposed_actions(status, proposed_at DESC);
CREATE INDEX IF NOT EXISTS idx_proposed_case ON proposed_actions(case_file, status);

-- ============================================================
-- E. deadline_alerts: sentinel audit trail
-- ============================================================
CREATE TABLE IF NOT EXISTS deadline_alerts (
  id            serial PRIMARY KEY,
  deadline_id   integer REFERENCES case_deadlines(id) ON DELETE CASCADE,
  tier          text NOT NULL,  -- 't14' | 't7' | 't3' | 't1' | 't0' | 'overdue'
  sent_at       timestamptz DEFAULT now(),
  channel       text DEFAULT 'telegram',
  message_text  text,
  delivery_ok   boolean
);
CREATE INDEX IF NOT EXISTS idx_dalerts_deadline ON deadline_alerts(deadline_id, tier);

ALTER TABLE case_deadlines
  ADD COLUMN IF NOT EXISTS reminder_t14_sent_at timestamptz,
  ADD COLUMN IF NOT EXISTS reminder_t0_sent_at  timestamptz;

-- ============================================================
-- F. Backfill: matters.case_file (link by clients.case_file) ; needed for joins
-- ============================================================
ALTER TABLE matters ADD COLUMN IF NOT EXISTS case_file text;

UPDATE matters m
   SET case_file = c.case_file
  FROM clients c
 WHERE m.client_code = c.client_code
   AND (m.case_file IS NULL OR m.case_file='');
"""

def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    print("  → applying schema migration …")
    cur.execute(SQL)
    # verify
    checks = [
        ("matters.current_stage", "SELECT 1 FROM information_schema.columns WHERE table_name='matters' AND column_name='current_stage'"),
        ("case_stage_transitions", "SELECT 1 FROM information_schema.tables WHERE table_name='case_stage_transitions'"),
        ("truth_negotiations", "SELECT 1 FROM information_schema.tables WHERE table_name='truth_negotiations'"),
        ("firm_goals", "SELECT 1 FROM information_schema.tables WHERE table_name='firm_goals'"),
        ("proposed_actions", "SELECT 1 FROM information_schema.tables WHERE table_name='proposed_actions'"),
        ("deadline_alerts", "SELECT 1 FROM information_schema.tables WHERE table_name='deadline_alerts'"),
        ("case_deadlines.reminder_t14_sent_at", "SELECT 1 FROM information_schema.columns WHERE table_name='case_deadlines' AND column_name='reminder_t14_sent_at'"),
    ]
    for label, q in checks:
        cur.execute(q)
        ok = cur.fetchone() is not None
        print(f"    {'✓' if ok else '✗'} {label}")
    cur.close(); conn.close()
    print("  ✓ schema migration complete")

if __name__ == "__main__":
    main()
