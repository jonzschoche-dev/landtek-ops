#!/usr/bin/env bash
# LandTek nightly backup — runs from systemd timer.
#
# Backs up to /var/backups/landtek/ on the same VPS:
#   - postgres/YYYY-MM-DD.sql.gz       (n8n DB dump, ~few MB)
#   - uploads/                         (rsync of /root/landtek/uploads/ mirror)
#   - code/YYYY-MM-DD.tgz              (code + configs, no uploads/git)
#   - snapshots/YYYY-MM-DD.json        (current workflow JSON dump)
#
# Retention: keep last 7 daily + 4 weekly (Sunday) + 12 monthly (1st).
#
# Off-site upload step: stub — fill in when destination is chosen
# (Backblaze B2 / Drive / rsync.net / S3).

set -uo pipefail

DEST=/var/backups/landtek
LOG=/var/log/landtek_backup.log
DATE=$(date -u +%Y-%m-%d)
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

mkdir -p "$DEST/postgres" "$DEST/uploads" "$DEST/code" "$DEST/snapshots"

log() {
  echo "[$TS] $*" | tee -a "$LOG"
}

log "=== backup start ==="

# ── 1. Postgres dump ──────────────────────────────────────────────────────
PG_DEST="$DEST/postgres/${DATE}.sql.gz"
if docker exec -i n8n-postgres-1 pg_dump -U n8n -d n8n --no-owner --no-privileges \
   | gzip -9 > "$PG_DEST"; then
  SIZE=$(stat -c%s "$PG_DEST")
  log "postgres: ${PG_DEST} (${SIZE} bytes)"
else
  log "ERROR: postgres dump failed"
fi

# ── 2. Uploads mirror ─────────────────────────────────────────────────────
if rsync -a --delete /root/landtek/uploads/ "$DEST/uploads/" 2>>"$LOG"; then
  FILES=$(find "$DEST/uploads" -type f | wc -l)
  SIZE=$(du -sb "$DEST/uploads" | cut -f1)
  log "uploads: ${FILES} files, ${SIZE} bytes"
else
  log "ERROR: uploads rsync failed"
fi

# ── 3. Code + configs tarball (exclude uploads, .git, large reports) ──────
CODE_DEST="$DEST/code/${DATE}.tgz"
tar -czf "$CODE_DEST" \
    --exclude=uploads --exclude=.git --exclude=__pycache__ \
    --exclude=reports --exclude=per_page_work --exclude=case_files \
    --exclude=intake_out --exclude=memo_out --exclude=pass1_out --exclude=pass2_out \
    --exclude=heightened_ocr/extract_with_timeout.log \
    -C /root landtek \
    -C /etc/nginx sites-available/leo htpasswd.landtek 2>>"$LOG" \
  && log "code: ${CODE_DEST} ($(stat -c%s "$CODE_DEST") bytes)" \
  || log "ERROR: code tarball failed"

# ── 4. Workflow JSON snapshot ─────────────────────────────────────────────
SNAP_DEST="$DEST/snapshots/${DATE}.json"
docker exec -i n8n-postgres-1 psql -U n8n -d n8n -tAc "
  SELECT row_to_json(w)::text FROM
    (SELECT id, name, nodes, connections, \"updatedAt\"
       FROM workflow_entity WHERE name='Leos Workflow') w;
" > "$SNAP_DEST" 2>>"$LOG" && log "snapshot: ${SNAP_DEST} ($(stat -c%s "$SNAP_DEST") bytes)" \
  || log "ERROR: workflow snapshot failed"

# ── 5. Retention pruning ──────────────────────────────────────────────────
# Daily: keep last 7
# Weekly (Sunday): keep last 4
# Monthly (1st): keep last 12
# Implementation: find files older than thresholds and delete unless Sunday/1st
for kind in postgres code snapshots; do
  find "$DEST/$kind" -type f -mtime +7 | while read -r f; do
    base=$(basename "$f" | sed 's/\.[a-z.]*$//')
    # Extract YYYY-MM-DD
    if [[ "$base" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2} ]]; then
      DAY_OF_WEEK=$(date -d "${BASH_REMATCH[0]}" +%u 2>/dev/null || echo 0)
      DAY_OF_MONTH=$(date -d "${BASH_REMATCH[0]}" +%d 2>/dev/null || echo 0)
      AGE_DAYS=$(( ( $(date +%s) - $(date -d "${BASH_REMATCH[0]}" +%s 2>/dev/null) ) / 86400 ))
      # Keep Sundays for up to 28 days, 1sts for up to 365 days
      if [[ "$DAY_OF_MONTH" == "01" ]] && (( AGE_DAYS < 365 )); then continue; fi
      if [[ "$DAY_OF_WEEK" == "7" ]] && (( AGE_DAYS < 28 )); then continue; fi
      rm -f "$f" && log "pruned: $f (${AGE_DAYS}d old)"
    fi
  done
done

# ── 6. Off-site upload to Backblaze B2 ────────────────────────────────────
# Remote 'landtek-b2' is configured in /root/.config/rclone/rclone.conf (chmod 600).
# Bucket 'LeoLandtek' is scoped to a dedicated app key (no master credentials).
#
# Sync is idempotent: only changed files are re-uploaded.
# uploads/ is EXCLUDED from B2 — the document corpus is already backed up in Google
# Drive, and mirroring it here was ~4.5 GB of redundant data that filled the bucket.
# B2 holds the irreplaceable layer only: DB dumps, code tarballs, workflow snapshots.
# (rclone sync will delete the existing uploads/ mirror from B2 on the next run.)
log "starting B2 off-site sync (uploads/ excluded — corpus lives in Drive)..."
if rclone sync "$DEST/" landtek-b2:LeoLandtek/landtek-vps/ \
     --exclude 'uploads/**' \
     --transfers 4 --checkers 8 \
     --log-file "$LOG" --log-level NOTICE 2>>"$LOG"; then
  REMOTE_SIZE=$(rclone size landtek-b2:LeoLandtek/landtek-vps/ --json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['bytes'])" 2>/dev/null || echo "?")
  log "B2 sync: ok (${REMOTE_SIZE} bytes in bucket)"
else
  log "ERROR: B2 sync failed — local backup is fine, off-site is stale until next run"
fi

# ── 7. Inventory summary ──────────────────────────────────────────────────
log "=== inventory ==="
log "postgres: $(ls $DEST/postgres | wc -l) dumps, $(du -sh $DEST/postgres | cut -f1)"
log "uploads:  $(find $DEST/uploads -type f | wc -l) files, $(du -sh $DEST/uploads | cut -f1)"
log "code:     $(ls $DEST/code | wc -l) tarballs, $(du -sh $DEST/code | cut -f1)"
log "snaps:    $(ls $DEST/snapshots | wc -l) snapshots, $(du -sh $DEST/snapshots | cut -f1)"
log "TOTAL:    $(du -sh $DEST | cut -f1)"

log "=== backup end ==="
exit 0
