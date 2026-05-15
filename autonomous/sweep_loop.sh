#!/usr/bin/env bash
# sweep_loop.sh — keep running tct_sweep.py until queue drains or all keys cool
# Recognizes structured exit reasons emitted by tct_sweep.py
set -euo pipefail

LOG=/var/log/sweep-loop.log
SLEEP_BETWEEN=10        # short pause between productive cycles
SLEEP_ON_NOTHING=900    # 15 min when queue empty
SLEEP_ON_COOLDOWN=1800  # 30 min when all keys cool
SLEEP_ON_BUDGET=3600    # 1 hour when budget exhausted

while true; do
    OUT=$(python3 /root/landtek/autonomous/tct_sweep.py 2>&1)
    echo "[$(date -u +%H:%M:%S)] $OUT" >> "$LOG"

    if echo "$OUT" | grep -qE "no docs queued|nothing to extract"; then
        echo "[$(date -u +%H:%M:%S)] queue empty — sleeping ${SLEEP_ON_NOTHING}s" >> "$LOG"
        sleep $SLEEP_ON_NOTHING
    elif echo "$OUT" | grep -qiE "all keys in cooldown|in cooldown — waiting"; then
        echo "[$(date -u +%H:%M:%S)] all keys cooled — sleeping ${SLEEP_ON_COOLDOWN}s" >> "$LOG"
        sleep $SLEEP_ON_COOLDOWN
    elif echo "$OUT" | grep -qiE "budget exhausted|daily budget"; then
        echo "[$(date -u +%H:%M:%S)] budget exhausted — sleeping ${SLEEP_ON_BUDGET}s" >> "$LOG"
        sleep $SLEEP_ON_BUDGET
    else
        # Productive cycle (extracted something or failed-but-progressed)
        sleep $SLEEP_BETWEEN
    fi
done
