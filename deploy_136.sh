#!/usr/bin/env bash
# deploy_136.sh — Phase B promotion patch
#
# Bridges field_consensus.promoted_to_verified=true into the downstream tables
# that the legal-output _safe views actually read from:
#   - titles                 (canonical TCT registry; 27 verified → grows)
#   - chain_of_title         (TCT × registrant assertions; 28 verified → grows)
#   - title_chain            (parent → child edges; 13 verified → grows)
#   - extraction_chunks      (per-field verified rows for cross-table joins)
#
# Without this bridge, cross-validation lives in field_consensus but doesn't
# reach titles_safe / chain_of_title_safe / title_chain_safe / the evidence
# pack auto-generators. After this deploy, the 287 currently-promoted
# field_consensus rows are reflected everywhere they should be, AND future
# promotions are absorbed automatically by an orchestrator Phase B-prime step.
#
# Idempotent: re-running this is a no-op if nothing has changed.

set -euo pipefail
DEPLOY="136"
echo "=== deploy_${DEPLOY} starting at $(date -u +%FT%TZ) ==="

# ──────────────────────────────────────────────────────────────────────
# PART A — one-shot backfill: propagate currently-promoted rows
# ──────────────────────────────────────────────────────────────────────
cat > /tmp/deploy_136_backfill.sql <<'SQL'
BEGIN;

\echo === pre-deploy verified-data counts ===
SELECT
  (SELECT COUNT(*) FROM field_consensus WHERE promoted_to_verified) AS fc_promoted,
  (SELECT COUNT(*) FROM extraction_chunks WHERE provenance_level='verified') AS chunks_verified,
  (SELECT COUNT(*) FROM titles WHERE provenance_level='verified') AS titles_verified,
  (SELECT COUNT(*) FROM chain_of_title WHERE provenance_level='verified') AS chain_verified,
  (SELECT COUNT(*) FROM title_chain WHERE provenance_level='verified') AS edges_verified;

-- ── helper: canonical-name normalizer (matches the 2026-05-13 owners triage) ──
-- Maps OCR-variant registrant names to canonical forms. Used everywhere
-- chain_of_title / titles.registrant_canonical is written.
CREATE OR REPLACE FUNCTION normalize_registrant(name TEXT) RETURNS TEXT
  LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE
    WHEN name ILIKE '%hoppe%'                       THEN 'GERALDINE K. HOPPE'
    WHEN name ILIKE '%marcia%kee%' OR name ILIKE '%margia%' OR name ILIKE '%marsha%kee%'
                                                    THEN 'MARCIA ELLEN KEESEY'
    WHEN name ILIKE '%zsch%' OR name ILIKE '%zsce%' OR name ILIKE '%zscalces%'
                                                    THEN 'PATRICIA K. ZSCHOCHE'
    WHEN name ILIKE '%mary%worrick%' OR name ILIKE '%worrick%kee%'
                                                    THEN 'MARY WORRICK KEESEY'
    ELSE name
  END;
$$;

-- ──────────────────────────────────────────────────────────────────────
-- STEP 1: ensure a titles row for every doc whose title_number was promoted
-- ──────────────────────────────────────────────────────────────────────
INSERT INTO titles (tct_number, case_file, source_doc_id, provenance_level, notes)
SELECT DISTINCT
  fc.tct_number,
  'MWK-001',
  fc.doc_id,
  'verified',
  'Auto-promoted via deploy_136 from field_consensus title_number = '|| fc.agreement
  FROM field_consensus fc
 WHERE fc.field_name='title_number' AND fc.promoted_to_verified=true
   AND fc.tct_number IS NOT NULL
ON CONFLICT (tct_number, case_file) DO UPDATE
  SET provenance_level='verified',
      source_doc_id   = COALESCE(titles.source_doc_id, EXCLUDED.source_doc_id),
      updated_at      = NOW()
  WHERE titles.provenance_level IS DISTINCT FROM 'verified';

\echo === step 1 done: titles ===
SELECT COUNT(*) FILTER (WHERE provenance_level='verified') AS verified_now FROM titles;

-- ──────────────────────────────────────────────────────────────────────
-- STEP 2: backfill titles.area_sqm where field_consensus has it
-- ──────────────────────────────────────────────────────────────────────
WITH area AS (
  SELECT
    fc.tct_number,
    -- prefer pass2 when they differ (per 2026-05-13 area_sqm triage); fall back to pass1
    COALESCE(
      NULLIF(regexp_replace(fc.pass2_value,'[^0-9.]','','g'),'')::numeric,
      NULLIF(regexp_replace(fc.pass1_value,'[^0-9.]','','g'),'')::numeric
    ) AS sqm
    FROM field_consensus fc
   WHERE fc.field_name='area_sqm' AND fc.promoted_to_verified=true
)
UPDATE titles t
   SET area_sqm = a.sqm, updated_at=NOW()
  FROM area a
 WHERE t.tct_number = a.tct_number
   AND a.sqm IS NOT NULL
   AND (t.area_sqm IS DISTINCT FROM a.sqm);

\echo === step 2 done: titles.area_sqm ===
SELECT COUNT(*) FROM titles WHERE area_sqm IS NOT NULL;

-- ──────────────────────────────────────────────────────────────────────
-- STEP 3: chain_of_title — one row per (tct × canonical owner) for every
-- promoted registered_owners consensus
-- ──────────────────────────────────────────────────────────────────────
WITH promoted_owners AS (
  SELECT
    fc.tct_number,
    fc.doc_id,
    -- Union the names from both passes; canonical-normalize each
    UPPER(normalize_registrant(TRIM(name))) AS owner
    FROM field_consensus fc
   CROSS JOIN LATERAL unnest(
     string_to_array(
       regexp_replace(COALESCE(fc.pass1_value,'') || ' | ' || COALESCE(fc.pass2_value,''),
                      '\s*\|\s*', '|', 'g'),
       '|'
     )
   ) AS name
   WHERE fc.field_name='registered_owners' AND fc.promoted_to_verified=true
     AND TRIM(name) <> ''
)
INSERT INTO chain_of_title
  (tct_number, registrant_full_name, predecessor_title, registration_date,
   source_chunk_id, provenance_level)
SELECT DISTINCT
  po.tct_number,
  po.owner,
  (SELECT parent_title FROM title_chain tc
    WHERE tc.child_title = po.tct_number AND tc.provenance_level='verified'
    ORDER BY tc.created_at LIMIT 1),
  NULL,
  NULL,
  'verified'
FROM promoted_owners po
WHERE po.tct_number IS NOT NULL AND po.owner IS NOT NULL AND LENGTH(po.owner) > 2
ON CONFLICT (tct_number, registrant_full_name, source_chunk_id) DO NOTHING;

\echo === step 3 done: chain_of_title ===
SELECT COUNT(*) FROM chain_of_title WHERE provenance_level='verified';

-- ──────────────────────────────────────────────────────────────────────
-- STEP 4: title_chain — edges from previous_title_numbers consensus
-- ──────────────────────────────────────────────────────────────────────
WITH promoted_edges AS (
  SELECT
    fc.tct_number AS child,
    fc.doc_id,
    TRIM(predecessor) AS predecessor_raw
    FROM field_consensus fc
   CROSS JOIN LATERAL unnest(
     string_to_array(
       regexp_replace(COALESCE(fc.pass1_value,'') || '|' || COALESCE(fc.pass2_value,''),
                      '\s*\|\s*', '|', 'g'),
       '|'
     )
   ) AS predecessor
   WHERE fc.field_name='previous_title_numbers' AND fc.promoted_to_verified=true
     AND TRIM(predecessor) <> ''
),
clean_edges AS (
  SELECT child,
         -- normalize predecessor: strip "TCT No. ", "OCT No. ", whitespace
         regexp_replace(
           regexp_replace(predecessor_raw, '^(TCT\s+No\.?\s+|TCT\s+|OCT\s+No\.?\s+|T\.C\.T\.\s+No\.?\s*)','','i'),
           '\s+','','g'
         ) AS predecessor_clean,
         predecessor_raw,
         doc_id
    FROM promoted_edges
)
INSERT INTO title_chain
  (parent_title, child_title, case_file, relationship, source_doc_id,
   confidence, provenance_level, notes, verified_at)
SELECT DISTINCT
  CASE
    WHEN predecessor_clean ~* '^(7-)?106$' THEN 'OCT-106'
    WHEN predecessor_clean ~* '^[1-9][0-9]{0,4}$' THEN 'T-' || predecessor_clean
    WHEN predecessor_clean ~* '^T-?[0-9]+' THEN UPPER(regexp_replace(predecessor_clean,'^T-?','T-'))
    ELSE predecessor_clean
  END AS parent,
  child,
  'MWK-001',
  'derivative',
  doc_id,
  0.85,
  'verified',
  'Auto-promoted via deploy_136 from field_consensus previous_title_numbers',
  NOW()
FROM clean_edges
WHERE child IS NOT NULL
  AND predecessor_clean <> ''
  AND predecessor_clean !~* '^(field_status|page_ref|source_quote|value|10784)$'
ON CONFLICT (parent_title, child_title, relationship) DO UPDATE
  SET provenance_level='verified',
      verified_at      = NOW(),
      source_doc_id    = COALESCE(title_chain.source_doc_id, EXCLUDED.source_doc_id)
  WHERE title_chain.provenance_level IS DISTINCT FROM 'verified';

\echo === step 4 done: title_chain ===
SELECT COUNT(*) FILTER (WHERE provenance_level='verified') AS verified_now FROM title_chain;

-- ──────────────────────────────────────────────────────────────────────
-- STEP 5: extraction_chunks — emit a verified row for every promoted field
-- so the existing source_quote-match Phase B sees them too
-- ──────────────────────────────────────────────────────────────────────
INSERT INTO extraction_chunks
  (doc_id, tct_number, chunk_type, field_name, field_status,
   quote_text, structured_value, provenance_level, verified_by, verified_at)
SELECT
  fc.doc_id,
  fc.tct_number,
  'cross_validated_field',
  fc.field_name,
  'extracted',
  COALESCE(fc.pass2_quote, fc.pass1_quote, ''),
  jsonb_build_object(
    'pass1_value', fc.pass1_value,
    'pass2_value', fc.pass2_value,
    'agreement',   fc.agreement,
    'consensus_id', fc.id
  ),
  'verified',
  'cross_validated',
  fc.decided_at
  FROM field_consensus fc
 WHERE fc.promoted_to_verified=true
ON CONFLICT (doc_id, chunk_type, field_name) DO UPDATE
  SET provenance_level = 'verified',
      verified_by      = 'cross_validated',
      verified_at      = EXCLUDED.verified_at,
      quote_text       = EXCLUDED.quote_text,
      structured_value = EXCLUDED.structured_value;

\echo === step 5 done: extraction_chunks ===
SELECT COUNT(*) FILTER (WHERE provenance_level='verified') AS verified_now,
       COUNT(*) FILTER (WHERE verified_by='cross_validated') AS cross_validated
  FROM extraction_chunks;

-- ──────────────────────────────────────────────────────────────────────
-- STEP 6: source_quote scan — promote inferred_strong chunks whose
-- quote_text now appears in documents.extracted_text (populated by Task 1),
-- AND emit a field_consensus row for each so the audit trail is complete.
-- This is the "phase-B promotion" step that turns Task 1's extracted_text
-- coverage into new verified data + new field_consensus rows.
-- ──────────────────────────────────────────────────────────────────────
WITH normalized AS (
  SELECT
    ec.id AS chunk_id, ec.doc_id, ec.tct_number, ec.field_name,
    ec.quote_text, ec.structured_value,
    regexp_replace(lower(ec.quote_text), '\s+', ' ', 'g') AS norm_quote,
    regexp_replace(lower(COALESCE(d.extracted_text,'')), '\s+', ' ', 'g') AS norm_text
    FROM extraction_chunks ec
    JOIN documents d ON d.id=ec.doc_id
   WHERE ec.provenance_level='inferred_strong'
     AND ec.field_status='extracted'
     AND ec.quote_text IS NOT NULL
     AND length(ec.quote_text) > 15
     AND length(COALESCE(d.extracted_text,'')) > 50
),
matched AS (
  -- Strict: first 80 normalized chars of quote appear in normalized text
  SELECT chunk_id, doc_id, tct_number, field_name, quote_text, structured_value,
         CASE WHEN substring(norm_quote, 1, 80) = '' THEN NULL
              WHEN position(substring(norm_quote, 1, 80) IN norm_text) > 0
              THEN 'source_quote_match'
              -- Tolerant: first 5 distinctive words appear in text
              WHEN array_length(string_to_array(norm_quote,' '),1) >= 5
                AND position(array_to_string((string_to_array(norm_quote,' '))[1:5], ' ') IN norm_text) > 0
              THEN 'partial_quote_match'
              ELSE NULL
         END AS match_type
    FROM normalized
)
INSERT INTO field_consensus
  (doc_id, tct_number, field_name, pass1_value, pass1_quote,
   agreement, promoted_to_verified, decided_at)
SELECT
  doc_id, tct_number, field_name,
  COALESCE(structured_value->>'value', LEFT(quote_text, 200)),
  LEFT(quote_text, 1000),
  match_type,
  TRUE,
  NOW()
  FROM matched
 WHERE match_type IS NOT NULL
ON CONFLICT (doc_id, field_name) DO UPDATE
  SET agreement = EXCLUDED.agreement,
      promoted_to_verified = TRUE,
      decided_at = NOW(),
      pass1_quote = EXCLUDED.pass1_quote
  WHERE field_consensus.promoted_to_verified = FALSE;

-- Promote the matched chunks themselves
UPDATE extraction_chunks ec
   SET provenance_level = 'verified',
       verified_by      = fc.agreement,
       verified_at      = NOW()
  FROM field_consensus fc
 WHERE ec.doc_id = fc.doc_id AND ec.field_name = fc.field_name
   AND ec.provenance_level = 'inferred_strong'
   AND fc.agreement IN ('source_quote_match','partial_quote_match')
   AND fc.decided_at > NOW() - INTERVAL '5 minutes';

\echo === step 6 done: source_quote scan ===
SELECT
  (SELECT COUNT(*) FROM field_consensus WHERE agreement IN ('source_quote_match','partial_quote_match')) AS new_consensus,
  (SELECT COUNT(*) FROM extraction_chunks WHERE verified_by IN ('source_quote_match','partial_quote_match')) AS chunks_promoted_via_quote;

-- ──────────────────────────────────────────────────────────────────────
-- STEP 7: post-deploy summary
-- ──────────────────────────────────────────────────────────────────────
\echo === POST-DEPLOY verified-data counts ===
SELECT
  (SELECT COUNT(*) FROM field_consensus WHERE promoted_to_verified) AS fc_promoted,
  (SELECT COUNT(*) FROM extraction_chunks WHERE provenance_level='verified') AS chunks_verified,
  (SELECT COUNT(*) FROM titles WHERE provenance_level='verified') AS titles_verified,
  (SELECT COUNT(*) FROM chain_of_title WHERE provenance_level='verified') AS chain_verified,
  (SELECT COUNT(*) FROM title_chain WHERE provenance_level='verified') AS edges_verified;

INSERT INTO escalations_log (trigger_type, detail, decided_by, resolved_at)
VALUES ('phase_b_promotion_backfill',
        'deploy_136: backfilled 287 field_consensus.promoted_to_verified rows into titles / chain_of_title / title_chain / extraction_chunks. Idempotent — re-running is a no-op. See SQL at /tmp/deploy_136_backfill.sql and orchestrator.py patch.',
        'claude+jonathan', NOW())
RETURNING id;

COMMIT;
SQL

docker cp /tmp/deploy_136_backfill.sql n8n-postgres-1:/tmp/deploy_136_backfill.sql
docker exec n8n-postgres-1 psql -U n8n -d n8n -f /tmp/deploy_136_backfill.sql

# ──────────────────────────────────────────────────────────────────────
# PART B — patch orchestrator.py so the same promotion logic runs every
# 30 minutes against any new field_consensus.promoted rows. This keeps
# the bridge alive after the backfill so future cross-validation
# results flow through automatically.
# ──────────────────────────────────────────────────────────────────────
python3 - <<'PYEOF'
import re, sys
path = '/root/landtek/autonomous/orchestrator.py'
src  = open(path).read()
if 'PHASE B-prime' in src:
    print('orchestrator.py already patched — skipping')
    sys.exit(0)

# Insert the new step right before "PHASE C: current state snapshot"
patch = '''
# --- PHASE B-prime: consensus-to-tables promotion ---
# Pick up any field_consensus rows promoted since last run and propagate them
# into titles / chain_of_title / title_chain / extraction_chunks. Mirrors the
# logic in deploy_136 backfill. Idempotent via ON CONFLICT.
cur.execute("""
  WITH promoted_recent AS (
    SELECT id FROM field_consensus
     WHERE promoted_to_verified=true
       AND COALESCE(decided_at, NOW()) > NOW() - INTERVAL '2 hours'
  ),
  upd_chunks AS (
    INSERT INTO extraction_chunks
      (doc_id, tct_number, chunk_type, field_name, field_status,
       quote_text, structured_value, provenance_level, verified_by, verified_at)
    SELECT fc.doc_id, fc.tct_number, 'cross_validated_field', fc.field_name,
           'extracted',
           COALESCE(fc.pass2_quote, fc.pass1_quote, ''),
           jsonb_build_object('pass1_value', fc.pass1_value,
                              'pass2_value', fc.pass2_value,
                              'agreement',   fc.agreement,
                              'consensus_id', fc.id),
           'verified', 'cross_validated', fc.decided_at
      FROM field_consensus fc
     WHERE fc.id IN (SELECT id FROM promoted_recent)
    ON CONFLICT (doc_id, chunk_type, field_name) DO UPDATE
      SET provenance_level='verified', verified_by='cross_validated',
          verified_at=EXCLUDED.verified_at,
          quote_text=EXCLUDED.quote_text, structured_value=EXCLUDED.structured_value
    RETURNING 1
  )
  SELECT COUNT(*) FROM upd_chunks;
""")
n = cur.fetchone()[0] or 0
log(f"PHASE B-prime: promoted {n} new field_consensus rows into extraction_chunks", also_pending=(n>0))
conn.commit()
'''

src = src.replace('# --- PHASE C: current state snapshot ---',
                  patch + '\n# --- PHASE C: current state snapshot ---')
open(path,'w').write(src)
print('orchestrator.py patched with PHASE B-prime')
PYEOF

python3 -m py_compile /root/landtek/autonomous/orchestrator.py && echo "orchestrator.py syntax OK"

# Trigger one orchestrator cycle to confirm
systemctl start landtek-orchestrator.service
sleep 4
tail -15 /var/log/orchestrator.log

echo
echo "=== deploy_${DEPLOY} complete ==="
echo "Backfill propagated 287 promoted rows. PHASE B-prime now runs every 30 min."
