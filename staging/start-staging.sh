#!/usr/bin/env bash
# Bring up the LandTek staging stack with a fresh restore of prod's
# latest pg_dump.
#
# Usage:  ./start-staging.sh
#         ./start-staging.sh --no-restore     # bring up, don't restore (preserves existing staging state)
#
# After it runs:
#   - n8n editor:  https://staging.leo.hayuma.org   (or http://127.0.0.1:5679 from VPS)
#   - postgres:    127.0.0.1:5433  (user=n8n, pass=same as prod)
#
# Inside containers, postgres is reachable as 'postgres-staging:5432'.

set -euo pipefail

STAGING_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="/var/backups/landtek/postgres"
COMPOSE="docker compose -f $STAGING_DIR/docker-compose.staging.yml --env-file $STAGING_DIR/.env"

RESTORE=true
if [ "${1:-}" = "--no-restore" ]; then
  RESTORE=false
fi

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

log "=== staging start ==="

# ── 1. Bring up postgres-staging FIRST (n8n depends on it) ────────────────
log "starting postgres-staging..."
$COMPOSE up -d postgres-staging

# Wait for postgres to be ready
for i in $(seq 1 30); do
  if docker exec n8n-postgres-staging pg_isready -U n8n -d n8n >/dev/null 2>&1; then
    log "postgres-staging ready"
    break
  fi
  [ $i -eq 30 ] && { log "ERROR: postgres-staging never became ready"; exit 1; }
  sleep 1
done

# ── 2. Restore latest prod pg_dump (unless --no-restore) ──────────────────
if $RESTORE; then
  LATEST=$(ls -1 $BACKUP_DIR/*.sql.gz 2>/dev/null | tail -1 || true)
  if [ -z "$LATEST" ]; then
    log "WARN: no pg_dump found at $BACKUP_DIR — staging will start empty"
  else
    log "restoring from: $LATEST"
    log "  dropping existing schemas..."
    docker exec -i n8n-postgres-staging psql -U n8n -d n8n -v ON_ERROR_STOP=1 -c "
      DROP SCHEMA IF EXISTS public CASCADE;
      CREATE SCHEMA public;
      GRANT ALL ON SCHEMA public TO n8n;
      GRANT ALL ON SCHEMA public TO public;
    " >/dev/null

    log "  loading dump (this takes ~5-10s)..."
    gunzip -c "$LATEST" | docker exec -i n8n-postgres-staging psql -U n8n -d n8n -v ON_ERROR_STOP=1 -q >/dev/null
    log "restore complete"

    # Sanity check: workflow count
    WF_COUNT=$(docker exec n8n-postgres-staging psql -U n8n -d n8n -tAc "SELECT count(*) FROM workflow_entity;")
    log "  workflows in staging DB: $WF_COUNT"
  fi
fi

# ── 3. Bring up n8n-staging ───────────────────────────────────────────────
log "starting n8n-staging..."
$COMPOSE up -d n8n-staging

# Wait for n8n
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:5679/healthz >/dev/null 2>&1; then
    log "n8n-staging ready at http://127.0.0.1:5679"
    break
  fi
  [ $i -eq 60 ] && { log "ERROR: n8n-staging never became ready"; exit 1; }
  sleep 1
done

# ── 4. Summary ────────────────────────────────────────────────────────────
log "=== staging up ==="
log "  editor (local):  http://127.0.0.1:5679"
log "  editor (public): https://staging.leo.hayuma.org  (if nginx + DNS set)"
log "  postgres:        127.0.0.1:5433  (user=n8n)"
log ""
log "When done: ./stop-staging.sh"
