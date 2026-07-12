#!/bin/bash
# offbox_backup_pull.sh — the A62 off-box leg, v2 (2026-07-11): the Mac pulls the nightly DOMAIN dump
# from the VPS over the tailnet, verifies the checksum, encrypts it locally, uploads the ciphertext to
# the canonical LANDTEK Drive through the VPS service account, prunes local ladders, and writes receipts
# to the VPS (/root/backups/offbox_receipts.log) — the receipt is what the truth test verifies, so the
# deploy gate never touches the network (A53-clean) and a silent Mac failure surfaces as a stale receipt.
# Runs on the Mac via launchd com.landtek.offbox-backup (daily 11:00 local = 03:00 UTC, 1h after the dump).
# $0 · no third party · different failure domain (the Mac is already always-on stack infrastructure).
set -u
VPS="root@100.85.203.58"
DEST="$HOME/landtek-backups"
KEEP=10
KEY_FILE="${LANDTEK_BACKUP_KEY_FILE:-$HOME/.config/landtek/backup-encryption.key}"
CLOUD_DIR="08 - Internal/Backups/Database"
mkdir -p "$DEST"

NEWEST=$(ssh -o ConnectTimeout=20 "$VPS" 'ls -t /root/backups/landtek_backup_*.sql.gz 2>/dev/null | head -1')
[ -z "$NEWEST" ] && { echo "$(date -u +%FT%TZ) PULL FAILED: no dump found on VPS"; exit 1; }
BASE=$(basename "$NEWEST")

scp -q "$VPS:$NEWEST" "$DEST/$BASE.part" || { echo "$(date -u +%FT%TZ) PULL FAILED: scp $BASE"; exit 1; }

REMOTE_SHA=$(ssh "$VPS" "shasum -a 256 $NEWEST 2>/dev/null || sha256sum $NEWEST" | cut -d' ' -f1)
LOCAL_SHA=$(shasum -a 256 "$DEST/$BASE.part" | cut -d' ' -f1)
if [ -z "$REMOTE_SHA" ] || [ "$REMOTE_SHA" != "$LOCAL_SHA" ]; then
    echo "$(date -u +%FT%TZ) PULL FAILED: checksum mismatch on $BASE (remote=$REMOTE_SHA local=$LOCAL_SHA)"
    rm -f "$DEST/$BASE.part"; exit 1
fi
mv "$DEST/$BASE.part" "$DEST/$BASE"

# receipt on the VPS: written ONLY after a verified copy exists off-box
ssh "$VPS" "echo \"$(date -u +%FT%TZ) $LOCAL_SHA $BASE mac:$(hostname -s)\" >> /root/backups/offbox_receipts.log"

# Independent cloud leg.  Only ciphertext leaves the Mac; the key never goes to the VPS or Drive.
[ -s "$KEY_FILE" ] || { echo "$(date -u +%FT%TZ) CLOUD FAILED: encryption key missing: $KEY_FILE"; exit 1; }
ENC="$DEST/$BASE.enc"
openssl enc -aes-256-cbc -salt -pbkdf2 -iter 250000 -md sha256 \
  -in "$DEST/$BASE" -out "$ENC.part" -pass "file:$KEY_FILE" || {
    rm -f "$ENC.part"; echo "$(date -u +%FT%TZ) CLOUD FAILED: encryption"; exit 1;
  }
mv "$ENC.part" "$ENC"
ENC_SHA=$(shasum -a 256 "$ENC" | cut -d' ' -f1)
ENC_BASE=$(basename "$ENC")
scp -q "$ENC" "$VPS:/tmp/$ENC_BASE.part" || {
  echo "$(date -u +%FT%TZ) CLOUD FAILED: encrypted transfer"; exit 1;
}
ssh "$VPS" "set -e; rclone copyto '/tmp/$ENC_BASE.part' 'gdrive-sa:$CLOUD_DIR/$ENC_BASE'; rm -f '/tmp/$ENC_BASE.part'" || {
  ssh "$VPS" "rm -f '/tmp/$ENC_BASE.part'" 2>/dev/null || true
  echo "$(date -u +%FT%TZ) CLOUD FAILED: Drive upload"; exit 1;
}
CLOUD_SHA=$(ssh "$VPS" "rclone cat 'gdrive-sa:$CLOUD_DIR/$ENC_BASE' | sha256sum" | cut -d' ' -f1)
if [ -z "$CLOUD_SHA" ] || [ "$CLOUD_SHA" != "$ENC_SHA" ]; then
  echo "$(date -u +%FT%TZ) CLOUD FAILED: ciphertext checksum mismatch"; exit 1
fi
ssh "$VPS" "echo \"$(date -u +%FT%TZ) $ENC_SHA $ENC_BASE gdrive:LANDTEK/$CLOUD_DIR\" >> /root/backups/cloud_receipts.log"

# prune the local ladder
ls -t "$DEST"/landtek_backup_*.sql.gz 2>/dev/null | tail -n +$((KEEP+1)) | xargs -I{} rm -f {}
ls -t "$DEST"/landtek_backup_*.sql.gz.enc 2>/dev/null | tail -n +$((KEEP+1)) | xargs -I{} rm -f {}
echo "$(date -u +%FT%TZ) off-box+cloud OK: $BASE ($(du -h "$DEST/$BASE" | cut -f1)) sha=$LOCAL_SHA cloud_sha=$ENC_SHA"
