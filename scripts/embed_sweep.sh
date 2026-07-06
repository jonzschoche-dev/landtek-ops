#!/usr/bin/env bash
# embed_sweep.sh — Mac-side embedding sweep (the 'embedded' connect-verify signal).
#
# Why Mac-side: rag_embed_local.py embeds with fastembed (bge-small, 384-dim, $0, no quota) and
# ships the vectors to the VPS over ssh+docker-exec. The 1GB VPS can't hold the model, so this is
# the one connect-verify signal the VPS sweep (case_corpus_sweep.sh §3.5) deliberately does NOT own.
# Run on a launchd timer (mac/com.landtek.embed.plist) so newly-ingested docs get embedded each cycle.
# Idempotent: rag_embed_local only embeds docs not already in rag_local.
set -euo pipefail
REPO="${LANDTEK_REPO:-/Users/jonathanzschoche/landtek}"
PY="/Users/jonathanzschoche/yes/bin/python3"   # the interpreter that has fastembed
cd "$REPO"
echo "[embed_sweep] $(date -u +%FT%TZ) start"
"$PY" scripts/rag_embed_local.py --embed 2>&1 | tail -4 || true
echo "[embed_sweep] $(date -u +%FT%TZ) done"
