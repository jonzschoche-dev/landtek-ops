#!/usr/bin/env bash
# publish.sh — ONE command to publish an instrument (Mac-side wrapper for the VPS publish.py).
# Collapses: write md -> scp -> render -> register/host -> (Telegram) -> pull PDF back.
#
#   scripts/publish.sh 1891_output/foo.md --matter MWK-ARTA-1210 --title "Errata — OP/1210"
#   scripts/publish.sh 1891_output/foo.md --matter MWK-OP-PETITION --matter MWK-ARTA-1210 \
#                      --telegram --caption "..."
#   scripts/publish.sh 1891_output/foo.md --dry        # render only, no DB write / no send
set -euo pipefail
[ $# -ge 1 ] || { echo "usage: publish.sh <markdown.md> [--matter M] [--title T] [--telegram --caption C] [--dry]"; exit 1; }
MD="$1"; shift
VPS="root@100.85.203.58"
base="$(basename "$MD")"
[ -f "$MD" ] || { echo "not found: $MD"; exit 1; }

scp -q "$MD" "$VPS:/root/landtek/1891_output/$base"
# pass remaining args through with shell-safe quoting (handles --title "two words")
ssh -o ConnectTimeout=90 "$VPS" "cd /root/landtek && set -a; . .env 2>/dev/null; set +a; \
  python3 scripts/publish.py /root/landtek/1891_output/$base $(printf '%q ' "$@") 2>&1 | grep -vE 'Warning|warn|oauth2|file_cache|Insecure'"
# pull the rendered PDF back for local reference (best-effort)
scp -q "$VPS:/root/landtek/1891_output/${base%.md}.pdf" "$(dirname "$MD")/" 2>/dev/null && echo "[publish] PDF copied to $(dirname "$MD")/" || true
