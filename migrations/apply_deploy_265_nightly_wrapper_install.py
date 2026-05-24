#!/usr/bin/env python3
"""Deploy 265 (companion) - install nightly wrapper + monitor.

Replaces /usr/local/bin/landtek-truth-tests-wrapper.sh (deploy_246) with
landtek_nightly_wrapper.sh that ALSO runs scripts/monitor_n8n_executions.py.

Idempotent. Run as root.
"""
import os
import subprocess
import sys

WRAPPER_SRC = "/root/landtek/scripts/landtek_nightly_wrapper.sh"
WRAPPER_DST = "/usr/local/bin/landtek-truth-tests-wrapper.sh"


def main():
    if os.geteuid() != 0:
        print("Run as root (sudo)")
        sys.exit(1)
    if not os.path.exists(WRAPPER_SRC):
        print(f"missing source {WRAPPER_SRC}")
        sys.exit(1)

    # Read, write, chmod
    with open(WRAPPER_SRC) as f:
        content = f.read()
    with open(WRAPPER_DST, "w") as f:
        f.write(content)
    os.chmod(WRAPPER_DST, 0o755)
    print(f"  installed {WRAPPER_DST}")

    # Trigger the timer once to confirm
    r = subprocess.run(
        ["systemctl", "start", "landtek-truth-tests.service"],
        capture_output=True, text=True
    )
    print(f"  start service: rc={r.returncode}")
    if r.stderr:
        print(f"    stderr: {r.stderr.strip()}")

    # Show last log lines
    print("\n  Recent log:")
    for log in ["/var/log/landtek/truth_tests.log", "/var/log/landtek/n8n_health.log"]:
        if os.path.exists(log):
            print(f"  --- {log} (last 5 lines) ---")
            r = subprocess.run(["tail", "-5", log], capture_output=True, text=True)
            print("    " + r.stdout.replace("\n", "\n    ").rstrip())


if __name__ == "__main__":
    main()
