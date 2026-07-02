#!/usr/bin/env python3
"""deploy_649 — install the calendar-sync systemd timer (always-on Agenda Engine).

Installs a push timer (every 15 min) and a nightly pull-reconcile for
scripts/calendar_sync.py. SELF-GUARDING: the timers are only enabled/started when
CALENDAR_REFRESH_TOKEN is present in /root/landtek/.env. Before the token exists the
units are written but left disabled — so a run never produces a 'failed' unit
(honors the systemctl --failed == 0 invariant). Re-run this after minting the token
(scripts/mint_calendar_token.py) to flip the timers on.

Idempotent: safe to run repeatedly.
"""
import os
import subprocess

LOG_DIR = "/var/log/landtek"
ENV_PATH = "/root/landtek/.env"

UNITS = {
    "/etc/systemd/system/landtek-calendar-sync.service": """[Unit]
Description=LandTek Agenda Engine — push Postgres agenda to Google Calendar
After=docker.service network-online.target

[Service]
Type=oneshot
WorkingDirectory=/root/landtek
ExecStart=/usr/bin/python3 /root/landtek/scripts/calendar_sync.py --apply --daemon
StandardOutput=append:/var/log/landtek/calendar_sync.log
StandardError=append:/var/log/landtek/calendar_sync.log
""",
    "/etc/systemd/system/landtek-calendar-sync.timer": """[Unit]
Description=Run LandTek calendar push every 15 minutes

[Timer]
OnBootSec=3min
OnUnitActiveSec=15min
AccuracySec=30s
Unit=landtek-calendar-sync.service

[Install]
WantedBy=timers.target
""",
    "/etc/systemd/system/landtek-calendar-sync-pull.service": """[Unit]
Description=LandTek Agenda Engine — reconcile manual Google Calendar edits back
After=docker.service network-online.target

[Service]
Type=oneshot
WorkingDirectory=/root/landtek
ExecStart=/usr/bin/python3 /root/landtek/scripts/calendar_sync.py --pull --apply --daemon
StandardOutput=append:/var/log/landtek/calendar_sync.log
StandardError=append:/var/log/landtek/calendar_sync.log
""",
    "/etc/systemd/system/landtek-calendar-sync-pull.timer": """[Unit]
Description=Nightly reconcile of manual Google Calendar edits

[Timer]
OnCalendar=*-*-* 18:30:00 UTC
Persistent=true
Unit=landtek-calendar-sync-pull.service

[Install]
WantedBy=timers.target
""",
}

TIMERS = ["landtek-calendar-sync.timer", "landtek-calendar-sync-pull.timer"]


def has_calendar_token():
    try:
        with open(ENV_PATH) as f:
            for line in f:
                if line.startswith("CALENDAR_REFRESH_TOKEN=") and line.strip() != "CALENDAR_REFRESH_TOKEN=":
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

    if has_calendar_token():
        for t in TIMERS:
            subprocess.run(["systemctl", "enable", "--now", t], check=True)
            print(f"enabled + started {t}")
        print("\n✓ Agenda Engine live — pushing every 15 min, nightly pull-reconcile.")
    else:
        print("\n⚠ CALENDAR_REFRESH_TOKEN not set in /root/landtek/.env.")
        print("  Units installed but LEFT DISABLED (no failing units).")
        print("  1) python3 scripts/mint_calendar_token.py   # then add the line to .env")
        print("  2) python3 scripts/calendar_sync.py --apply  # verify one manual run")
        print("  3) re-run this migration to enable the timers.")


if __name__ == "__main__":
    main()
