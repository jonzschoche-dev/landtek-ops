#!/usr/bin/env python3
"""deploy_837 — install the scheduling-assistant SPONGE (two-way inbound) — self-guarding.

Installs landtek-assistant-inbound.service (long-poll daemon on the DEDICATED assistant
bot). SELF-GUARDING like every assistant unit: the service is only enabled/started when
ASSISTANT_BOT_TOKEN is present in /root/landtek/.env. Before that it is installed but
disabled — no failing units, nothing listening.

On activation (token present) this also:
  * registers/updates the `assistant_telegram` row in `channels` (active=true)
  * writes a `channel_audit` activation record (invariant A30 — auditable activation)

Idempotent. Re-run after adding the token to go live. To create the bot:
@BotFather → /newbot → name it (e.g. "LandTek Assistant") → copy the token →
add `ASSISTANT_BOT_TOKEN=<token>` to /root/landtek/.env → re-run this migration.
"""
import json
import os
import subprocess

import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
ENV_PATH = "/root/landtek/.env"
LOG_DIR = "/var/log/landtek"
CHANNEL_NAME = "assistant_telegram"

UNIT_PATH = "/etc/systemd/system/landtek-assistant-inbound.service"
UNIT = """[Unit]
Description=LandTek scheduling assistant — inbound sponge (dedicated bot, long-poll)
After=docker.service network-online.target

[Service]
Type=simple
WorkingDirectory=/root/landtek
ExecStart=/usr/bin/python3 /root/landtek/scripts/assistant_inbound.py --daemon
Restart=always
RestartSec=30
StandardOutput=append:/var/log/landtek/assistant_inbound.log
StandardError=append:/var/log/landtek/assistant_inbound.log

[Install]
WantedBy=multi-user.target
"""


def token_present():
    try:
        with open(ENV_PATH) as f:
            for line in f:
                if line.startswith("ASSISTANT_BOT_TOKEN=") and len(line.strip()) > len("ASSISTANT_BOT_TOKEN="):
                    return True
    except FileNotFoundError:
        pass
    return False


def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(UNIT_PATH, "w") as f:
        f.write(UNIT)
    print(f"wrote {UNIT_PATH}")
    subprocess.run(["systemctl", "daemon-reload"], check=True)

    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    # register the channel row (inactive until token) — assistant_inbound.py also
    # self-provisions, but the registry row should exist ahead of first run
    cur.execute("SELECT id FROM channels WHERE name=%s", (CHANNEL_NAME,))
    row = cur.fetchone()
    if not row:
        cur.execute(
            "INSERT INTO channels (name, provider, auth_secret_ref, active, notes) "
            "VALUES (%s,'BotAPI','ASSISTANT_BOT_TOKEN', false, "
            "'Dedicated scheduling-assistant bot — internal-only (operator chat). NOT @LeoLandTekBot.') "
            "RETURNING id", (CHANNEL_NAME,))
        row = cur.fetchone()
        print(f"registered channels row '{CHANNEL_NAME}' (id {row[0]}, inactive)")
    ch_id = row[0]

    if token_present():
        cur.execute("UPDATE channels SET active=true WHERE id=%s AND NOT active", (ch_id,))
        activated_now = cur.rowcount > 0
        if activated_now:
            cur.execute(
                "INSERT INTO channel_audit (channel_id, event_type, payload, result) "
                "VALUES (%s,'activation',%s,'activated')",
                (ch_id, json.dumps({
                    "by": "apply_deploy_837_assistant_inbound",
                    "reason": "ASSISTANT_BOT_TOKEN provisioned by operator",
                    "scope": "internal-only (operator chat 6513067717); strangers logged+ignored",
                })))
            print("channels.active=true + channel_audit activation row written (A30)")
        conn.commit()
        subprocess.run(["systemctl", "enable", "--now", "landtek-assistant-inbound.service"], check=True)
        print("\n✓ SPONGE LIVE — message the assistant bot from Telegram. "
              "Try: \"what's on\" · \"hearing moved to Aug 20\" · anything (it keeps notes).")
    else:
        conn.commit()
        print("\n⚠ ASSISTANT_BOT_TOKEN not set — service installed but LEFT DISABLED.")
        print("  1) In Telegram: @BotFather → /newbot → e.g. \"LandTek Assistant\"")
        print("  2) Add ASSISTANT_BOT_TOKEN=<token> to /root/landtek/.env (chmod 600)")
        print("  3) Re-run this migration — it enables the daemon + audits the activation.")
    conn.close()


if __name__ == "__main__":
    main()
