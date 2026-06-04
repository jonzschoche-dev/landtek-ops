#!/usr/bin/env python3
"""connection_loss_sentinel.py — the silence detector (deploy_290).

Closes the gap Jonathan named: "the original mandate of Leo was never to lose
a message or a connection." Our prior watchers checked the visible reply path
(bot alive, webhook registered, n8n healthy) but NOT whether each inbound
message actually produced an outbound response. Three silent-failure incidents
in one night (Qdrant cascade, onboarding ECONNREFUSED, Notify-Jonathan no-op)
all passed those checks while real messages were dropped.

This sentinel watches the ACTUAL mandate. Every 60 seconds it scans recent
Leo executions and flags any where an inbound Telegram message did NOT result
in at least one message-send node firing. If found, it alerts Jonathan within
a minute — instead of us discovering the silence hours later.

Detection logic
---------------
For each execution in the last LOOKBACK_MIN minutes on the Leo workflow:
  1. Confirm it was Telegram-triggered (has a Telegram Trigger node run).
  2. Find which "terminal" nodes fired. A healthy run fires at least one of:
       Reply to Jonathan, Reply to Client, Send Onboarding Reply,
       Notify Jonathan Unauth, Call Slash API (slash replies), Ask Clarification
  3. If NONE of those fired (and the run isn't a pure system/no-op), the
     inbound message was received but nothing went back → SILENCE → alert.
  4. Also alert on any execution with status='error' (defensive — even though
     deploy_289 made the memory tail fail-safe, a NEW error class should page us).

Dedup: each execution alerts at most once (tracked in sentinel_alerts table).

Alerts go through scripts/tg_send.py (source='watchdog', rate-limit-exempt).
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
try:
    from tg_send import send  # deploy_288 chokepoint
except Exception:
    send = None

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"
JONATHAN = "6513067717"
LOOKBACK_MIN = 10  # scan a wider window than the 60s cadence to catch stragglers

# A healthy inbound conversation fires at least one of these
TERMINAL_SEND_NODES = {
    "Reply to Jonathan",
    "Reply to Client",
    "Send Onboarding Reply",
    "Notify Jonathan Unauth",
    "Call Slash API",
    "Ask Clarification",
    "Safe Reply",
}

# Nodes that mark an execution as a genuine inbound message (vs a cron/no-op)
TRIGGER_NODE = "Telegram Trigger"


def ensure_schema(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sentinel_alerts (
            id          serial PRIMARY KEY,
            execution_id text NOT NULL,
            reason      text NOT NULL,
            alerted_at  timestamptz NOT NULL DEFAULT now(),
            UNIQUE (execution_id, reason)
        );
        """
    )


def deref(raw):
    """Resolve n8n's ref-array exec data with cycle guard."""
    def D(v, depth=0, seen=None):
        seen = seen or set()
        if depth > 40:
            return None
        if isinstance(v, str) and v.isdigit():
            i = int(v)
            if i in seen or i >= len(raw):
                return None
            return D(raw[i], depth + 1, seen | {i})
        if isinstance(v, list):
            return [D(x, depth + 1, seen) for x in v]
        if isinstance(v, dict):
            return {k: D(x, depth + 1, seen) for k, x in v.items()}
        return v
    return D(raw[0])


def analyze_exec(cur, exec_id):
    """Return (is_inbound, fired_terminal, sender_id, text) for an execution."""
    cur.execute(
        'SELECT data::text FROM execution_data WHERE "executionId" = %s', (exec_id,)
    )
    row = cur.fetchone()
    if not row:
        return None
    try:
        raw = json.loads(row["data"])
        root = deref(raw)
    except Exception:
        return None
    if not isinstance(root, dict):
        return None
    run = (root.get("resultData") or {}).get("runData") or {}
    if TRIGGER_NODE not in run:
        return None  # not a Telegram-triggered run
    fired_terminal = any(n in run for n in TERMINAL_SEND_NODES)
    # Extract sender + text for the alert
    sender_id, text = None, None
    try:
        tt = run[TRIGGER_NODE][0]["data"]["main"][0][0]["json"]
        msg = tt.get("message", tt)
        sender_id = str((msg.get("from") or {}).get("id", ""))
        text = (msg.get("text") or msg.get("caption") or "")[:160]
    except Exception:
        pass
    return {"is_inbound": True, "fired_terminal": fired_terminal,
            "sender_id": sender_id, "text": text}


def already_alerted(cur, exec_id, reason):
    cur.execute(
        "SELECT 1 FROM sentinel_alerts WHERE execution_id = %s AND reason = %s",
        (exec_id, reason),
    )
    return cur.fetchone() is not None


def record_alert(cur, exec_id, reason):
    cur.execute(
        "INSERT INTO sentinel_alerts (execution_id, reason) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (exec_id, reason),
    )


def alert(text):
    if send is None:
        print("[sentinel] tg_send unavailable; would alert:", text[:120])
        return
    send(JONATHAN, text, source="watchdog", recipient_name="Jonathan",
         override_rate_limit=True)


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_schema(cur)

    cur.execute(
        """
        SELECT id, status, "startedAt"
          FROM execution_entity
         WHERE "workflowId" = %s
           AND "startedAt" > now() - (%s || ' minutes')::interval
         ORDER BY id DESC
        """,
        (WORKFLOW_ID, LOOKBACK_MIN),
    )
    execs = cur.fetchall()

    silence_hits = []
    error_hits = []

    for e in execs:
        exec_id = str(e["id"])
        info = analyze_exec(cur, exec_id)

        # deploy_311: skip sim execs — they have their own grader + leak sentinel.
        # Silence/error on a sim sender (999000001-005) is expected behavior when
        # Reply nodes are gated to chat_id=0 (deploy_300). Paging on these would
        # bombard Jonathan with non-actionable noise.
        sender_id = (info or {}).get("sender_id") or ""
        if sender_id.startswith("999000"):
            continue

        # Error executions — page even though memory-tail is fail-safe (new class)
        if e["status"] == "error" and not already_alerted(cur, exec_id, "exec_error"):
            error_hits.append((exec_id, info))
            record_alert(cur, exec_id, "exec_error")

        # Silence — inbound message but no terminal send fired
        if info and info["is_inbound"] and not info["fired_terminal"]:
            if not already_alerted(cur, exec_id, "silence"):
                silence_hits.append((exec_id, info))
                record_alert(cur, exec_id, "silence")

    for exec_id, info in silence_hits:
        sender = (info or {}).get("sender_id") or "unknown"
        text = (info or {}).get("text") or "(no text)"
        alert(
            f"\U0001F6A8 <b>SILENCE DETECTED</b>\n\n"
            f"Leo received a message but sent nothing back.\n\n"
            f"  exec #{exec_id}\n"
            f"  from chat_id: {sender}\n"
            f"  message: \"{text}\"\n\n"
            f"No reply / onboarding / notify node fired. Investigate now — "
            f"this is the 'never lose a message' tripwire."
        )

    if error_hits:
        lines = "\n".join(f"  exec #{eid}" for eid, _ in error_hits[:6])
        alert(
            f"⚠️ <b>Leo execution error(s)</b>\n\n"
            f"{len(error_hits)} execution(s) errored in the last {LOOKBACK_MIN} min:\n"
            f"{lines}\n\n"
            f"Memory-tail is fail-safe (deploy_289), so this is likely a NEW "
            f"error class. Check execution_data for the failing node."
        )

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[{ts}] scanned={len(execs)} silence={len(silence_hits)} errors={len(error_hits)}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
