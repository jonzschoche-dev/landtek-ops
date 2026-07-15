#!/bin/bash
# offbox_backup_pull.sh — the A62 off-box leg, v2 (2026-07-11): the Mac pulls the nightly DOMAIN dump
# from the VPS over the tailnet, verifies the checksum, encrypts it locally, uploads the ciphertext to
# the canonical LANDTEK Drive through the VPS service account, prunes local ladders, and writes receipts
# to the VPS (/root/backups/offbox_receipts.log) — the receipt is what the truth test verifies, so the
# deploy gate never touches the network (A53-clean) and a silent Mac failure surfaces as a stale receipt.
# Runs on the Mac via launchd com.landtek.offbox-backup (daily 11:00 local = 03:00 UTC, 1h after the dump).
# $0 · no third party · different failure domain (the Mac is already always-on stack infrastructure).
set -u
# Prefer Host alias (ssh config / Tailscale) — IP alone has hit check-mode reauth failures.
VPS="${LANDTEK_VPS_SSH:-landtek}"
DEST="$HOME/landtek-backups"
KEEP=10
KEY_FILE="${LANDTEK_BACKUP_KEY_FILE:-$HOME/.config/landtek/backup-encryption.key}"
CLOUD_DIR="08 - Internal/Backups/Database"
SSH_OPTS="-o ConnectTimeout=20 -o BatchMode=yes -o StrictHostKeyChecking=accept-new"
mkdir -p "$DEST"

ssh_vps() { ssh $SSH_OPTS "$VPS" "$@"; }
scp_vps() { scp $SSH_OPTS "$@"; }

NEWEST=$(ssh_vps 'ls -t /root/backups/landtek_backup_*.sql.gz 2>/dev/null | head -1')
[ -z "$NEWEST" ] && { echo "$(date -u +%FT%TZ) PULL FAILED: no dump found on VPS (ssh=$VPS)"; exit 1; }
BASE=$(basename "$NEWEST")

scp_vps -q "$VPS:$NEWEST" "$DEST/$BASE.part" || { echo "$(date -u +%FT%TZ) PULL FAILED: scp $BASE"; exit 1; }

REMOTE_SHA=$(ssh_vps "shasum -a 256 $NEWEST 2>/dev/null || sha256sum $NEWEST" | cut -d' ' -f1)
LOCAL_SHA=$(shasum -a 256 "$DEST/$BASE.part" | cut -d' ' -f1)
if [ -z "$REMOTE_SHA" ] || [ "$REMOTE_SHA" != "$LOCAL_SHA" ]; then
    echo "$(date -u +%FT%TZ) PULL FAILED: checksum mismatch on $BASE (remote=$REMOTE_SHA local=$LOCAL_SHA)"
    rm -f "$DEST/$BASE.part"; exit 1
fi
mv "$DEST/$BASE.part" "$DEST/$BASE"

# REQUIRED A62 off-box receipt: written ONLY after a verified Mac copy exists.
# This is the survivable-record leg. Cloud below is OPTIONAL hardening — must not undo this.
ssh_vps "echo \"$(date -u +%FT%TZ) $LOCAL_SHA $BASE mac:$(hostname -s)\" >> /root/backups/offbox_receipts.log"
echo "$(date -u +%FT%TZ) off-box OK: $BASE ($(du -h "$DEST/$BASE" | cut -f1)) sha=$LOCAL_SHA"

# Optional encrypted Drive leg. Failures are reported; exit 0 so launchd does not look "dead"
# when the required off-box copy already succeeded (gdrive-sa 403 is structural until OAuth/Shared Drive).
CLOUD_OK=0
if [ ! -s "$KEY_FILE" ]; then
  echo "$(date -u +%FT%TZ) CLOUD SKIPPED: encryption key missing: $KEY_FILE (off-box leg is green)"
else
  ENC="$DEST/$BASE.enc"
  if openssl enc -aes-256-cbc -salt -pbkdf2 -iter 250000 -md sha256 \
      -in "$DEST/$BASE" -out "$ENC.part" -pass "file:$KEY_FILE"; then
    mv "$ENC.part" "$ENC"
    ENC_SHA=$(shasum -a 256 "$ENC" | cut -d' ' -f1)
    ENC_BASE=$(basename "$ENC")
    if scp_vps -q "$ENC" "$VPS:/tmp/$ENC_BASE.part" \
       && ssh_vps "set -e; rclone copyto '/tmp/$ENC_BASE.part' 'gdrive-sa:$CLOUD_DIR/$ENC_BASE'; rm -f '/tmp/$ENC_BASE.part'"; then
      CLOUD_SHA=$(ssh_vps "rclone cat 'gdrive-sa:$CLOUD_DIR/$ENC_BASE' | sha256sum" | cut -d' ' -f1)
      if [ -n "$CLOUD_SHA" ] && [ "$CLOUD_SHA" = "$ENC_SHA" ]; then
        ssh_vps "echo \"$(date -u +%FT%TZ) $ENC_SHA $ENC_BASE gdrive:LANDTEK/$CLOUD_DIR\" >> /root/backups/cloud_receipts.log"
        CLOUD_OK=1
        echo "$(date -u +%FT%TZ) cloud OK: $ENC_BASE sha=$ENC_SHA"
      else
        echo "$(date -u +%FT%TZ) CLOUD FAILED: ciphertext checksum mismatch (off-box still green)"
      fi
    else
      ssh_vps "rm -f '/tmp/$ENC_BASE.part'" 2>/dev/null || true
      echo "$(date -u +%FT%TZ) CLOUD FAILED: Drive upload (off-box still green; often gdrive-sa 403 quota)"
    fi
  else
    rm -f "$ENC.part"
    echo "$(date -u +%FT%TZ) CLOUD FAILED: encryption (off-box still green)"
  fi
fi

# prune the local ladder
ls -t "$DEST"/landtek_backup_*.sql.gz 2>/dev/null | tail -n +$((KEEP+1)) | xargs -I{} rm -f {}
ls -t "$DEST"/landtek_backup_*.sql.gz.enc 2>/dev/null | tail -n +$((KEEP+1)) | xargs -I{} rm -f {}
if [ "$CLOUD_OK" = 1 ]; then
  echo "$(date -u +%FT%TZ) off-box+cloud OK: $BASE sha=$LOCAL_SHA"
else
  echo "$(date -u +%FT%TZ) off-box OK (cloud not operational): $BASE sha=$LOCAL_SHA"
fi
exit 0
