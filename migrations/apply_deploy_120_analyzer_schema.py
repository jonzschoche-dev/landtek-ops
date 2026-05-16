#!/usr/bin/env python3
"""Deploy 120 — Systems analyzer + back-test schema."""
import psycopg2
DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SQL = r"""
-- Heartbeat: each cron job emits a row on every run
CREATE TABLE IF NOT EXISTS system_heartbeat (
  id           serial PRIMARY KEY,
  source       text NOT NULL,         -- 'gmail-watcher','drive-sync','deadline-sentinel','goal-accelerator','systems-analyzer'
  status       text NOT NULL,         -- 'ok','degraded','failed'
  duration_ms  integer,
  metadata     jsonb,
  emitted_at   timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_heartbeat_source ON system_heartbeat(source, emitted_at DESC);

-- Analyzer findings
CREATE TABLE IF NOT EXISTS system_analyzer_findings (
  id           serial PRIMARY KEY,
  finding_type text NOT NULL,         -- 'staleness','coverage_gap','verification_drift','integrity','remediation_proposed'
  severity     text NOT NULL,         -- 'critical','high','medium','low','info'
  source_area  text,                  -- which subsystem
  description  text NOT NULL,
  suggested_fix text,
  auto_remediable boolean DEFAULT false,
  remediated_at timestamptz,
  remediated_via text,
  created_at   timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_findings_severity ON system_analyzer_findings(severity, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_findings_open ON system_analyzer_findings(remediated_at) WHERE remediated_at IS NULL;

-- Back-test suite
CREATE TABLE IF NOT EXISTS back_test_suite (
  id              serial PRIMARY KEY,
  test_name       text UNIQUE NOT NULL,
  claim           text NOT NULL,
  case_file       text,
  expected_verdict text NOT NULL,    -- 'verified','refuted','uncertain','unsourced','uncitable_draft'
  expected_doc_ids integer[],         -- docs that MUST appear in fact_backers
  expected_contains_quote text,       -- challenger response should mention this
  notes           text,
  active          boolean DEFAULT true,
  created_at      timestamptz DEFAULT now()
);

-- Back-test runs (history of every test)
CREATE TABLE IF NOT EXISTS back_test_runs (
  id              serial PRIMARY KEY,
  test_id         integer REFERENCES back_test_suite(id) ON DELETE CASCADE,
  passed          boolean NOT NULL,
  actual_verdict  text,
  actual_doc_ids  integer[],
  challenger_reason text,
  failure_reason  text,
  run_at          timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_btruns_test ON back_test_runs(test_id, run_at DESC);

-- Seed initial back-test cases
INSERT INTO back_test_suite (test_name, claim, case_file, expected_verdict, expected_doc_ids, expected_contains_quote, notes)
VALUES
  ('cesar-is-dead', 'Cesar M. de la Fuente is dead', 'MWK-001', 'verified',
   ARRAY[407], 'Patay na po',
   'Salvador''s judicial affidavit doc#407 is the smoking gun in Filipino'),

  ('cesar-died-pre-2019', 'Cesar de la Fuente died before September 2019', 'MWK-001', 'refuted',
   NULL, '2016',
   'Doc#444 shows him executing a 2016 deed; pre-2019 death not supported'),

  ('case-26360-pretrial', 'Civil Case 26-360 is at the pretrial pending stage', 'MWK-001', 'verified',
   ARRAY[392], 'Notice of Pre-trial',
   'Doc#392 is the Notice of Pre-trial Conference'),

  ('arta-admin-only', 'ARTA Case CTN SL-2025-1021-0747 charges Mayor Pajarillo with R.A. 11032 violations only', 'MWK-001', 'verified',
   ARRAY[384], 'R.A. 11032',
   'Doc#384 is the Complaint-Affidavit'),

  ('t52540-cancelled-via-cesar-deed', 'T-52540 was cancelled in 2021 via a Deed of Sale executed by Cesar de la Fuente in September 2019', 'MWK-001', 'verified',
   ARRAY[233, 441], 'September',
   'Multiple docs cite the 2016/2019 deed-of-sale chain')
ON CONFLICT (test_name) DO NOTHING;
"""

def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SQL)
    cur.execute("SELECT count(*) FROM back_test_suite WHERE active")
    n = cur.fetchone()[0]
    print(f"  ✓ schema applied · {n} back-test cases seeded")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
