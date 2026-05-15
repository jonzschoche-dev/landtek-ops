#!/usr/bin/env bash
# LeoLandTek v4 — Step 1: persist secrets + swap n8n postgres to pgvector image.
# Run: bash vps_step1_postgres_pgvector.sh 2>&1 | tee /root/landtek/step1.log
# Idempotent — safe to re-run if it fails partway.

set -euo pipefail

LANDTEK=/root/landtek
ENV_FILE="$LANDTEK/.env"
mkdir -p "$LANDTEK" "$LANDTEK/inbox" "$LANDTEK/backups" "$LANDTEK/scripts"

echo "===== [1/8] Persisting secrets to $ENV_FILE ====="
cat > "$ENV_FILE" <<'ENV'
# LeoLandTek runtime secrets. chmod 600. Do not commit.
OPENAI_API_KEY=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
ANTHROPIC_API_KEY=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
GEMINI_API_KEY=AIzaSyCAYfXQrsrAolaGhSzAcFat7g6NzBIMQbQ
GOOGLE_APPLICATION_CREDENTIALS=/root/landtek/google-creds.json
QDRANT_URL=https://6ac62f30-e965-4b10-84f2-ce95caa09a4d.australia-southeast1-0.gcp.cloud.qdrant.io
QDRANT_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIiwic3ViamVjdCI6ImFwaS1rZXk6N2Y3ZTQwMmEtZDczYy00ODZiLTgwODgtYzgwZmQ0YjI5YTg2In0.gqi506r3NMyVGcpFczFAltFcfbkMKEcINsNj-Fl_geg
PGHOST=172.18.0.3
PGPORT=5432
PGDATABASE=n8n
PGUSER=n8n
PGPASSWORD=n8npassword
TG_AUTHORIZED_USERS=6513067717:Jonathan_Zschoche
TAVILY_API_KEY=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
ENV
chmod 600 "$ENV_FILE"
echo "  OK ($(wc -l < "$ENV_FILE") lines, mode $(stat -c%a "$ENV_FILE"))"

echo
echo "===== [2/8] Discovering n8n docker-compose ====="
COMPOSE=""
for cand in /root/n8n/docker-compose.yml /root/n8n/docker-compose.yaml \
           /root/.n8n/docker-compose.yml /opt/n8n/docker-compose.yml \
           /root/docker-compose.yml /root/docker-compose.yaml; do
  [ -f "$cand" ] && COMPOSE="$cand" && break
done
if [ -z "$COMPOSE" ]; then
  COMPOSE=$(find /root /opt /etc -maxdepth 4 -name 'docker-compose*.y*ml' 2>/dev/null \
            | xargs -I{} grep -l -E 'postgres:15|n8nio/n8n' {} 2>/dev/null | head -1)
fi
if [ -z "$COMPOSE" ]; then
  echo "  ERROR: could not locate docker-compose for n8n stack"
  echo "  Run: find / -name 'docker-compose*.y*ml' 2>/dev/null"
  exit 2
fi
echo "  Found: $COMPOSE"
COMPOSE_DIR=$(dirname "$COMPOSE")

echo
echo "===== [3/8] Backing up compose + listing current postgres state ====="
TS=$(date +%Y%m%d_%H%M%S)
cp "$COMPOSE" "$LANDTEK/backups/$(basename "$COMPOSE").$TS"
echo "  Backup: $LANDTEK/backups/$(basename "$COMPOSE").$TS"
echo "  Current postgres image lines:"
grep -nE 'image:.*postgres' "$COMPOSE" | sed 's/^/    /'
echo "  Postgres container info:"
docker inspect n8n-postgres-1 -f 'image={{.Config.Image}} | mounts={{range .Mounts}}{{.Source}}->{{.Destination}} {{end}}' || true

echo
echo "===== [4/8] Patching postgres image -> pgvector/pgvector:pg15 ====="
if grep -qE 'image:\s*pgvector/pgvector:pg15' "$COMPOSE"; then
  echo "  Already on pgvector image, skipping patch"
else
  sed -i.bak -E 's|image:\s*postgres:15([^[:space:]]*)|image: pgvector/pgvector:pg15|' "$COMPOSE"
  echo "  Patched. Diff:"
  diff "$LANDTEK/backups/$(basename "$COMPOSE").$TS" "$COMPOSE" | sed 's/^/    /' || true
fi

echo
echo "===== [5/8] Recreating postgres container (n8n briefly drops) ====="
cd "$COMPOSE_DIR"
docker compose pull postgres || docker compose pull db || true
docker compose up -d
sleep 3

echo
echo "===== [6/8] Waiting for postgres to accept connections ====="
for i in $(seq 1 30); do
  if docker exec n8n-postgres-1 pg_isready -U n8n -d n8n >/dev/null 2>&1; then
    echo "  Ready after ${i}s"; break
  fi
  sleep 1
  if [ $i -eq 30 ]; then echo "  ERROR: postgres did not come up in 30s"; docker logs --tail=50 n8n-postgres-1; exit 3; fi
done

echo
echo "===== [7/8] Installing extensions ====="
docker exec n8n-postgres-1 psql -U n8n -d n8n -c "CREATE EXTENSION IF NOT EXISTS vector;"
docker exec n8n-postgres-1 psql -U n8n -d n8n -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
echo "  Installed extensions:"
docker exec n8n-postgres-1 psql -U n8n -d n8n -c "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector','pg_trgm');"

echo
echo "===== [8/8] Smoke test: vector type works ====="
docker exec n8n-postgres-1 psql -U n8n -d n8n -c "SELECT '[1,2,3]'::vector(3) <=> '[3,2,1]'::vector(3) AS cosine_distance;"
echo
echo "===== STEP 1 COMPLETE ====="
echo "  - .env persisted"
echo "  - postgres swapped to pgvector/pgvector:pg15"
echo "  - extensions vector + pg_trgm installed"
echo "  - existing data preserved (volume mount unchanged)"
echo
echo "Verify n8n is alive:"
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}' | grep -E 'n8n|postgres'
