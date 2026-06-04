#!/usr/bin/env python3
"""sim_leak_sentinel.py — last-line defense against sim execs reaching real recipients.

Runs every 60 seconds. Scans the last 90 seconds of Leo workflow executions
whose originating Telegram sender is in the sim range (999000001-999000005).
For each, looks at the execution_data for any chat_id field value that is
NOT in {sim range, Jonathan, 0/sentinel}.

If a real-recipient chat_id is found:
  1. Stops leo-simulator.service immediately (self-defense).
  2. Pages Jonathan via tg_send with source='watchdog' (rate-limit exempt).
  3. Records the incident to sim_leak_incidents.

Why this exists:
  deploy_300 added a chat_id='0' guard to every Telegram send node in the
  workflow, which is watertight per the controlled test. This sentinel is
  belt-and-suspenders: if any new send node is added that omits the guard,
  if an n8n version upgrade changes expression semantics, or if a tool node
  ever directly invokes the Telegram bot API, this catches it within ~1 min
  and halts the bleeding.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
try:
    from tg_send import send as tg_send
except Exception:
    tg_send = None

DSN         = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"
JONATHAN    = "6513067717"

# The sim range — anything in here is fine to appear as a chat_id (Telegram rejects them anyway).
SIM_PREFIX  = "999000"
# Jonathan's own id — fine, he's the operator.
ALLOWED     = {JONATHAN}

# Sentinel value the gate substitutes — fine to appear, means the gate fired.
SENTINEL_VALUES = {"0"}

# Pull every distinct number that looks like a Telegram chat_id from the exec data.
# Telegram ids are typically 8-12 digit unsigned integers.
CHAT_ID_RE = re.compile(
    r'(?:"chatId"\s*:\s*"?(\d{8,12})"?|"chat_id"\s*:\s*(\d{8,12}))'
)


def ensure_incident_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sim_leak_incidents (
            id            serial PRIMARY KEY,
            detected_at   timestamptz NOT NULL DEFAULT now(),
            execution_id  text NOT NULL,
            sim_sender_id text,
            leaked_chat_id text NOT NULL,
            excerpt       text,
            acted         text NOT NULL
        )
    """)


def stop_simulator_now() -> str:
    try:
        r = subprocess.run(
            ["systemctl", "stop", "leo-simulator.service"],
            capture_output=True, text=True, timeout=10,
        )
        return "stopped" if r.returncode == 0 else f"stop_failed:{r.stderr.strip()[:80]}"
    except Exception as e:
        return f"stop_exception:{e}"


def alert(text: str):
    if tg_send is None:
        return
    try:
        tg_send(JONATHAN, text, source="watchdog",
                recipient_name="Jonathan", override_rate_limit=True)
    except Exception:
        pass


def scan_window(cur):
    """Find sim-execs in the last 90s and scan for leaks."""
    cur.execute(
        """
        SELECT id
          FROM execution_entity
         WHERE "workflowId" = %s
           AND "startedAt" > now() - interval '90 seconds'
        """,
        (WORKFLOW_ID,),
    )
    ids = [r["id"] for r in cur.fetchall()]
    leaks = []
    for eid in ids:
        cur.execute('SELECT data FROM execution_data WHERE "executionId"=%s', (eid,))
        r = cur.fetchone()
        if not r:
            continue
        raw = r["data"] if isinstance(r["data"], str) else json.dumps(r["data"])
        # Only care about sim execs — look for the sim-prefix in the data.
        if SIM_PREFIX not in raw:
            continue
        sim_match = re.search(r'"from"\s*:\s*\{\s*"id"\s*:\s*(' + SIM_PREFIX + r'\d+)', raw)
        sim_sender = sim_match.group(1) if sim_match else None
        if not sim_sender:
            continue
        # Now look for chat_id values that are NOT the gate sentinel and NOT in the allowed set.
        for m in CHAT_ID_RE.finditer(raw):
            cid = m.group(1) or m.group(2)
            if cid in SENTINEL_VALUES:
                continue
            if cid.startswith(SIM_PREFIX):
                continue
            if cid in ALLOWED:
                continue
            # LEAK
            i = m.start()
            excerpt = raw[max(0, i - 120): i + 160]
            leaks.append((eid, sim_sender, cid, excerpt))
    return leaks


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_incident_table(cur)
    leaks = scan_window(cur)
    if not leaks:
        print(f"[sim_sentinel] OK — no leaks in last 90s", flush=True)
        cur.close(); conn.close()
        return

    # LEAK DETECTED — stop simulator immediately and page.
    action = stop_simulator_now()
    # Dedupe by (exec, chat) so multiple regex hits don't multi-page.
    seen = set()
    fresh = []
    for eid, sender, cid, excerpt in leaks:
        k = (eid, cid)
        if k in seen:
            continue
        seen.add(k)
        fresh.append((eid, sender, cid, excerpt))

    for eid, sender, cid, excerpt in fresh:
        cur.execute(
            "INSERT INTO sim_leak_incidents (execution_id, sim_sender_id, leaked_chat_id, excerpt, acted) "
            "VALUES (%s, %s, %s, %s, %s)",
            (str(eid), sender, cid, excerpt[:600], action),
        )

    summary = (
        f"🚨 <b>SIM LEAK SENTINEL TRIPPED</b>\n\n"
        f"action: <code>{action}</code>\n"
        f"sim execs with real chat_ids: {len(fresh)}\n\n"
        + "\n".join(
            f"  exec {eid}  sim={sender}  →  leaked chat_id {cid}"
            for eid, sender, cid, _ in fresh[:5]
        )
    )
    alert(summary)
    print(f"[sim_sentinel] LEAK — stopped service ({action}) and paged Jonathan; {len(fresh)} leak(s)",
          flush=True)
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
