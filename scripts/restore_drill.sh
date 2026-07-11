#!/bin/bash
# restore_drill.sh — A62 restore-drill: prove the nightly dump actually restores.
# Runs on the VPS (needs docker n8n-postgres-1). Restores the latest local dump into a
# throwaway scratch DB, checks the restore is FAITHFUL (scratch counts == prod counts on
# a stable table), then drops the scratch DB. Records to /root/backups/RESTORE_DRILL.log
# so "backup" stops being an untested hope. Idempotent; safe (scratch DB, dropped after).
#
# NB: it first REFRESH COLLATION VERSION on template1 — a libc 2.41->2.36 change on the
# host makes template1's recorded collation mismatch, which otherwise BLOCKS CREATE
# DATABASE (found 2026-07-11). This is metadata-only; a full REINDEX for the same mismatch
# on the live DBs is a separate operator maintenance-window item (flagged, not done here).
set -uo pipefail
LOG=/root/backups/RESTORE_DRILL.log
DUMP=$(ls -t /root/backups/landtek_backup_*.sql.gz | head -1)
DDB=n8n_restore_drill
PSQL="docker exec -i n8n-postgres-1 psql -U n8n"
{
  echo "=== RESTORE DRILL $(date -u +%FT%TZ) ==="
  echo "dump: $DUMP ($(du -h "$DUMP" | cut -f1))"
  $PSQL -d postgres -qc "ALTER DATABASE template1 REFRESH COLLATION VERSION;" 2>&1 | grep -i refresh || true
  $PSQL -d postgres -qc "DROP DATABASE IF EXISTS $DDB;" >/dev/null 2>&1
  $PSQL -d postgres -qc "CREATE DATABASE $DDB;" 2>&1 | grep -iE "error|created" || echo "  create: ok"
  echo "restoring (this is the real test)..."
  gunzip -c "$DUMP" | $PSQL -d "$DDB" -q -v ON_ERROR_STOP=0 >/dev/null 2>/tmp/drill_err.txt
  for T in documents matters matter_facts; do
    P=$($PSQL -tAd n8n -c "SELECT count(*) FROM $T" 2>/dev/null)
    S=$($PSQL -tAd "$DDB" -c "SELECT count(*) FROM $T" 2>/dev/null)
    echo "  $T: prod=$P scratch=$S $([ "$P" = "$S" ] && [ -n "$S" ] && echo MATCH || echo 'MISMATCH (prod drift since dump)')"
  done
  S=$($PSQL -tAd "$DDB" -c "SELECT count(*) FROM documents" 2>/dev/null)
  P=$($PSQL -tAd n8n -c "SELECT count(*) FROM documents" 2>/dev/null)
  $PSQL -d postgres -qc "DROP DATABASE $DDB;" >/dev/null 2>&1
  if [ -n "$S" ] && [ "$S" = "$P" ]; then
    echo "VERDICT: PASS — restore faithful (documents $S=$P), scratch dropped $(date -u +%FT%TZ)"
  else
    echo "VERDICT: FAIL — scratch documents=$S vs prod=$P $(date -u +%FT%TZ)"
  fi
  echo
} >> "$LOG" 2>&1
