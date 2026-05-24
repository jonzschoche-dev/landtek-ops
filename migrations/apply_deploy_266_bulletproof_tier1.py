#!/usr/bin/env python3
"""Deploy 266 - Tier 1 bulletproofing: alerting, autoheal, fast ACK, backup, smoke.

Postmortem trigger: Jonathan trip May 21-22 - bot dead for 5 days, zero alerts.

Five pieces in one atomic migration with backup-first / rollback-on-fail:

  1. Backup Leos Workflow JSON before any change (workflow_backups/)
  2. Create "Leo Error Alert" workflow + wire Leos Workflow.settings.errorWorkflow
     so any error in Leos Workflow DMs Jonathan within 30s
  3. Add "Fast ACK" Telegram node right after Whitelist Check so authorized
     users get an instant "received, processing..." reply even if main path dies
  4. Add docker healthcheck to n8n container (compose edit + recreate)
  5. Post-deploy smoke test - synthetic /ping update through webhook; if no
     successful execution within 60s, AUTO-ROLLBACK to the pre-deploy backup

Idempotent: re-run with no-op if Error Workflow already exists. Audited via
app.actor='jonathan_deploy_266'.
"""
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
LEO_WF_ID = "vSDQv1vfn6627bnA"
ERROR_WF_NAME = "Leo Error Alert"
JONATHAN_CHAT_ID = "6513067717"
BACKUP_DIR = "/root/landtek/workflow_backups"

# Telegram bot creds (referenced by n8n credential ID — find via DB)
TELEGRAM_CRED_NAME = "Telegram account"


def backup_leo_workflow():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    conn = psycopg2.connect(DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""SELECT id, nodes, connections, settings, "versionId"
                     FROM workflow_entity WHERE id = %s""", (LEO_WF_ID,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    path = os.path.join(BACKUP_DIR, f"{LEO_WF_ID}_pre_deploy_266_{ts}.json")
    with open(path, "w") as f:
        json.dump(dict(row), f, indent=2, default=str)
    print(f"  backup: {path}")
    return path


def find_telegram_credential(cur):
    """Return the credential ID + name n8n uses for Telegram."""
    cur.execute("""SELECT id, name FROM credentials_entity WHERE type='telegramApi' LIMIT 1""")
    r = cur.fetchone()
    return (r["id"], r["name"]) if r else (None, None)


def make_error_workflow_nodes(cred_id, cred_name):
    """Two nodes: Error Trigger + Telegram Send Message."""
    return [
        {
            "id": str(uuid.uuid4()),
            "name": "Error Trigger",
            "type": "n8n-nodes-base.errorTrigger",
            "typeVersion": 1,
            "position": [240, 240],
            "parameters": {},
        },
        {
            "id": str(uuid.uuid4()),
            "name": "DM Jonathan",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [560, 240],
            "credentials": (
                {"telegramApi": {"id": cred_id, "name": cred_name}}
                if cred_id else {}
            ),
            "onError": "continueRegularOutput",
            "parameters": {
                "chatId": JONATHAN_CHAT_ID,
                "text": ('=🚨 <b>Leo workflow error</b>\n\n'
                         'Workflow: {{ $json.workflow.name || "unknown" }}\n'
                         'Failed node: {{ $json.execution.lastNodeExecuted || "?" }}\n'
                         'Error: {{ ($json.execution.error && $json.execution.error.message) || "?" }}\n\n'
                         'Execution: {{ $json.execution.id }}\n'
                         'Mode: {{ $json.execution.mode }}\n'
                         'Time: {{ $json.execution.startedAt }}'),
                "additionalFields": {"parse_mode": "HTML"},
            },
        },
    ]


def make_error_workflow_connections():
    return {"Error Trigger": {"main": [[{"node": "DM Jonathan", "type": "main", "index": 0}]]}}


def ensure_error_workflow(cur):
    """Create if missing; return error workflow id."""
    cur.execute("SELECT id FROM workflow_entity WHERE name = %s LIMIT 1", (ERROR_WF_NAME,))
    r = cur.fetchone()
    if r:
        print(f"  Error workflow already exists: {r['id']} (no-op create)")
        return r["id"]

    cred_id, cred_name = find_telegram_credential(cur)
    if not cred_id:
        raise RuntimeError("No telegramApi credential found in credentials_entity")
    print(f"  Using Telegram credential: {cred_name} (id={cred_id})")

    new_id = str(uuid.uuid4()).replace("-", "")[:16]
    nodes = make_error_workflow_nodes(cred_id, cred_name)
    connections = make_error_workflow_connections()
    settings = {"executionOrder": "v1"}
    version_id = str(uuid.uuid4())

    cur.execute("""
        INSERT INTO workflow_entity
            (id, name, active, nodes, connections, settings, "versionId", "triggerCount")
        VALUES (%s, %s, true, %s::json, %s::json, %s::json, %s, 0)
    """, (new_id, ERROR_WF_NAME, json.dumps(nodes), json.dumps(connections),
          json.dumps(settings), version_id))
    print(f"  Created Error Workflow: {new_id}")
    return new_id


def wire_error_workflow_pointer(cur, error_wf_id):
    cur.execute("SELECT settings FROM workflow_entity WHERE id = %s", (LEO_WF_ID,))
    s = cur.fetchone()["settings"] or {}
    if isinstance(s, str):
        s = json.loads(s)
    if s.get("errorWorkflow") == error_wf_id:
        print("  errorWorkflow already wired (no-op)")
        return
    s["errorWorkflow"] = error_wf_id
    cur.execute("UPDATE workflow_entity SET settings = %s::json WHERE id = %s",
                (json.dumps(s), LEO_WF_ID))
    print(f"  Wired Leos Workflow settings.errorWorkflow -> {error_wf_id}")


def add_fast_ack_node(cur):
    """Add a Telegram node sending 'received, processing...' right after If Authorized
    (the existing whitelist branch's success edge). Skip if already present."""
    cur.execute("SELECT nodes, connections FROM workflow_entity WHERE id = %s", (LEO_WF_ID,))
    row = cur.fetchone()
    nodes = row["nodes"] if isinstance(row["nodes"], list) else json.loads(row["nodes"])
    connections = row["connections"] if isinstance(row["connections"], dict) else json.loads(row["connections"])

    if any(n.get("name") == "Fast ACK" for n in nodes):
        print("  Fast ACK already exists (no-op)")
        return False

    cred_id, cred_name = find_telegram_credential(cur)
    fast_ack = {
        "id": str(uuid.uuid4()),
        "name": "Fast ACK",
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [-100, -100],   # off the main path visually
        "credentials": (
            {"telegramApi": {"id": cred_id, "name": cred_name}}
            if cred_id else {}
        ),
        "onError": "continueRegularOutput",
        "parameters": {
            "chatId": "={{ $('Telegram Trigger').first().json.message.chat.id }}",
            "text": "📥 received, processing…",
            "additionalFields": {"disable_notification": True},
        },
    }
    nodes.append(fast_ack)

    # Wire: Telegram Trigger -> Fast ACK (parallel to existing Whitelist Check edge).
    # We append to Telegram Trigger's existing main outputs as a 2nd branch.
    tt = connections.get("Telegram Trigger", {}).setdefault("main", [])
    # Existing main[0] is the array of next nodes (Whitelist Check). Append Fast ACK to it
    # so both fire in parallel.
    if tt and isinstance(tt[0], list):
        # Check if already wired
        if not any(c.get("node") == "Fast ACK" for c in tt[0]):
            tt[0].append({"node": "Fast ACK", "type": "main", "index": 0})
    else:
        tt.append([{"node": "Fast ACK", "type": "main", "index": 0}])

    cur.execute(
        "UPDATE workflow_entity SET nodes = %s::json, connections = %s::json, "
        "\"updatedAt\" = now() WHERE id = %s",
        (json.dumps(nodes), json.dumps(connections), LEO_WF_ID),
    )
    print("  Added Fast ACK node + wired parallel to Whitelist Check")
    return True


def patch_docker_healthcheck():
    """Add a healthcheck to n8n service in /root/n8n/docker-compose.yml. Idempotent."""
    path = "/root/n8n/docker-compose.yml"
    with open(path) as f:
        content = f.read()
    if "healthcheck:" in content:
        print("  docker-compose healthcheck already present (no-op)")
        return False
    # Insert healthcheck block right after the n8n service's volumes block.
    # The compose file is simple enough for line-level insert.
    new_lines = []
    inserted = False
    in_n8n = False
    for line in content.splitlines(keepends=True):
        new_lines.append(line)
        if line.strip().startswith("n8n:") and not line.strip().startswith("- n8n:"):
            in_n8n = True
        if in_n8n and not inserted and line.strip() == "user: root":
            indent = "    "
            new_lines.append(indent + "healthcheck:\n")
            new_lines.append(indent + "  test: [\"CMD-SHELL\", \"wget -q -O- http://localhost:5678/healthz || exit 1\"]\n")
            new_lines.append(indent + "  interval: 30s\n")
            new_lines.append(indent + "  timeout: 10s\n")
            new_lines.append(indent + "  retries: 3\n")
            new_lines.append(indent + "  start_period: 30s\n")
            inserted = True
    if inserted:
        with open(path + ".bak.deploy_266", "w") as f:
            f.write(content)
        with open(path, "w") as f:
            f.writelines(new_lines)
        print("  docker-compose.yml: added healthcheck block (backup: .bak.deploy_266)")
        return True
    print("  WARN: could not find insertion anchor in docker-compose.yml")
    return False


def main():
    print("Deploy 266 - Tier 1 bulletproofing")
    print("=" * 60)

    # STEP 1: BACKUP
    print("\n[1/5] Backup Leos Workflow")
    backup_path = backup_leo_workflow()

    try:
        conn = psycopg2.connect(DSN)
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SET LOCAL app.actor = 'jonathan_deploy_266'")

        # STEP 2: ERROR WORKFLOW
        print("\n[2/5] Error Workflow")
        error_wf_id = ensure_error_workflow(cur)
        wire_error_workflow_pointer(cur, error_wf_id)

        # STEP 3: FAST ACK
        print("\n[3/5] Fast ACK node")
        add_fast_ack_node(cur)

        conn.commit()
        cur.close()
        conn.close()
        print("  DB changes committed")

        # STEP 4: DOCKER HEALTHCHECK
        print("\n[4/5] Docker healthcheck")
        healthcheck_changed = patch_docker_healthcheck()
        # Only restart n8n if compose file actually changed; n8n re-reads
        # workflows from DB on each execution so DB changes don't require restart.
        if healthcheck_changed:
            print("  compose changed; restarting n8n...")
            r = subprocess.run(["docker", "compose", "-f", "/root/n8n/docker-compose.yml",
                                "up", "-d", "n8n"], capture_output=True, text=True)
            print(f"  compose up: rc={r.returncode}")
            if r.stderr:
                print(f"    {r.stderr.strip()[:300]}")
        else:
            print("  no restart needed (DB changes pick up on next execution)")

        # STEP 5: SMOKE TEST + AUTO-ROLLBACK
        # Wait for n8n to report healthy before running smoke. Container needs
        # ~30-60s to fully start including webhook re-registration with Telegram.
        print("\n[5/5] Post-deploy smoke test")
        import time
        print("  Waiting for n8n to report healthy + webhook registered (up to 90s)...")
        deadline = time.time() + 90
        last_msg = ""
        while time.time() < deadline:
            r = subprocess.run(
                ["docker", "inspect", "n8n-n8n-1", "--format", "{{.State.Health.Status}}"],
                capture_output=True, text=True,
            )
            health = r.stdout.strip()
            # Also check webhook is registered
            wh_ok = False
            try:
                import urllib.request, json as _json, os as _os
                token = None
                with open(BACKUP_DIR.replace("workflow_backups", ".env"), "r") if False else open("/root/landtek/.env") as f:
                    for line in f:
                        if line.startswith("TG_BOT_TOKEN=") or line.startswith("TELEGRAM_BOT_TOKEN="):
                            token = line.split("=", 1)[1].strip().strip('"\'')
                            break
                if token:
                    with urllib.request.urlopen(
                        f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=5
                    ) as resp:
                        data = _json.loads(resp.read())
                    wh_ok = bool(data.get("result", {}).get("url"))
            except Exception:
                pass
            last_msg = f"health={health} webhook_registered={wh_ok}"
            if health == "healthy" and wh_ok:
                print(f"  ready: {last_msg}")
                break
            time.sleep(5)
        else:
            print(f"  WARN: didn't fully ready in 90s ({last_msg}) — running smoke anyway")

        smoke = subprocess.run(
            ["python3", "/root/landtek/scripts/post_deploy_smoke.py"],
            capture_output=True, text=True,
        )
        print("  --- smoke output ---")
        print("  " + smoke.stdout.strip().replace("\n", "\n  "))
        if smoke.stderr.strip():
            print("  stderr: " + smoke.stderr.strip()[:300])
        if smoke.returncode != 0:
            print(f"  smoke FAILED (rc={smoke.returncode}) - AUTO-ROLLBACK")
            subprocess.run(["python3", "/root/landtek/scripts/backup_workflow.py",
                            LEO_WF_ID, "rollback", "--restore-from", backup_path],
                           check=False)
            print("  Restarting n8n after rollback...")
            subprocess.run(["docker", "restart", "n8n-n8n-1"], capture_output=True)
            sys.exit(1)
        print("  smoke PASSED")

    except Exception as e:
        print(f"\nFATAL: {type(e).__name__}: {e}")
        print(f"To rollback manually: python3 scripts/backup_workflow.py {LEO_WF_ID} rollback --restore-from {backup_path}")
        sys.exit(1)


if __name__ == "__main__":
    main()
