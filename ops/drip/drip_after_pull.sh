#!/bin/bash
# Runs right after every inbox pull (gmail-watcher every 15 min, jonzschoche backup sweep every 3 h) so an office's
# reply shows in the drip within hours, not at midnight (Jonathan, 23 Oct 2026).
#   1. ingest_email_bodies.py: new office e-mails become corpus documents (an office's reply = proof of receipt)
#   2. drip_log.py reconcile: logs replies and our sends nobody logged; a corpus proof starts or updates the clock
# Read/write to the database only; never sends. One run at a time (flock); a failure never fails the pull.
cd /root/landtek || exit 0
exec >> /var/log/landtek/drip-after-pull.log 2>&1
exec 9>/run/lock/drip_after_pull.lock
flock -n 9 || { echo "$(date -u '+%F %T') busy, skipped"; exit 0; }
echo "=== $(date -u '+%F %T') UTC after-pull ($1) ==="
/usr/bin/python3 ingest_email_bodies.py --since "$(date -u -d '2 days ago' +%F)" | grep -E 'created|linked' || true
/usr/bin/python3 scripts/drip_log.py reconcile --since "$(date -u -d '10 days ago' +%F)" || echo "reconcile FAILED"
exit 0
