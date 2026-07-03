#!/usr/bin/env python3
"""deploy_656 — install the scheduling-assistant reminder timers (self-guarding).

Morning week-ahead brief (07:00 Asia/Manila) + evening day-before nudge (18:00 Manila),
running scripts/assistant_cadence.py, over TWO independently-gated channels:
  - Telegram — enabled only when ASSISTANT_CADENCE_LIVE=1 in /root/landtek/.env
  - Email (to Jonathan, self only) — enabled only when ASSISTANT_EMAIL_LIVE=1

SELF-GUARDING: each channel's timers are only enabled/started when its flag is set, so
nothing reaches Jonathan's phone or inbox until he flips the matching switch. Before that
the units are written but left disabled (no failing units, no surprise messages).

Idempotent. Re-run after setting either flag to go live on that channel.
"""
import os
import subprocess

LOG_DIR = "/var/log/landtek"
ENV_PATH = "/root/landtek/.env"

UNITS = {
    "/etc/systemd/system/landtek-assistant-morning.service": """[Unit]
Description=LandTek assistant — morning week-ahead brief
After=docker.service network-online.target

[Service]
Type=oneshot
WorkingDirectory=/root/landtek
ExecStart=/usr/bin/python3 /root/landtek/scripts/assistant_cadence.py --morning
StandardOutput=append:/var/log/landtek/assistant_cadence.log
StandardError=append:/var/log/landtek/assistant_cadence.log
""",
    "/etc/systemd/system/landtek-assistant-morning.timer": """[Unit]
Description=Morning brief at 07:00 Asia/Manila

[Timer]
OnCalendar=*-*-* 07:00:00 Asia/Manila
Persistent=true
Unit=landtek-assistant-morning.service

[Install]
WantedBy=timers.target
""",
    "/etc/systemd/system/landtek-assistant-evening.service": """[Unit]
Description=LandTek assistant — evening day-before nudge
After=docker.service network-online.target

[Service]
Type=oneshot
WorkingDirectory=/root/landtek
ExecStart=/usr/bin/python3 /root/landtek/scripts/assistant_cadence.py --evening
StandardOutput=append:/var/log/landtek/assistant_cadence.log
StandardError=append:/var/log/landtek/assistant_cadence.log
""",
    "/etc/systemd/system/landtek-assistant-evening.timer": """[Unit]
Description=Day-before nudge at 18:00 Asia/Manila

[Timer]
OnCalendar=*-*-* 18:00:00 Asia/Manila
Persistent=true
Unit=landtek-assistant-evening.service

[Install]
WantedBy=timers.target
""",
    # ── Email channel (self only) ──────────────────────────────────────
    "/etc/systemd/system/landtek-assistant-morning-email.service": """[Unit]
Description=LandTek assistant — morning brief via email
After=docker.service network-online.target

[Service]
Type=oneshot
WorkingDirectory=/root/landtek
ExecStart=/usr/bin/python3 /root/landtek/scripts/assistant_cadence.py --morning --email
StandardOutput=append:/var/log/landtek/assistant_cadence.log
StandardError=append:/var/log/landtek/assistant_cadence.log
""",
    "/etc/systemd/system/landtek-assistant-morning-email.timer": """[Unit]
Description=Morning brief via email at 07:00 Asia/Manila

[Timer]
OnCalendar=*-*-* 07:00:00 Asia/Manila
Persistent=true
Unit=landtek-assistant-morning-email.service

[Install]
WantedBy=timers.target
""",
    "/etc/systemd/system/landtek-assistant-evening-email.service": """[Unit]
Description=LandTek assistant — day-before nudge via email
After=docker.service network-online.target

[Service]
Type=oneshot
WorkingDirectory=/root/landtek
ExecStart=/usr/bin/python3 /root/landtek/scripts/assistant_cadence.py --evening --email
StandardOutput=append:/var/log/landtek/assistant_cadence.log
StandardError=append:/var/log/landtek/assistant_cadence.log
""",
    "/etc/systemd/system/landtek-assistant-evening-email.timer": """[Unit]
Description=Day-before nudge via email at 18:00 Asia/Manila

[Timer]
OnCalendar=*-*-* 18:00:00 Asia/Manila
Persistent=true
Unit=landtek-assistant-evening-email.service

[Install]
WantedBy=timers.target
""",
}

TELEGRAM_TIMERS = ["landtek-assistant-morning.timer", "landtek-assistant-evening.timer"]
EMAIL_TIMERS = ["landtek-assistant-morning-email.timer", "landtek-assistant-evening-email.timer"]


def flag_set(name):
    try:
        with open(ENV_PATH) as f:
            for line in f:
                if line.strip() == f"{name}=1":
                    return True
    except FileNotFoundError:
        pass
    return False


def _apply(group, live, label, flag):
    if live:
        for t in group:
            subprocess.run(["systemctl", "enable", "--now", t], check=True)
            print(f"enabled + started {t}")
        print(f"✓ {label} cadence LIVE — 07:00 brief + 18:00 nudge (Asia/Manila).")
    else:
        print(f"⚠ {flag}=1 not set — {label} timers installed but DISABLED.")


def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    for path, content in UNITS.items():
        with open(path, "w") as f:
            f.write(content)
        print(f"wrote {path}")
    subprocess.run(["systemctl", "daemon-reload"], check=True)

    _apply(TELEGRAM_TIMERS, flag_set("ASSISTANT_CADENCE_LIVE"), "Telegram", "ASSISTANT_CADENCE_LIVE")
    _apply(EMAIL_TIMERS, flag_set("ASSISTANT_EMAIL_LIVE"), "Email", "ASSISTANT_EMAIL_LIVE")
    print("\nPreview safely any time: python3 scripts/assistant_cadence.py --dry "
          "(add --email for the email version). Flip a channel on by setting its flag in "
          ".env and re-running this migration.")


if __name__ == "__main__":
    main()
