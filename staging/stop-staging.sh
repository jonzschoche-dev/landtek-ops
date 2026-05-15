#!/usr/bin/env bash
# Shut down the LandTek staging stack.
#
# Usage:  ./stop-staging.sh                  # stop containers, keep volumes
#         ./stop-staging.sh --wipe-volumes   # also delete staging DB + n8n data
#                                            # (next start-staging.sh restores fresh from prod)

set -euo pipefail

STAGING_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE="docker compose -f $STAGING_DIR/docker-compose.staging.yml --env-file $STAGING_DIR/.env"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

log "=== staging stop ==="

if [ "${1:-}" = "--wipe-volumes" ]; then
  log "stopping + wiping volumes..."
  $COMPOSE down -v
  log "volumes wiped — next start will restore from latest pg_dump"
else
  log "stopping containers (keeping volumes)..."
  $COMPOSE down
  log "stopped — staging DB preserved, next start will REPLACE it via restore"
  log "  (use --wipe-volumes to clear staging state entirely)"
fi

log "=== staging down ==="
