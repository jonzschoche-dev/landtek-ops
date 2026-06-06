#!/usr/bin/env python3
"""Deploy 207 — `holes/` package schema.

Companion to the `holes/` Python package. Creates two tables that every gap-finding
routine writes to:

  holes_findings — one row per OPEN hole. Idempotent via finding_id_hash partial
                   unique index (status='open'), so re-running a routine that
                   re-discovers the same hole doesn't create dupes.

  holes_runs     — one row per routine invocation. Run history for trendlines,
                   regression detection, and the daily digest.

Severities: P0 (immediate Telegram push) | P1 | P2 | P3 | info
Hole types: truth_gap | evidence_gap | coverage_gap | discipline_drift |
            schema_drift | capacity_gap | coordination_gap | memory_drift

See holes/README.md for the full design.
"""
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SQL = r"""
-- One row per OPEN hole. Routines emit findings; the digest reads them.
CREATE TABLE IF NOT EXISTS holes_findings (
  id                serial PRIMARY KEY,
  routine_name      text NOT NULL,           -- e.g. 'A2_self_research'
  routine_version   text NOT NULL DEFAULT 'v1',
  finding_id_hash   text NOT NULL,           -- stable hash of routine + key fields
  severity          text NOT NULL,           -- 'P0','P1','P2','P3','info'
  hole_type         text NOT NULL,           -- truth_gap, evidence_gap, ...
  case_file         text,
  matter_code       text,
  doc_id            integer,
  description       text NOT NULL,
  suggested_fix     text,
  fix_sql           text,                    -- auto-remediation, if SQL
  fix_command       text,                    -- auto-remediation, if shell
  auto_remediable   boolean DEFAULT false,
  metadata          jsonb DEFAULT '{}'::jsonb,
  status            text NOT NULL DEFAULT 'open',  -- open | remediated | dismissed | expired
  remediated_at     timestamptz,
  remediated_via    text,                    -- 'auto' or 'manual'
  remediated_by     text,                    -- routine name or user
  dismissed_at      timestamptz,
  dismissed_reason  text,
  created_at        timestamptz DEFAULT now()
);

-- Partial unique index: prevent duplicate OPEN findings for the same hole.
-- A re-emit when status='open' is a no-op; once remediated/dismissed, future emits create new rows.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_holes_open_hash
  ON holes_findings(finding_id_hash) WHERE status = 'open';

CREATE INDEX IF NOT EXISTS idx_holes_status ON holes_findings(status, severity, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_holes_routine ON holes_findings(routine_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_holes_case ON holes_findings(case_file) WHERE status='open';

-- Per-routine run history. One row per invocation.
CREATE TABLE IF NOT EXISTS holes_runs (
  id                serial PRIMARY KEY,
  routine_name      text NOT NULL,
  routine_version   text NOT NULL DEFAULT 'v1',
  status            text NOT NULL,           -- 'ok','degraded','failed'
  duration_ms       integer,
  findings_count    integer DEFAULT 0,
  p0_count          integer DEFAULT 0,
  metadata          jsonb DEFAULT '{}'::jsonb,
  error_message     text,
  run_at            timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_holes_runs_routine ON holes_runs(routine_name, run_at DESC);
"""


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SQL)
    cur.execute("SELECT count(*) FROM holes_findings WHERE status='open'")
    n_open = cur.fetchone()[0]
    print(f"  ✓ holes schema applied · {n_open} open holes currently tracked")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
