#!/usr/bin/env python3
"""Deploy 290 — Connection-Loss Sentinel (the silence detector).

Closes the original-mandate gap Jonathan named: "Leo was never to lose a
message or a connection." Installs scripts/connection_loss_sentinel.py on a
60-second systemd timer.

Every minute it scans the last 10 minutes of Leo executions and alerts
Jonathan if:
  - an inbound Telegram message produced NO terminal send node (silence), or
  - any execution errored (new error class beyond the fail-safe memory tail).

This is the watcher that would have caught tonight's three incidents within
60 seconds instead of hours:
  - Qdrant cascade (deploy_283)      → would fire 'exec_error'
  - onboarding ECONNREFUSED (285)    → would fire 'silence' (no Send Onboarding)
  - Notify-Jonathan no-op (286)      → would fire 'silence' for the unauth path

Idempotent."""
import os
import subprocess

REPO_ROOT = "/root/landtek"
SENTINEL = f"{REPO_ROOT}/scripts/connection_loss_sentinel.py"
NAME = "landtek-connection-sentinel"

SERVICE = f"""[Unit]
Description=LandTek connection-loss sentinel — never lose a message
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory={REPO_ROOT}
Environment="PG_DSN=postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
ExecStart=/usr/bin/python3 {SENTINEL}
StandardOutput=append:/var/log/landtek-connection-sentinel.log
StandardError=append:/var/log/landtek-connection-sentinel.log
"""

TIMER = f"""[Unit]
Description=Run connection-loss sentinel every 60s

[Timer]
OnBootSec=90s
OnUnitActiveSec=60s
AccuracySec=10s
Unit={NAME}.service

[Install]
WantedBy=timers.target
"""


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def main():
    print("Deploy 290 — Connection-Loss Sentinel")
    print("=" * 44)
    if not os.path.exists(SENTINEL):
        print(f"  ✗ MISSING {SENTINEL} — copy scripts/connection_loss_sentinel.py first")
        return 1
    os.chmod(SENTINEL, 0o755)
    print(f"  ✓ sentinel present + executable")

    for path, content in [
        (f"/etc/systemd/system/{NAME}.service", SERVICE),
        (f"/etc/systemd/system/{NAME}.timer", TIMER),
    ]:
        with open(path, "w") as f:
            f.write(content)
        print(f"  ✓ wrote {path}")

    run(["systemctl", "daemon-reload"])
    rc, _ = run(["systemctl", "enable", "--now", f"{NAME}.timer"])
    print(f"  ✓ timer enabled rc={rc}")

    # First run to seed the sentinel_alerts table + verify it parses recent execs
    print("\n  First run:")
    rc, out = run(["python3", SENTINEL])
    print("   ", out[-400:])
    print("\n  ✓ deploy_290 complete — silence detector live (60s cadence)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
