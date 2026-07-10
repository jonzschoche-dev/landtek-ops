#!/usr/bin/env python3
"""deploy_841 — daily date-proposer scan (keeps the pulse's dark-item worklist live).

Runs `date_proposer.py --scan --apply` at 05:00 Manila (before the 05:30 pulse tick +
07:00 brief). SAFE TO ENABLE: the scan writes ONLY the date_proposals ledger — it NEVER
writes a date to the spine. Approvals stay operator-only (--approve). So this surfaces
new dark items + refreshes grounded proposals daily, but changes no matter/goal date on
its own. Enqueue-of-proposals, not commitment.

Idempotent; re-runnable.
"""
import os
import subprocess

LOG_DIR = "/var/log/landtek"

UNITS = {
    "/etc/systemd/system/landtek-date-proposer.service": """[Unit]
Description=LandTek date proposer — refresh the dark-item proposal ledger (no spine writes)
After=docker.service network-online.target

[Service]
Type=oneshot
WorkingDirectory=/root/landtek
ExecStart=/usr/bin/python3 /root/landtek/scripts/date_proposer.py --scan --apply
StandardOutput=append:/var/log/landtek/date_proposer.log
StandardError=append:/var/log/landtek/date_proposer.log
""",
    "/etc/systemd/system/landtek-date-proposer.timer": """[Unit]
Description=Daily date-proposer scan at 05:00 Asia/Manila

[Timer]
OnCalendar=*-*-* 05:00:00 Asia/Manila
Persistent=true
Unit=landtek-date-proposer.service

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
    subprocess.run(["systemctl", "enable", "--now", "landtek-date-proposer.timer"], check=True)
    print("✓ date-proposer scan LIVE — daily 05:00 Manila; ledger-only, approvals stay manual.")


if __name__ == "__main__":
    main()
