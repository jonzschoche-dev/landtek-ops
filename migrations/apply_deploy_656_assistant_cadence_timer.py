#!/usr/bin/env python3
"""deploy_656 — install the scheduling-assistant reminder timers (self-guarding).

Morning week-ahead brief (07:00 Asia/Manila) + evening day-before nudge (18:00 Manila),
running scripts/assistant_cadence.py. SELF-GUARDING: timers are only enabled/started when
ASSISTANT_CADENCE_LIVE=1 is present in /root/landtek/.env — so the assistant never messages
Jonathan's phone until he explicitly flips it on. Before that the units are written but
left disabled (no failing units, no surprise messages).

Idempotent. Re-run after setting ASSISTANT_CADENCE_LIVE=1 to go live.
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
}

TIMERS = ["landtek-assistant-morning.timer", "landtek-assistant-evening.timer"]


def cadence_live():
    try:
        with open(ENV_PATH) as f:
            for line in f:
                if line.strip() == "ASSISTANT_CADENCE_LIVE=1":
                    return True
    except FileNotFoundError:
        pass
    return False


def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    for path, content in UNITS.items():
        with open(path, "w") as f:
            f.write(content)
        print(f"wrote {path}")
    subprocess.run(["systemctl", "daemon-reload"], check=True)

    if cadence_live():
        for t in TIMERS:
            subprocess.run(["systemctl", "enable", "--now", t], check=True)
            print(f"enabled + started {t}")
        print("\n✓ Reminder cadence LIVE — 07:00 brief + 18:00 nudge (Asia/Manila).")
    else:
        print("\n⚠ ASSISTANT_CADENCE_LIVE=1 not set in /root/landtek/.env.")
        print("  Timers installed but LEFT DISABLED (nothing will message your phone).")
        print("  Preview safely any time: python3 scripts/assistant_cadence.py --dry")
        print("  Go live: add ASSISTANT_CADENCE_LIVE=1 to .env, then re-run this migration.")


if __name__ == "__main__":
    main()
