#!/bin/bash
cd /root/landtek
# Check if doc 389 still has no chunks
ORPHAN=$(docker exec n8n-postgres-1 psql -U n8n -d n8n -tA -c \
  "SELECT id FROM documents WHERE id = 389 AND (chunk_count IS NULL OR chunk_count = 0)")
if [ -z "$ORPHAN" ]; then
  echo "$(date -u): doc 389 done, removing cron"
  crontab -l | grep -v cron_retry_orphans | crontab -
  exit 0
fi
python3 /root/landtek/retry_doc_389.py >> /root/landtek/retry_orphans.log 2>&1
