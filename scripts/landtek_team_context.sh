#!/usr/bin/env bash
# Prints team context at Claude Code SessionStart: latest change logs and the latest Grok handoff.
cd "$(dirname "$0")/.." || exit 0
echo "=== LANDTEK TEAM CONTEXT (you are one AI on a team; the record is the source of truth) ==="
echo "--- Latest change logs (case_work/CHANGELOGS) ---"
ls -t case_work/CHANGELOGS/*.txt 2>/dev/null | head -3 | while read f; do echo ">> $f"; head -60 "$f"; done
echo "--- Latest Grok to Claude handoff ---"
f=$(ls -t case_work/CLAUDE_GROK_HANDOFF/*GROK_TO_CLAUDE*.md 2>/dev/null | head -1)
[ -n "$f" ] && { echo ">> $f"; head -80 "$f"; }
echo "--- 5 most recent OPEN ITEMS (case_work/HARVEST/MASTER_HARVEST.md) ---"
[ -f case_work/HARVEST/MASTER_HARVEST.md ] && awk '/^## Recent open items/{f=1;next} f&&/^## /{exit} f&&/^- /{print; if(++n==5) exit}' case_work/HARVEST/MASTER_HARVEST.md
echo "=== Before ending: write case_work/CHANGELOGS/CHANGELOG_claude_<matter>_<YYYY-MM-DD>.txt (CHANGED, DECIDED, OPEN, CONFLICTS) ==="
exit 0
