#!/usr/bin/env python3
"""supervisor_sentinel.py — the "or surfaces" half of A59 (governed task completion).

A59: any governed-data-mutating task runs under a work_order reaching a TERMINAL state (done/held/
failed-with-reason), never silently abandoned — and an order STALLED past its review horizon SURFACES
to the operator. supervisor.py drives orders forward; this sentinel catches the ones that stop moving:
a non-terminal order older than its horizon → a holes_findings row + a notifications/pending.txt line
(same surfacing pattern as the offline/incorporation nightly steps). Idempotent: one finding per
stalled order; auto-closed when the order later reaches a terminal state.

  python3 scripts/supervisor_sentinel.py            # scan + surface (writes findings + pending.txt)
  python3 scripts/supervisor_sentinel.py --dry      # preview only, no writes
"""
from __future__ import annotations
import os
import sys
import json
import hashlib
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
NOTIF_PATH = "/root/landtek/notifications/pending.txt"
ROUTINE = "supervisor_sentinel"
ROUTINE_VERSION = "1"

# Review horizons per non-terminal status (hours). Past this with no movement → stalled → surface.
HORIZONS = {
    "queued": 24,              # routed but never picked up
    "in_progress": 24,
    "awaiting_handoff": 48,    # waiting on a human/agent handoff
    "blocked_governance": 72,  # held for a human — longer rope, but still must not rot
}
TERMINAL = ("done", "cancelled", "failed", "held")


def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


def _hash(order_id):
    return hashlib.sha256(f"stalled-work-order-{order_id}".encode()).hexdigest()[:32]


def _notify(msg):
    try:
        os.makedirs(os.path.dirname(NOTIF_PATH), exist_ok=True)
        with open(NOTIF_PATH, "a") as f:
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] {ROUTINE}: {msg}\n")
    except Exception:
        pass  # surfacing must never crash the sentinel


def scan(dry=False):
    conn = _conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # 1) Auto-close open findings whose order has since reached a terminal state (self-healing).
    closed = 0
    if not dry:
        cur.execute(
            "UPDATE holes_findings h SET status='remediated', remediated_at=now(), "
            "remediated_via='order_reached_terminal' "
            "FROM work_orders w "
            "WHERE h.routine_name=%s AND h.status='open' "
            "AND h.metadata->>'order_id' = w.id::text AND w.status = ANY(%s)",
            (ROUTINE, list(TERMINAL)),
        )
        closed = cur.rowcount

    # 2) Find non-terminal orders past their horizon.
    cur.execute(
        """SELECT id, kind, matter_code, status, title, updated_at,
                  EXTRACT(EPOCH FROM (now() - updated_at))/3600.0 AS age_h
             FROM work_orders
            WHERE status NOT IN %s
            ORDER BY updated_at ASC""",
        (TERMINAL,),
    )
    stalled = []
    for r in cur.fetchall():
        horizon = HORIZONS.get(r["status"], 48)
        if r["age_h"] < horizon:
            continue
        stalled.append((r, horizon))

    surfaced = 0
    for r, horizon in stalled:
        fid = _hash(r["id"])
        age = round(r["age_h"], 1)
        sev = "high" if r["age_h"] >= 3 * horizon else "warn"
        desc = (f"work_order #{r['id']} ({r['kind']}, matter={r['matter_code'] or '-'}) STALLED in "
                f"'{r['status']}' for {age}h (horizon {horizon}h): {(r['title'] or '')[:80]}")
        if dry:
            print(f"  WOULD SURFACE [{sev}] {desc}")
            continue
        # dedup: one open finding per stalled order
        cur.execute("SELECT 1 FROM holes_findings WHERE finding_id_hash=%s AND status='open'", (fid,))
        if cur.fetchone():
            continue
        cur.execute(
            """INSERT INTO holes_findings
                 (routine_name, routine_version, finding_id_hash, severity, hole_type,
                  matter_code, description, suggested_fix, auto_remediable, metadata, status)
               VALUES (%s,%s,%s,%s,'stalled_work_order',%s,%s,%s,false,%s,'open')""",
            (ROUTINE, ROUTINE_VERSION, fid, sev, r["matter_code"], desc,
             f"python3 scripts/supervisor.py status {r['id']}  # then resolve / complete / cancel it",
             json.dumps({"order_id": r["id"], "kind": r["kind"], "status": r["status"],
                         "age_hours": age, "horizon_hours": horizon})),
        )
        _notify(desc)
        surfaced += 1

    print(f"[{ROUTINE}] scanned; stalled={len(stalled)} surfaced_new={surfaced} auto_closed={closed}"
          + (" (dry-run)" if dry else ""))
    cur.close(); conn.close()


if __name__ == "__main__":
    scan(dry="--dry" in sys.argv)
