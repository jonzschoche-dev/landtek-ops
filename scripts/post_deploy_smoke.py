#!/usr/bin/env python3
"""post_deploy_smoke.py - send a synthetic Telegram update + verify Leo replies.

Tier 1 bulletproofing (deploy_266). Call after ANY workflow mutation:

  python3 scripts/post_deploy_smoke.py

Exit code 0 if a new successful execution appears within timeout, nonzero
otherwise. Migrations should treat nonzero as "rollback needed" and call
backup_workflow.py --restore-from <last backup>.

Strategy: POST a synthetic Telegram update directly to the n8n webhook.
The update mimics a real Telegram message from Jonathan saying "/ping".
Then poll execution_entity for a NEW successful execution since the POST
time.
"""
import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import urllib.request
import urllib.error

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
WORKFLOW_ID = "vSDQv1vfn6627bnA"
WEBHOOK_URL = "http://localhost:5678/webhook/2fe01d2f-680c-47bd-86c6-7bb24893afb9/webhook"
JONATHAN_TELEGRAM_ID = 6513067717


def synth_update(text):
    """Build a synthetic Telegram update mimicking Jonathan sending a message."""
    update_id = int(time.time())
    msg_id = update_id  # crude but unique enough for smoke testing
    return {
        "update_id": update_id,
        "message": {
            "message_id": msg_id,
            "from": {
                "id": JONATHAN_TELEGRAM_ID,
                "is_bot": False,
                "first_name": "Jonathan",
                "last_name": "Zschoche",
                "username": "jonzschoche",
                "language_code": "en",
            },
            "chat": {
                "id": JONATHAN_TELEGRAM_ID,
                "first_name": "Jonathan",
                "last_name": "Zschoche",
                "username": "jonzschoche",
                "type": "private",
            },
            "date": update_id,
            "text": text,
            "_synthetic": True,  # marker so the workflow could optionally skip side effects
        },
    }


def post_to_webhook(update):
    data = json.dumps(update).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK_URL, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return None, str(e)


def wait_for_execution(start_dt, timeout_sec=60, want_status="success"):
    """Poll execution_entity for a new execution that started after start_dt."""
    conn = psycopg2.connect(DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    deadline = time.time() + timeout_sec
    last_seen = None
    while time.time() < deadline:
        cur.execute("""
            SELECT id, status, "startedAt", "stoppedAt"
              FROM execution_entity
             WHERE "workflowId" = %s
               AND "startedAt" >= %s
             ORDER BY "startedAt" DESC LIMIT 1
        """, (WORKFLOW_ID, start_dt))
        row = cur.fetchone()
        if row:
            last_seen = row
            if row["status"] == want_status:
                cur.close()
                conn.close()
                return True, row
            elif row["status"] in ("error", "crashed"):
                cur.close()
                conn.close()
                return False, row
        time.sleep(2)
    cur.close()
    conn.close()
    return False, last_seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="/ping",
                    help="Synthetic message text (default: /ping)")
    ap.add_argument("--timeout", type=int, default=60)
    args = ap.parse_args()

    print(f"post_deploy_smoke: sending synthetic update text={args.text!r}")
    start = datetime.now(timezone.utc)

    update = synth_update(args.text)
    code, body = post_to_webhook(update)
    if code != 200:
        print(f"  webhook POST failed: code={code} body={(body or '')[:200]!r}")
        sys.exit(1)
    print(f"  webhook accepted ({code})")

    ok, row = wait_for_execution(start, timeout_sec=args.timeout)
    if ok:
        print(f"  SUCCESS: execution {row['id']} status={row['status']} "
              f"in {(row['stoppedAt'] - row['startedAt']).total_seconds():.1f}s")
        sys.exit(0)
    else:
        if row:
            print(f"  FAIL: latest execution {row['id']} status={row['status']}")
        else:
            print(f"  FAIL: no execution observed within {args.timeout}s")
        sys.exit(1)


if __name__ == "__main__":
    main()
