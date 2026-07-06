#!/usr/bin/env bash
# case_corpus_sweep.sh — keep every matter's case file COMPLETE + CURRENT.
# Runs on a timer: recover referenced-but-unheld records from the live sources (+OCR),
# self-dedup any duplicate matter-links the sweep may create, then refresh the per-matter
# case-file snapshots. The case_timeline VIEW is always-current on its own; this keeps the
# DATA behind it complete. $0 (live Gmail + Tesseract + local).
set -euo pipefail
set -a; . /root/landtek/.env 2>/dev/null || true; set +a
cd /root/landtek

# 1) recover new / missing records across the agency surface (idempotent: dedups by content)
python3 scripts/find_missing_record.py --backfill --apply 2>&1 | tail -3 || true

# 2) self-heal: remove any duplicate (doc_id, matter_code) link rows
docker exec -i n8n-postgres-1 psql -U n8n -d n8n -c \
  "DELETE FROM document_matter_links a USING document_matter_links b WHERE a.ctid > b.ctid AND a.doc_id=b.doc_id AND a.matter_code=b.matter_code;" || true

# 2b) enforce the 1319 <-> 1321 separation invariant (operator directive 2026-06-29):
# a doc whose OWN text names only the OTHER ARTA docket must never be linked to this matter
# (docket-exact guard — undoes any re-conflation the sweep's re-linking could introduce)
docker exec -i n8n-postgres-1 psql -U n8n -d n8n <<'EOSQL' || true
DELETE FROM document_matter_links l WHERE l.matter_code='MWK-ARTA-1319'
  AND EXISTS (SELECT 1 FROM documents d WHERE d.id=l.doc_id
    AND coalesce(d.original_filename,'')||coalesce(left(d.extracted_text,5000),'') ~* '0209-1321'
    AND coalesce(d.original_filename,'')||coalesce(left(d.extracted_text,5000),'') !~* '0209-1319');
DELETE FROM document_matter_links l WHERE l.matter_code='MWK-ARTA-1321'
  AND EXISTS (SELECT 1 FROM documents d WHERE d.id=l.doc_id
    AND coalesce(d.original_filename,'')||coalesce(left(d.extracted_text,5000),'') ~* '0209-1319'
    AND coalesce(d.original_filename,'')||coalesce(left(d.extracted_text,5000),'') !~* '0209-1321');
EOSQL

# 3) refresh the per-matter case-file snapshots (the view is live; these are the readable copies)
python3 scripts/case_file.py --all || true

# 3.5) CONNECT — bring every newly-ingested doc up to the connect-verify signals (deploy_712 gate).
#      Re-score OCR quality, stamp engine-provenance from the doc's OWN extraction_runs record
#      (truthful — never fabricated), and type the doc from its existing classification (deterministic
#      map). The other two gate signals are owned elsewhere: text by ingest/re-OCR, embedding Mac-side
#      by com.landtek.embed (fastembed, $0 — the 1GB VPS can't hold the model). So each sweep closes the
#      three VPS-derivable signals and a new doc self-connects instead of landing half-wired.
#      All $0, deterministic, idempotent.
python3 scripts/ocr_quality.py --scan --go 2>&1 | tail -1 || true             # signal: ocr_quality (re-score)
docker exec -i n8n-postgres-1 psql -U n8n -d n8n <<'EOSQL' || true
-- signal: provenance (model_used) <- latest COMPLETED extraction_runs.model (honest source; never invented)
WITH latest AS (
  SELECT DISTINCT ON (doc_id) doc_id, model FROM extraction_runs
  WHERE status='completed' AND coalesce(model,'')<>'' ORDER BY doc_id, completed_at DESC NULLS LAST)
UPDATE documents d SET model_used = latest.model FROM latest
  WHERE latest.doc_id=d.id AND coalesce(d.model_used,'')='';
-- signal: document_type <- classification (deterministic map; only fills blanks, never overwrites)
UPDATE documents SET document_type = CASE
    WHEN lower(classification) LIKE 'title%'                                          THEN 'TCT'
    WHEN lower(classification) = 'deed'                                               THEN 'Deed'
    WHEN lower(classification) LIKE '%power of attorney'                              THEN 'SPA'
    WHEN lower(classification) LIKE '%affidavit%'                                     THEN 'Affidavit'
    WHEN lower(classification) IN ('resolution','order','decision')                  THEN 'Court Order'
    WHEN lower(classification) IN ('complaint','motion','reply','petition','court filing') THEN 'Court Filing'
    WHEN lower(classification) = 'tax document'                                       THEN 'Tax Document'
    WHEN lower(classification) IN ('letter','correspondence','demand letter','email','notice','memorandum') THEN 'Correspondence'
    WHEN lower(classification) = 'receipt'                                            THEN 'Receipt'
    WHEN lower(classification) = 'contract'                                           THEN 'Contract'
    WHEN lower(classification) = 'government submission'                              THEN 'Government Submission'
    ELSE document_type END
  WHERE (document_type IS NULL OR document_type='') AND classification IS NOT NULL;
EOSQL

# 4) KNOWLEDGE + STRATEGY refresh — close the ingest->knowledge->strategy lockstep gap.
#    Newly-ingested docs land in the DIGITAL corpus (documents); without this they stay invisible to
#    the KNOWLEDGE layer (matter_facts) and the strategy engine reasons on stale inputs. This promotes
#    structured facts from the new docs, then re-aims the campaign board — so the war room reflects the
#    latest evidence every cycle. $0 (regex harvest + pure-rules engines; no LLM).
python3 scripts/harvest_facts.py --all --go 2>&1 | tail -2 || true            # docs -> matter_facts (grounded)
python3 scripts/strategy_engine.py --seed --go 2>&1 | tail -2 || true         # north-star + leverage + keystones
python3 scripts/play_engine.py --generate-all --go 2>&1 | tail -2 || true     # offensive war-room queue

# 5) ACCESSIBILITY — is the freshened corpus actually REACHABLE across every issue?
#    "up to date" is only half the ask; the other half is that no matter goes dark. This scores
#    system-wide awareness (what we SHOULD know vs. what we actually know as grounded facts),
#    NAMES the biggest cluelessness gaps, and logs the number to awareness_log so every sweep must
#    visibly move it — a matter whose corpus is unreachable shows up here as a gap, not a silent hole.
#    Pure SQL, creditless. The per-matter readable snapshots (step 3) are the reachable surface itself.
echo "[sweep] accessibility scorecard (cross-matter):"
python3 scripts/knowledge_coverage.py --log 2>&1 | grep -E 'OVERALL AWARENESS|•' || true

echo "[sweep] done $(date -u +%FT%TZ)"
