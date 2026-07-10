#!/usr/bin/env python3
"""deploy_839 — the pulse tick timer (calendar_orchestrator, daily 05:30 Manila).

The calendar-is-the-pulse inversion made autonomous: every morning BEFORE the 07:00
brief, the pulse walks the agenda spine and fires `deliverable` work orders (T-14 rule)
into the supervisor's FAIL-CLOSED state machine. Enqueue-only — the tick never executes
a step and never sends anything; every order ends in a human-held T3 certify.

Enabled immediately (unlike the notification timers there is no external side effect to
gate — the output is internal queued work). Idempotent; re-runnable.
"""
import os
import subprocess

LOG_DIR = "/var/log/landtek"

UNITS = {
    "/etc/systemd/system/landtek-pulse-orchestrator.service": """[Unit]
Description=LandTek pulse — dated items fire fail-closed work orders (T-14 prep)
After=docker.service network-online.target

[Service]
Type=oneshot
WorkingDirectory=/root/landtek
ExecStart=/usr/bin/python3 /root/landtek/scripts/calendar_orchestrator.py --apply
StandardOutput=append:/var/log/landtek/pulse_orchestrator.log
StandardError=append:/var/log/landtek/pulse_orchestrator.log
""",
    "/etc/systemd/system/landtek-pulse-orchestrator.timer": """[Unit]
Description=Daily pulse tick at 05:30 Asia/Manila (before the 07:00 brief)

[Timer]
OnCalendar=*-*-* 05:30:00 Asia/Manila
Persistent=true
Unit=landtek-pulse-orchestrator.service

[Install]
WantedBy=timers.target
""",
}


def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    for path, content in UNITS.items():
        with open(path, "w") as f:
            f.write(content)
        print(f"wrote {path}")
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "--now", "landtek-pulse-orchestrator.timer"], check=True)
    print("✓ pulse tick LIVE — daily 05:30 Manila; enqueue-only, fail-closed downstream.")


if __name__ == "__main__":
    main()
