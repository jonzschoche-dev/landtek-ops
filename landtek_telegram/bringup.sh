#!/usr/bin/env bash
# bringup.sh — install + start the bulletproof Telegram pipeline.
#
# Steps:
#   1. Apply migration (telegram_inbox + telegram_outbox_retry tables).
#   2. Install systemd units.
#   3. Add nginx location block + reload nginx.
#   4. Start inbox + router services.
#   5. Point Telegram webhook at the new URL.
#   6. Smoke-test by checking healthz + inbox writes.
#
# Re-runnable. Idempotent.

set -euo pipefail

cd /root/landtek

echo "[bringup] step 1: apply migration"
python3 migrations/apply_deploy_369_telegram_inbox.py

echo "[bringup] step 2: install systemd units"
cp landtek_telegram/landtek-tg-inbox.service /etc/systemd/system/
cp landtek_telegram/landtek-tg-router.service /etc/systemd/system/
systemctl daemon-reload

echo "[bringup] step 3: nginx config"
# Find the leo.hayuma.org server block, drop in our snippet
NGINX_CONF=$(grep -rl "server_name.*leo\.hayuma\.org" /etc/nginx/ 2>/dev/null | head -1 || true)
if [ -z "$NGINX_CONF" ]; then
    echo "  ! couldn't auto-find leo.hayuma.org nginx config — paste landtek_telegram/nginx_landtek_tg.conf manually into the server block"
else
    echo "  found nginx config: $NGINX_CONF"
    if ! grep -q "location = /landtek/tg" "$NGINX_CONF"; then
        # Insert before the closing brace of the server block
        SNIPPET=$(cat landtek_telegram/nginx_landtek_tg.conf)
        # Make a backup
        cp "$NGINX_CONF" "${NGINX_CONF}.pre-landtek-tg.bak"
        # Use awk to insert before the last closing brace
        awk -v snip="$SNIPPET" '
            { lines[NR] = $0 }
            END {
                # Find last } and insert snippet before it
                for (i = NR; i >= 1; i--) {
                    if (lines[i] ~ /^[[:space:]]*}[[:space:]]*$/ && inserted != 1) {
                        print snip
                        print lines[i]
                        inserted = 1
                    } else {
                        print lines[i]
                    }
                }
            }
        ' "${NGINX_CONF}.pre-landtek-tg.bak" > "$NGINX_CONF"
        nginx -t && systemctl reload nginx
        echo "  nginx reloaded with /landtek/tg location"
    else
        echo "  /landtek/tg location already present, skipping"
    fi
fi

echo "[bringup] step 4: start services"
systemctl enable --now landtek-tg-inbox.service
systemctl enable --now landtek-tg-router.service
sleep 3
systemctl is-active landtek-tg-inbox.service
systemctl is-active landtek-tg-router.service

echo "[bringup] step 5: healthz check"
curl -fsS http://127.0.0.1:8766/healthz | python3 -m json.tool

echo "[bringup] step 6: point Telegram webhook to the new URL"
TOKEN=$(grep -E "^(TG_BOT_TOKEN|TELEGRAM_BOT_TOKEN|BOT_TOKEN)=" /root/landtek/.env | head -1 | cut -d= -f2- | tr -d "\"'\''")
NEW_URL="https://leo.hayuma.org/landtek/tg"
echo "  setting webhook -> $NEW_URL"
curl -s "https://api.telegram.org/bot$TOKEN/setWebhook?url=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$NEW_URL")&allowed_updates=%5B%22message%22%2C%22edited_message%22%2C%22callback_query%22%2C%22my_chat_member%22%2C%22chat_member%22%5D" | python3 -m json.tool
echo "  current webhook info:"
curl -s "https://api.telegram.org/bot$TOKEN/getWebhookInfo" | python3 -m json.tool

echo
echo "[bringup] DONE. Send a Telegram message; check rows arrive:"
echo "  docker exec -i n8n-postgres-1 psql -U n8n -d n8n -c \"SELECT id, chat_id, text_content, processed_at, handler, handler_outcome FROM telegram_inbox ORDER BY id DESC LIMIT 5\""
