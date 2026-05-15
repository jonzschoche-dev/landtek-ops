#!/usr/bin/env python3
"""Deploy helpers for LandTek ops.

Usage from a patch script:

    import sys; sys.path.insert(0, "/root/landtek")
    from deploy_helpers import commit_deploy
    # ... do deploy work ...
    commit_deploy("045", "one-line summary of what changed")

Or from the command line, after running a deploy manually:

    /root/landtek/deploy_helpers.py 045 "one-line summary"

What commit_deploy does:
  1. git add -A (.gitignore keeps secrets out)
  2. git commit -m "deploy_NNN: <summary>" --allow-empty
  3. git push origin main

Push failures RAISE (not swallowed) so you notice when the safety net breaks.
Empty commits are allowed so even a metadata-only deploy registers a marker
in `git log` for the audit trail.

Skips push when LANDTEK_NO_PUSH=1 is set (useful for offline / dry-run).
"""
from __future__ import annotations
import os
import subprocess
import sys
from datetime import datetime, timezone

REPO_DIR = "/root/landtek"


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=REPO_DIR, capture_output=True, text=True, check=check)


def commit_deploy(deploy_id: str, summary: str) -> str:
    """Stage everything, commit as 'deploy_<id>: <summary>', push to origin/main.

    Returns the new commit hash. Raises CalledProcessError on git/push failure.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Stage
    _run(["git", "add", "-A"])

    # 2. Commit (allow empty so metadata-only deploys still register)
    msg = f"deploy_{deploy_id}: {summary}\n\nCommitted at {ts} UTC by deploy_helpers.commit_deploy()."
    commit_res = subprocess.run(
        ["git", "commit", "-m", msg, "--allow-empty"],
        cwd=REPO_DIR, capture_output=True, text=True
    )
    if commit_res.returncode not in (0, 1):
        raise subprocess.CalledProcessError(
            commit_res.returncode, commit_res.args,
            output=commit_res.stdout, stderr=commit_res.stderr
        )

    # 3. Push (unless dry-run env var set)
    if os.environ.get("LANDTEK_NO_PUSH") == "1":
        print(f"  [dry-run] LANDTEK_NO_PUSH=1 — skipping push")
    else:
        push_res = _run(["git", "push", "origin", "main"], check=False)
        if push_res.returncode != 0:
            raise RuntimeError(
                f"git push failed (exit {push_res.returncode}):\n"
                f"STDOUT: {push_res.stdout}\n"
                f"STDERR: {push_res.stderr}"
            )

    # 4. Return new commit hash
    rev = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    print(f"  deploy_{deploy_id} committed: {rev[:8]} -> origin/main")
    return rev


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: deploy_helpers.py <deploy_id> <summary>", file=sys.stderr)
        sys.exit(2)
    commit_deploy(sys.argv[1], " ".join(sys.argv[2:]))
