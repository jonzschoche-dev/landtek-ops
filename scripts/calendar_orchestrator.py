#!/usr/bin/env python3
"""calendar_orchestrator.py — THE PULSE RUNS THE COMPANY (calendar-is-the-pulse §inversion).

Operator doctrine (2026-07-11): "The calendar is a pulse that runs the company. You don't
engage it — it's the orchestrator. It engages all production, communications, deadlines."

This is the bridge that makes that literal: an approaching dated item FIRES WORK without
being asked. Each pulse tick walks the agenda spine (the same gather the calendar and the
briefs use) and, on deterministic lead-time rules, ENQUEUES work_orders into the
supervisor state machine (scripts/supervisor.py) — which is FAIL-CLOSED by construction:
every order ends in a human-held T3 step, and outward verbs are structurally blocked from
autonomous execution. The pulse initiates; governance still decides.

Lanes (v1 — deliberately narrow):
  PRODUCTION    T-14: an agenda item inside 14 days gets a `deliverable` work order
                (produce → verify → certify) so preparation STARTS on the pulse, not on
                somebody remembering. One order per item, idempotent (pulse_work_log).
  COMMUNICATIONS / ESCALATION are already pulse-driven (assistant_cadence briefs,
                deadline sentinels, agent_alert) — not duplicated here.

Guardrails: dry-run by default (--apply writes) · enqueue-only (this script never
executes a step, never sends anything) · per-tick cap with an explicit log line (no
silent truncation) · idempotent via pulse_work_log · degrade-don't-crash.

Usage:
  python3 scripts/calendar_orchestrator.py            # dry-run: show what the pulse WOULD fire
  python3 scripts/calendar_orchestrator.py --apply    # enqueue for real
  python3 scripts/calendar_orchestrator.py --horizon 14 --cap 10
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/root/landtek/scripts")

from calendar_sync import db  # noqa: E402
from assistant_cadence import get_agenda, item_date, manila_today  # noqa: E402

RULE = "T14_prep"
DEFAULT_HORIZON = 14
DEFAULT_CAP = 10


def ensure_ledger(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pulse_work_log (
            item_uid      TEXT NOT NULL,
            rule          TEXT NOT NULL,
            work_order_id INT,
            item_date     DATE,
            created_at    TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY (item_uid, rule)
        )""")


def already_fired(cur, uid, rule):
    cur.execute("SELECT work_order_id FROM pulse_work_log WHERE item_uid=%s AND rule=%s",
                (uid, rule))
    return cur.fetchone() is not None


def enqueue_deliverable(cur, item, by="calendar_orchestrator"):
    """Mirror supervisor.cmd_enqueue for kind='deliverable' (same shape, same audit),
    without shelling out. The kind's steps end in a human T3 certify — fail-closed."""
    from supervisor import KINDS  # the registry is the single source of step shape
    spec = KINDS["deliverable"]
    steps = [dict(s, status="pending", result=None) for s in spec["steps"]]
    d = item_date(item)
    title = f"[pulse T-14] Prepare: {item.title[:120]} (due {d.isoformat()})"
    note = (f"enqueued by the pulse (calendar_orchestrator {RULE}) · uid={item.uid} "
            f"· due={d.isoformat()} · owner={item.owner or '-'}")
    audit = [{"at": datetime.now(timezone.utc).isoformat(), "from": None,
              "to": "queued", "note": note}]
    cur.execute(
        """INSERT INTO work_orders (kind, matter_code, title, status, steps, current_step,
             created_by, target_ref, audit)
           VALUES ('deliverable', %s, %s, 'queued', %s, 0, %s, %s, %s) RETURNING id""",
        (item.matter or item.client, title, json.dumps(steps), by,
         f"agenda:{item.uid}", json.dumps(audit)))
    return cur.fetchone()[0]


def main():
    ap = argparse.ArgumentParser(description="the pulse tick — dated items fire work orders")
    ap.add_argument("--apply", action="store_true", help="enqueue for real (default: dry-run)")
    ap.add_argument("--horizon", type=int, default=DEFAULT_HORIZON, help="days ahead (default 14)")
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP, help="max new orders per tick")
    args = ap.parse_args()

    conn = db()
    cur = conn.cursor()
    ensure_ledger(cur)
    conn.commit()

    today = manila_today()
    horizon_end = today + timedelta(days=args.horizon)
    items = [i for i in get_agenda(cur)
             if today <= item_date(i) <= horizon_end]
    items.sort(key=item_date)

    # CONSOLIDATE before firing — the pulse must not amplify upstream noise (e.g. the
    # extractor writing N duplicate calendar_events rows) into N identical work orders.
    # One order per (matter, date, normalized title); duplicates are reported, not fired.
    seen, unique, dupes = set(), [], 0
    for it in items:
        key = (it.matter or it.client or "?", item_date(it),
               (it.title or "").strip().lower()[:60])
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        unique.append(it)
    if dupes:
        print(f"[pulse] consolidated {dupes} duplicate agenda row(s) (same matter+date+title)")
    items = unique

    print(f"[pulse] {today} — {len(items)} dated item(s) inside T-{args.horizon}")
    fired = skipped = 0
    deferred = []
    for it in items:
        if already_fired(cur, it.uid, RULE):
            skipped += 1
            continue
        if fired >= args.cap:
            deferred.append(it)
            continue
        d = item_date(it)
        tag = " · ".join(x for x in (it.client, it.matter, it.owner) if x) or "untagged"
        if not args.apply:
            print(f"  [WOULD FIRE] {d} [{tag}] {it.title[:70]}")
            fired += 1
            continue
        wo_id = enqueue_deliverable(cur, it)
        cur.execute(
            "INSERT INTO pulse_work_log (item_uid, rule, work_order_id, item_date) "
            "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", (it.uid, RULE, wo_id, d))
        conn.commit()
        print(f"  [FIRED wo#{wo_id}] {d} [{tag}] {it.title[:70]}")
        fired += 1

    if deferred:  # no silent caps
        print(f"[pulse] cap {args.cap} reached — {len(deferred)} item(s) deferred to the "
              f"next tick: " + ", ".join(i.uid for i in deferred[:8]))
    verb = "fired" if args.apply else "would fire"
    print(f"[pulse] {verb}: {fired} · already-fired (idempotent): {skipped}"
          + ("" if args.apply else "   (DRY-RUN — pass --apply)"))
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
