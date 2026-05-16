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



def patch_workflow_dual(workflow_id: str, nodes=None, connections=None):
    """Update workflow_entity AND workflow_history.latest, then reload via n8n REST API.

    n8n's runtime reads from workflow_history.latest (per deploy_057g). Updating
    only workflow_entity leaves the runtime on the stale snapshot.

    Reload mechanism (HARDENED 2026-05-16 — incident report below):
    Uses n8n's REST API deactivate+activate cycle, NOT a DB-level active=on/off
    toggle. The DB-toggle path silently strips the Telegram webhook's secret_token,
    causing every incoming Telegram POST to return 403 'Provided secret is not
    valid' — Leo appears alive (URL set) but rejects all messages. The REST API
    path re-registers the webhook WITH a fresh secret that n8n then validates.

    Incident 2026-05-16 ~00:00 UTC: deploy_074 used the DB-toggle path. Watchdog
    saw empty URL, called Telegram setWebhook directly, restored URL but wiped
    secret. Leo silently dead for ~10 min until manual deactivate+activate via
    n8n REST API. Both that hole (watchdog) and this one (patch_workflow_dual)
    are now closed.
    """
    import psycopg2, json as _json, urllib.request, urllib.error, time as _time
    conn = psycopg2.connect(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
    cur = conn.cursor()
    if nodes is not None:
        cur.execute('UPDATE workflow_entity SET nodes=%s::jsonb, "updatedAt"=now() WHERE id=%s',
                    (_json.dumps(nodes), workflow_id))
        cur.execute("""UPDATE workflow_history SET nodes=%s::jsonb
                         WHERE "workflowId"=%s AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""",
                    (_json.dumps(nodes), workflow_id, workflow_id))
    if connections is not None:
        cur.execute('UPDATE workflow_entity SET connections=%s::jsonb, "updatedAt"=now() WHERE id=%s',
                    (_json.dumps(connections), workflow_id))
        cur.execute("""UPDATE workflow_history SET connections=%s::jsonb
                         WHERE "workflowId"=%s AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""",
                    (_json.dumps(connections), workflow_id, workflow_id))
    conn.commit()
    cur.close(); conn.close()

    # Reload via n8n REST API (NOT DB-level active toggle — see docstring)
    api_key = _read_n8n_api_key()
    base = f"http://localhost:5678/api/v1/workflows/{workflow_id}"
    for action in ("deactivate", "activate"):
        req = urllib.request.Request(
            f"{base}/{action}", method="POST",
            headers={"X-N8N-API-KEY": api_key},
        )
        try:
            urllib.request.urlopen(req, timeout=15).read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"n8n REST API {action} failed: HTTP {e.code} {e.reason}")
        _time.sleep(2)

    print(f"  patch_workflow_dual: workflow_entity + workflow_history.latest synced + reloaded via n8n REST API for {workflow_id}")


def _read_n8n_api_key():
    """Read N8N_API_KEY from /root/landtek/.env (chmod 600)."""
    with open("/root/landtek/.env") as f:
        for line in f:
            if line.startswith("N8N_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("N8N_API_KEY not found in /root/landtek/.env")
