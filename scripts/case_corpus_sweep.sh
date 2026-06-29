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

# 4) KNOWLEDGE + STRATEGY refresh — close the ingest->knowledge->strategy lockstep gap.
#    Newly-ingested docs land in the DIGITAL corpus (documents); without this they stay invisible to
#    the KNOWLEDGE layer (matter_facts) and the strategy engine reasons on stale inputs. This promotes
#    structured facts from the new docs, then re-aims the campaign board — so the war room reflects the
#    latest evidence every cycle. $0 (regex harvest + pure-rules engines; no LLM).
python3 scripts/harvest_facts.py --all --go 2>&1 | tail -2 || true            # docs -> matter_facts (grounded)
python3 scripts/strategy_engine.py --seed --go 2>&1 | tail -2 || true         # north-star + leverage + keystones
python3 scripts/play_engine.py --generate-all --go 2>&1 | tail -2 || true     # offensive war-room queue
echo "[sweep] done $(date -u +%FT%TZ)"
