#!/usr/bin/env bash
# deploy_135.sh — operational logging + tracking tables (inferred schemas)
# Adds the 4 still-missing tables from the audit: escalations_log, phase_log,
# cooldown_log, service_recoveries. Idempotent — safe to re-run when a proper
# spec lands. Schemas inferred from session context — replace with authoritative
# spec when available.

set -euo pipefail
DEPLOY="135"
echo "=== deploy_${DEPLOY} starting at $(date -u +%FT%TZ) ==="

cat > /tmp/deploy_135.sql <<'SQL'
-- ──────────────────────────────────────────────────────────────────────
-- escalations_log: human-decision audit trail (threshold flips, manual
-- interventions, off-protocol decisions Claude or Leo had to make).
-- Concrete usage Jonathan provided:
--   INSERT INTO escalations_log (trigger_type, detail) VALUES (...)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS escalations_log (
  id            SERIAL PRIMARY KEY,
  trigger_type  TEXT NOT NULL,           -- 'threshold_lowered', 'manual_quarantine', etc.
  detail        TEXT NOT NULL,
  decided_by    TEXT,                    -- 'claude' | 'jonathan' | 'leo' | 'system'
  resolved_at   TIMESTAMPTZ,             -- when the escalation was closed
  created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_escalations_type    ON escalations_log(trigger_type);
CREATE INDEX IF NOT EXISTS idx_escalations_created ON escalations_log(created_at DESC);

-- ──────────────────────────────────────────────────────────────────────
-- phase_log: pipeline-state snapshots. Captures queue/chunk/key counters
-- at chosen moments so progress over time is queryable.
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS phase_log (
  id              SERIAL PRIMARY KEY,
  snapshotted_at  TIMESTAMPTZ DEFAULT now(),
  phase           TEXT,                  -- e.g. 'extraction', 'verification', 'evidence_pack'
  queue_state     JSONB,                 -- {queued, completed, failed, requires_heightened_ocr}
  chunk_state     JSONB,                 -- {verified, inferred_strong, total}
  key_state       JSONB,                 -- {primary: ready|cooled, fallback: ...}
  notes           TEXT
);
CREATE INDEX IF NOT EXISTS idx_phase_log_at    ON phase_log(snapshotted_at DESC);
CREATE INDEX IF NOT EXISTS idx_phase_log_phase ON phase_log(phase);

-- ──────────────────────────────────────────────────────────────────────
-- cooldown_log: history of Gemini key cooldowns. gemini_key_state holds
-- current state; this table holds the historical timeline.
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cooldown_log (
  id               SERIAL PRIMARY KEY,
  key_label        TEXT NOT NULL,        -- 'GEMINI_API_KEY', 'GEMINI_API_KEY_FALLBACK'
  cooled_at        TIMESTAMPTZ DEFAULT now(),
  cooled_until     TIMESTAMPTZ,
  reason           TEXT,                 -- '429 quota', '403 PERMISSION_DENIED', 'manual'
  recovered_at     TIMESTAMPTZ,          -- null if not yet recovered
  recovery_method  TEXT                  -- 'natural', 'manual_clear', 'key_replaced'
);
CREATE INDEX IF NOT EXISTS idx_cooldown_key    ON cooldown_log(key_label);
CREATE INDEX IF NOT EXISTS idx_cooldown_cooled ON cooldown_log(cooled_at DESC);

-- ──────────────────────────────────────────────────────────────────────
-- service_recoveries: systemd service failure → recovery events.
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS service_recoveries (
  id               SERIAL PRIMARY KEY,
  service_name     TEXT NOT NULL,        -- 'sweep-loop.service', 'landtek-orchestrator.service', 'n8n-n8n-1'
  failed_at        TIMESTAMPTZ,
  recovered_at     TIMESTAMPTZ DEFAULT now(),
  failure_reason   TEXT,
  recovery_action  TEXT                  -- 'systemctl restart', 'docker restart', 'manual fix + restart'
);
CREATE INDEX IF NOT EXISTS idx_svcrec_service   ON service_recoveries(service_name);
CREATE INDEX IF NOT EXISTS idx_svcrec_recovered ON service_recoveries(recovered_at DESC);

-- ──────────────────────────────────────────────────────────────────────
-- Seed: backfill the escalations_log + cooldown_log + service_recoveries
-- with the events we've actually observed this session, so the tables
-- aren't empty on first use.
-- ──────────────────────────────────────────────────────────────────────
INSERT INTO escalations_log (trigger_type, detail, decided_by, resolved_at) VALUES
  ('threshold_investigated',
   'QUALITY_THRESHOLD considered 0.8→0.6 on 2026-05-12; reverted after discriminator showed 0.8 reachable (doc 10 hit 1.000). Kept at 0.8.',
   'claude', now())
ON CONFLICT DO NOTHING;

INSERT INTO cooldown_log (key_label, cooled_at, cooled_until, reason, recovered_at, recovery_method) VALUES
  ('GEMINI_API_KEY',          '2026-05-12 07:24:02+00', '2026-05-12 11:24:02+00',
   '429 quota — initial daily-free-tier exhaustion', '2026-05-12 11:24:00+00', 'natural'),
  ('GEMINI_API_KEY_FALLBACK', '2026-05-12 08:15:07+00', '2026-05-13 08:15:07+00',
   '403 SERVICE_DISABLED on project 790571313389 (Gemini API not enabled)',
   '2026-05-12 11:51:00+00', 'key_replaced')
ON CONFLICT DO NOTHING;

INSERT INTO service_recoveries (service_name, failed_at, recovered_at, failure_reason, recovery_action) VALUES
  ('landtek-orchestrator.service', '2026-05-12 06:23:53+00', '2026-05-12 06:36:07+00',
   'psycopg2.errors.UndefinedColumn: column "verified_by" of relation "extraction_chunks" does not exist',
   'ALTER TABLE extraction_chunks ADD COLUMN verified_by/verified_at; service ran clean after'),
  ('sweep-loop.service',         '2026-05-12 10:30:00+00', '2026-05-12 10:34:35+00',
   'multiple processes contending; manual SIGKILL of stale workers',
   'pkill stragglers + systemctl restart sweep-loop.service'),
  ('n8n-n8n-1',                 NULL, '2026-05-12 12:25:34+00',
   'no failure — graceful restart for workflow node injection (deploy_134)',
   'docker restart n8n-n8n-1')
ON CONFLICT DO NOTHING;

-- A starter phase_log snapshot reflecting current state at deploy time.
INSERT INTO phase_log (phase, queue_state, chunk_state, key_state, notes)
SELECT
  'extraction',
  jsonb_build_object(
    'queued',                  (SELECT COUNT(*) FROM heightened_ocr_queue WHERE case_file='MWK-001' AND status='queued'),
    'completed',               (SELECT COUNT(*) FROM heightened_ocr_queue WHERE case_file='MWK-001' AND status='completed'),
    'failed',                  (SELECT COUNT(*) FROM heightened_ocr_queue WHERE case_file='MWK-001' AND status='failed'),
    'requires_heightened_ocr', (SELECT COUNT(*) FROM heightened_ocr_queue WHERE case_file='MWK-001' AND status='requires_heightened_ocr')
  ),
  jsonb_build_object(
    'verified',                (SELECT COUNT(*) FROM extraction_chunks WHERE provenance_level='verified'),
    'inferred_strong',         (SELECT COUNT(*) FROM extraction_chunks WHERE provenance_level='inferred_strong'),
    'total',                   (SELECT COUNT(*) FROM extraction_chunks)
  ),
  (SELECT jsonb_object_agg(key_label,
                           CASE WHEN cooldown_until > NOW() THEN 'cooled'
                                ELSE 'READY' END)
     FROM gemini_key_state),
  'Initial snapshot at deploy_135 (2026-05-12 12:30 UTC). Tables created from inferred schemas.';

\echo === all 4 tables now present ===
SELECT
  to_regclass('public.escalations_log') AS escalations_log,
  to_regclass('public.phase_log')       AS phase_log,
  to_regclass('public.cooldown_log')    AS cooldown_log,
  to_regclass('public.service_recoveries') AS service_recoveries;

\echo === seed counts ===
SELECT (SELECT COUNT(*) FROM escalations_log)   AS escalations,
       (SELECT COUNT(*) FROM phase_log)         AS phase_snapshots,
       (SELECT COUNT(*) FROM cooldown_log)      AS cooldowns,
       (SELECT COUNT(*) FROM service_recoveries) AS recoveries;

\echo === latest phase snapshot ===
SELECT id, snapshotted_at, phase, queue_state, key_state FROM phase_log ORDER BY id DESC LIMIT 1;
SQL

docker cp /tmp/deploy_135.sql n8n-postgres-1:/tmp/deploy_135.sql
docker exec n8n-postgres-1 psql -U n8n -d n8n -f /tmp/deploy_135.sql

cd /root/landtek
git add -A
git commit -m "deploy_${DEPLOY}: escalations_log + phase_log + cooldown_log + service_recoveries (inferred schemas; backfilled with session-observed events)" || true

echo
echo "=== deploy_${DEPLOY} complete ==="
echo
echo "Note: schemas inferred from session context only. When the authoritative"
echo "spec lands (e.g. 7-day directive §11 for phase_log), redeploy idempotently."
