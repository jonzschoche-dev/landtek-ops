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

# 3) refresh the per-matter case-file snapshots (the view is live; these are the readable copies)
python3 scripts/case_file.py --all || true
echo "[sweep] done $(date -u +%FT%TZ)"
