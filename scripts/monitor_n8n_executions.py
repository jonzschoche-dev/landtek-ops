#!/usr/bin/env python3
"""monitor_n8n_executions.py - health check for the Leos Workflow.

Postmortem trigger (May 22, 2026): Jonathan was away for a day; bot was
effectively dead the entire trip. No alerts because we only checked the
Telegram webhook status, not actual execution success.

This script answers two questions about the last 24h:
  1. Did the workflow run at all?
  2. Of the runs, what fraction succeeded?

Failure modes that trigger an alert (write to notifications/pending.txt
+ exit nonzero so cron / systemd can capture):
  - No executions in last 24h AND last successful exec was >48h ago
  - At least 1 execution in last 24h AND ALL of them errored
  - Error rate > 50% over last 24h with >= 3 executions

Usage:
  python3 scripts/monitor_n8n_executions.py            # report + alert
  python3 scripts/monitor_n8n_executions.py --json     # machine-readable
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
WORKFLOW_ID = "vSDQv1vfn6627bnA"
NOTIF_FILE = "/root/landtek/notifications/pending.txt"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--window-hours", type=int, default=24)
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # 24-hour window stats
    cur.execute("""
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE status='success') AS success,
          COUNT(*) FILTER (WHERE status='error') AS error,
          COUNT(*) FILTER (WHERE status='running') AS running,
          MAX("startedAt") FILTER (WHERE status='success') AS last_success_in_window,
          MAX("startedAt") AS last_attempt_in_window
        FROM execution_entity
        WHERE "workflowId" = %s
          AND "startedAt" >= now() - (%s || ' hours')::interval
    """, (WORKFLOW_ID, args.window_hours))
    win = cur.fetchone()

    # Last successful ever (could be older than the window)
    cur.execute("""
        SELECT MAX("startedAt") AS last_success_ever
          FROM execution_entity
         WHERE "workflowId" = %s AND status='success'
    """, (WORKFLOW_ID,))
    last_succ = cur.fetchone()["last_success_ever"]

    cur.close()
    conn.close()

    # Compute alert conditions
    alerts = []
    now = datetime.now(timezone.utc)

    if win["total"] == 0:
        # No executions in window
        if last_succ is None:
            alerts.append("CRITICAL: Workflow has NEVER had a successful execution")
        else:
            age_h = (now - last_succ.replace(tzinfo=timezone.utc)).total_seconds() / 3600
            if age_h > 48:
                alerts.append(
                    f"CRITICAL: No executions in last {args.window_hours}h. "
                    f"Last successful run was {age_h:.1f}h ago ({last_succ})"
                )

    elif win["success"] == 0 and win["total"] > 0:
        alerts.append(
            f"CRITICAL: {win['total']} executions in last {args.window_hours}h, "
            f"ALL ERRORED. Last attempt: {win['last_attempt_in_window']}"
        )

    elif win["total"] >= 3 and win["error"] / max(1, win["total"]) > 0.5:
        rate = 100 * win["error"] / win["total"]
        alerts.append(
            f"WARNING: error rate {rate:.0f}% over last {args.window_hours}h "
            f"({win['error']}/{win['total']} errored)"
        )

    report = {
        "window_hours": args.window_hours,
        "now": now.isoformat(),
        "total": win["total"],
        "success": win["success"],
        "error": win["error"],
        "running": win["running"],
        "last_success_in_window": win["last_success_in_window"].isoformat() if win["last_success_in_window"] else None,
        "last_success_ever": last_succ.isoformat() if last_succ else None,
        "alerts": alerts,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"n8n execution health (last {args.window_hours}h)")
        print("=" * 60)
        print(f"  total:    {win['total']}")
        print(f"  success:  {win['success']}")
        print(f"  error:    {win['error']}")
        print(f"  running:  {win['running']}")
        print(f"  last_success_in_window: {win['last_success_in_window']}")
        print(f"  last_success_ever:      {last_succ}")
        if alerts:
            print()
            print("  ALERTS:")
            for a in alerts:
                print(f"    {a}")
        else:
            print()
            print("  All clear.")

    # Write to notifications/pending.txt on alert (cron-friendly)
    if alerts:
        os.makedirs(os.path.dirname(NOTIF_FILE), exist_ok=True)
        with open(NOTIF_FILE, "a") as f:
            for a in alerts:
                f.write(f"[{now.isoformat()}] n8n_health: {a}\n")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
