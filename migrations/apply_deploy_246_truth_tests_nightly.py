#!/usr/bin/env python3
"""Deploy 246 — install nightly truth_tests cron + log rotation.

Wires:
  - systemd timer running truth_tests/run_all.py every night at 03:00 UTC
  - logs to /var/log/landtek/truth_tests.log
  - on FAIL, writes a notification line to notifications/pending.txt
    (the bridge picks these up and surfaces them next session start)

Idempotent: re-creates units, doesn't double-install.
"""
import os
import subprocess
import sys
import textwrap


SERVICE_UNIT = "/etc/systemd/system/landtek-truth-tests.service"
TIMER_UNIT = "/etc/systemd/system/landtek-truth-tests.timer"
LOG_DIR = "/var/log/landtek"
LOG_PATH = f"{LOG_DIR}/truth_tests.log"

SERVICE_CONTENT = """[Unit]
Description=LandTek truth_tests nightly assertion run
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/root/landtek
ExecStart=/usr/local/bin/landtek-truth-tests-wrapper.sh
StandardOutput=append:/var/log/landtek/truth_tests.log
StandardError=append:/var/log/landtek/truth_tests.log

[Install]
WantedBy=multi-user.target
"""

TIMER_CONTENT = """[Unit]
Description=Run LandTek truth_tests nightly

[Timer]
OnCalendar=*-*-* 03:00:00 UTC
Persistent=true
Unit=landtek-truth-tests.service

[Install]
WantedBy=timers.target
"""

WRAPPER_SCRIPT = """#!/usr/bin/env bash
# landtek-truth-tests-wrapper.sh — nightly runner.
# Writes a notification on failure that the session-start hook picks up.

set -u
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
cd /root/landtek

echo ""
echo "=== truth_tests nightly run $TS ==="

if python3 truth_tests/run_all.py; then
    echo "$TS  truth_tests PASSED" >> /var/log/landtek/truth_tests.log
    # Successful runs don't notify
    exit 0
else
    rc=$?
    echo "$TS  truth_tests FAILED (rc=$rc)" >> /var/log/landtek/truth_tests.log
    # Notify next session
    mkdir -p /root/landtek/notifications
    {
        echo "[$TS] truth_tests FAILED — see /var/log/landtek/truth_tests.log"
        echo "  Check: tail -100 /var/log/landtek/truth_tests.log"
    } >> /root/landtek/notifications/pending.txt
    exit $rc
fi
"""


def write_file(path, content, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, mode)
    print(f"  ✓ wrote {path}")


def run(cmd):
    print(f"  $ {cmd}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.stdout.strip():
        print("    " + r.stdout.strip().replace("\n", "\n    "))
    if r.returncode != 0:
        print(f"    ✗ rc={r.returncode}: {r.stderr.strip()}")
    return r.returncode == 0


def main():
    print("Deploy 246 — install nightly truth_tests cron")
    print("=" * 60)

    if os.geteuid() != 0:
        print("  ⚠ not running as root — systemd units may not install.")
        print("    Re-run with: sudo python3 migrations/apply_deploy_246_truth_tests_nightly.py")
        sys.exit(1)

    # 1. Log dir
    os.makedirs(LOG_DIR, exist_ok=True)
    print(f"  ✓ {LOG_DIR}/ exists")

    # 2. Wrapper script
    write_file("/usr/local/bin/landtek-truth-tests-wrapper.sh", WRAPPER_SCRIPT, mode=0o755)

    # 3. Service unit
    write_file(SERVICE_UNIT, SERVICE_CONTENT)

    # 4. Timer unit
    write_file(TIMER_UNIT, TIMER_CONTENT)

    # 5. Reload + enable
    if not run("systemctl daemon-reload"):
        sys.exit(1)
    if not run("systemctl enable --now landtek-truth-tests.timer"):
        sys.exit(1)

    # 6. Show status
    print()
    run("systemctl status landtek-truth-tests.timer --no-pager | head -20")
    print()
    run("systemctl list-timers landtek-truth-tests.timer --no-pager")

    print()
    print("  ✓ Nightly truth_tests installed.")
    print("    Next fire: see 'NEXT' column above.")
    print(f"    Logs:     {LOG_PATH}")
    print(f"    Failures notify: /root/landtek/notifications/pending.txt")


if __name__ == "__main__":
    main()
