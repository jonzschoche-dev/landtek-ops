#!/bin/bash
# Ping Pong Drip — Claude side. Runs weekdays 10:00–18:00 PHT, every 2h (offset from Grok's 9,11,13,15,17,19).
DOW=$(date +%u); [ "$DOW" -gt 5 ] && exit 0
DRIP="$HOME/Library/CloudStorage/GoogleDrive-jonathan@hayuma.org/My Drive/LANDTEK /Drip"
LOG="$HOME/landtek/ops/drip/claude_pingpong.log"
cd "$HOME/landtek" || exit 1
# Headless auth: launchd can't use the interactive login. Token minted with `claude setup-token`, stored by
# Jonathan in the login keychain as service "landtek-claude-oauth" (never in a repo file, never echoed).
TOKEN=$(security find-generic-password -s landtek-claude-oauth -w 2>/dev/null)
[ -n "$TOKEN" ] && export CLAUDE_CODE_OAUTH_TOKEN="$TOKEN"
unset TOKEN
echo "=== $(date '+%F %T') start" >> "$LOG"
PROMPT="You are Claude, the drafter in LandTek's Ping Pong Drip with Grok (The Drip Bot). Shared folder: $DRIP. Read DRIP_THREAD.md and any new files in to-claude since your last Claude entry. For each open Grok QUESTION, brief, or proposal: reply by appending a stamped entry at the BOTTOM of DRIP_THREAD.md, using the format '### <YYYY-MM-DD HH:MM PHT> — Claude — <ANSWER|AGREE|CHANGE|OBJECT|FIX|QUESTION>' and citing a file path for every fact. When a brief asks for a draft, write it into from-claude (formal; 14 pt on 8.5x13 in for documents; mark gaps [TO FILL]; invent nothing). Log every corpus fix in CORPUS_CHANGELOG.md. Read the corpus in this repo (MASTER_PLAN.md, case_work/) as needed. Never edit another author's entry, never edit MASTER_PLAN.md or other shared stack files, and never send, email, file or post anything outward. If nothing is new, make no changes."
"$HOME/.local/bin/claude" -p "$PROMPT" --permission-mode acceptEdits --add-dir "$DRIP" < /dev/null >> "$LOG" 2>&1
echo "=== $(date '+%F %T') end" >> "$LOG"
