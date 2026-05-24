#!/usr/bin/env python3
"""Deploy 269 - install webhook_watchdog as a systemd timer (every 60s).

Telegram webhook has spontaneously deregistered 3x today. Until root cause
is known, run a watchdog every 60s that re-registers when URL goes empty.

Idempotent. Run as root.
"""
import os
import subprocess
import sys

SERVICE_PATH = "/etc/systemd/system/landtek-webhook-watchdog.service"
TIMER_PATH = "/etc/systemd/system/landtek-webhook-watchdog.timer"

SERVICE = """[Unit]
Description=Landtek Telegram webhook auto-recovery
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/root/landtek
ExecStart=/usr/bin/python3 /root/landtek/scripts/webhook_watchdog.py
StandardOutput=append:/var/log/landtek/webhook_watchdog.log
StandardError=append:/var/log/landtek/webhook_watchdog.log
"""

TIMER = """[Unit]
Description=Run Landtek webhook watchdog every 60 seconds

[Timer]
OnBootSec=30s
OnUnitActiveSec=60s
AccuracySec=10s
Unit=landtek-webhook-watchdog.service

[Install]
WantedBy=timers.target
"""


def write(path, content, mode=0o644):
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, mode)
    print(f"  wrote {path}")


def main():
    if os.geteuid() != 0:
        print("Run as root")
        sys.exit(1)

    os.makedirs("/var/log/landtek", exist_ok=True)
    write(SERVICE_PATH, SERVICE)
    write(TIMER_PATH, TIMER)

    for cmd in (
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", "--now", "landtek-webhook-watchdog.timer"],
    ):
        r = subprocess.run(cmd, capture_output=True, text=True)
        print(f"  $ {' '.join(cmd)} rc={r.returncode}")
        if r.stderr.strip():
            print(f"    stderr: {r.stderr.strip()[:300]}")

    # Show status
    r = subprocess.run(
        ["systemctl", "list-timers", "landtek-webhook-watchdog.timer", "--no-pager"],
        capture_output=True, text=True,
    )
    print("\n  Timer state:")
    print("  " + r.stdout.replace("\n", "\n  ").rstrip())

    print("\n  First watchdog run now (to verify it works):")
    r = subprocess.run(
        ["python3", "/root/landtek/scripts/webhook_watchdog.py"],
        capture_output=True, text=True,
    )
    print("  " + r.stdout.replace("\n", "\n  ").rstrip())
    print(f"  rc={r.returncode} (0=healthy, 1=just_recovered, 2=fail)")


if __name__ == "__main__":
    main()
