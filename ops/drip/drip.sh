#!/bin/bash
# The drip, single input → single output (Jonathan, 20 Oct 2026). One brain: Claude. Never sends.
#   drip.sh next                 show the ONE next draft waiting for comment
#   drip.sh comment ID "text"    record a comment (the draft comes back revised)
#   drip.sh ready ID "who/when"  Jonathan's word "make the draft" → staged next (account/thread from the record)
#   drip.sh status               queue board
set -e
cd "$HOME/landtek"
ssh -N -L 15432:172.18.0.3:5432 landtek & T=$!; trap "kill $T 2>/dev/null" EXIT; sleep 3
set -a; . "$HOME/.landtek_db.env"; set +a   # secret lives in a 600 file, not here (Phase 0, 23 Oct 2026)
export PG_DSN="postgresql://${PGUSER}:${PGPASSWORD}@127.0.0.1:15432/n8n"
case "$1" in
  next)    python3 scripts/drip_draft_queue.py --fill --next ;;
  comment) python3 scripts/drip_draft_queue.py --comment "$2" "$3" ;;
  ready)   python3 scripts/drip_draft_queue.py --ready "$2" "$3" ;;
  status|*) python3 scripts/drip_draft_queue.py --status ;;
esac
