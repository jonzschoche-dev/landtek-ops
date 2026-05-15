#!/usr/bin/env bash
# 5-phase orchestrator. Run on the VPS.
set -uo pipefail   # not -e: we want to continue on partial failures and report

LANDTEK=/root/landtek
cd "$LANDTEK/worker" || { echo "worker dir missing"; exit 1; }

source <(grep -E '^[A-Z]+=.*$' "$LANDTEK/.env" | sed 's/^/export /')

echo
echo "###########################################################"
echo "#  PHASE 1: Drive inventory"
echo "###########################################################"
python3 inventory.py 2>&1 | tee "$LANDTEK/phase1_inventory.log"

echo
echo "###########################################################"
echo "#  PHASE 2: Verify folders.json"
echo "###########################################################"
if [ -f "$LANDTEK/folders.json" ]; then
  echo "  folders.json already exists — keeping current values"
else
  cp "$LANDTEK/worker/folders.json" "$LANDTEK/folders.json"
  echo "  Wrote $LANDTEK/folders.json from worker/folders.json"
fi
cat "$LANDTEK/folders.json"

echo
echo "###########################################################"
echo "#  PHASE 3: Ingestion (PyMuPDF/DocAI -> GPT-4o -> Drive -> Qdrant -> Postgres)"
echo "###########################################################"
python3 ingest_v5.py 2>&1 | tee "$LANDTEK/phase3_ingest.log"

echo
echo "###########################################################"
echo "#  PHASE 4: Backtests"
echo "###########################################################"
python3 backtest.py 2>&1 | tee "$LANDTEK/phase4_backtest.log"

echo
echo "###########################################################"
echo "#  PHASE 5: Final state report"
echo "###########################################################"
echo
echo "--- Postgres documents by case ---"
docker exec n8n-postgres-1 psql -U n8n -d n8n -c \
  "SELECT case_file, COUNT(*), SUM(duplicate_count) AS total_seen FROM documents GROUP BY case_file ORDER BY case_file;"

echo
echo "--- Qdrant landtek_documents count ---"
curl -s -H "api-key: $QDRANT_KEY" "$QDRANT_URL/collections/landtek_documents" \
  | python3 -c "import sys,json; d=json.load(sys.stdin)['result']; print(f\"  points_count: {d.get('points_count')}, vectors_count: {d.get('vectors_count')}, status: {d.get('status')}\")"

echo
echo "--- Logs available at: ---"
ls -la "$LANDTEK"/phase*_*.log

echo
echo "DONE."
