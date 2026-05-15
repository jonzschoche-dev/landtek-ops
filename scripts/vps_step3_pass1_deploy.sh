#!/usr/bin/env bash
# LeoLandTek v4 - Step 3: install Pass 1 deps + run smoke test.
# Assumes /root/landtek/scripts/worker.tar.gz already exists (paste #1 wrote it).
set -euo pipefail

LANDTEK=/root/landtek
mkdir -p "$LANDTEK" "$LANDTEK/scripts" "$LANDTEK/inbox" "$LANDTEK/pass1_out"

echo "===== [1/4] Verifying tarball ====="
if [ ! -f "$LANDTEK/scripts/worker.tar.gz" ]; then
  echo "ERROR: $LANDTEK/scripts/worker.tar.gz missing. Run paste #1 first."; exit 2
fi
ls -la "$LANDTEK/scripts/worker.tar.gz"

echo
echo "===== [2/4] Installing Python deps ====="
pip install --break-system-packages --ignore-installed typing-extensions >/dev/null 2>&1 || true
pip install --break-system-packages python-dotenv anthropic openai lxml httpx \
  pymupdf requests psycopg2-binary google-auth google-cloud-documentai
echo "  deps installed"

echo
echo "===== [3/4] Extracting worker -> $LANDTEK/worker/ ====="
tar xzf "$LANDTEK/scripts/worker.tar.gz" -C "$LANDTEK/"
ls -la "$LANDTEK/worker/"

echo
echo "===== [4/4] Smoke test: Pass 1 over /root/landtek/inbox/ ====="
cd "$LANDTEK/worker" && python3 test_pass1.py 2>&1 | tee "$LANDTEK/step3.log"

echo
echo "===== Pass 1 XML outputs ====="
ls -la "$LANDTEK/pass1_out/" 2>/dev/null
echo
echo "===== STEP 3 COMPLETE ====="
