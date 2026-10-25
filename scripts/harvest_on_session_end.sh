#!/usr/bin/env bash
# SessionEnd hook: harvest this session into case_work/HARVEST in the background.
# Reads the hook input JSON on stdin for session_id. Never touches the .jsonl itself.
cd "$(dirname "$0")/.." || exit 0
sid=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("session_id",""))' 2>/dev/null)
[ -z "$sid" ] && exit 0
# The harvester's own claude -p children run from /tmp without persistence, so this hook never fires for them.
nohup bash -c "sleep 10; python3 scripts/harvest_sessions.py --only '${sid:0:8}' --now" \
  >> case_work/HARVEST/_harvest.log 2>&1 < /dev/null &
disown 2>/dev/null
exit 0
