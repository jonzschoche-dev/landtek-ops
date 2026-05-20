#!/usr/bin/env bash
# mac_sync.sh — auto-pull landtek-ops on the Mac, safely.
#
# Pulls from origin/main if and only if:
#   - working tree is clean (no uncommitted changes)
#   - we are on the `main` branch
#   - origin has new commits AND the local HEAD is a strict ancestor (fast-forward only)
#
# Never auto-merges. Never overwrites local work. Never auto-commits or auto-pushes.
# Designed to run from launchd every couple of minutes.
#
# Logs to ~/Library/Logs/landtek_sync.log
#
# Companion: ~/Library/LaunchAgents/com.landtek.sync.plist (installs the schedule)
# Documentation: see WORKFLOW.md § "Mac auto-sync"

set -euo pipefail

REPO="${LANDTEK_REPO:-$HOME/landtek}"
LOG="$HOME/Library/Logs/landtek_sync.log"
mkdir -p "$(dirname "$LOG")"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*" >> "$LOG"; }

if [ ! -d "$REPO/.git" ]; then
    log "no git repo at $REPO — exiting"
    exit 0
fi

cd "$REPO"

# Refuse to touch a non-main branch (user is doing something deliberate)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ]; then
    log "on branch '$BRANCH' (not main) — skipping pull"
    exit 0
fi

# Refuse to touch a dirty working tree
if ! git diff-index --quiet HEAD --; then
    log "dirty working tree — skipping pull (run 'cd $REPO && git status' to see what's modified)"
    exit 0
fi

# Refuse if there are untracked files that look important (top-level only, ignored files OK)
UNTRACKED=$(git ls-files --others --exclude-standard --directory --no-empty-directory --error-unmatch . 2>/dev/null | head -1 || true)
# (note: not blocking on untracked — git pull won't touch them)

# Fetch quietly
if ! git fetch --quiet origin main 2>>"$LOG"; then
    log "fetch failed — check SSH key / network"
    exit 0
fi

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    # nothing new — silent (avoid spamming the log)
    exit 0
fi

# Make sure remote is ahead, not diverged
BASE=$(git merge-base HEAD origin/main)
if [ "$BASE" != "$LOCAL" ]; then
    log "diverged from origin/main (local has commits remote doesn't) — skipping pull. Resolve manually with: cd $REPO && git pull --rebase"
    exit 0
fi

# Fast-forward pull
if git pull --ff-only --quiet origin main 2>>"$LOG"; then
    NEW=$(git rev-parse HEAD)
    COMMITS=$(git log --oneline --no-decorate "$LOCAL..$NEW")
    NUM=$(echo "$COMMITS" | wc -l | tr -d ' ')
    log "pulled $NUM new commit(s):"
    while IFS= read -r line; do
        log "    $line"
    done <<< "$COMMITS"
else
    log "pull failed (something blocked the fast-forward)"
fi
