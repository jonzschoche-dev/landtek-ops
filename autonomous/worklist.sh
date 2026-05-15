#!/usr/bin/env bash
# Show the "what to do when Gemini is paused" section + current pause state
echo "=== Current key state ==="
docker exec -i n8n-postgres-1 psql -U n8n -d n8n -c "
SELECT key_label,
       CASE WHEN cooldown_until > NOW() THEN 'PAUSED until ' || to_char(cooldown_until, 'HH24:MI UTC')
            ELSE 'available' END AS state,
       LEFT(notes, 60) AS notes
  FROM gemini_key_state;"

echo ""
echo "=== Tasks to do while paused ==="
sed -n '/^## When Gemini is paused/,/^## /p' /root/landtek/DIRECTIVE.md | head -60
