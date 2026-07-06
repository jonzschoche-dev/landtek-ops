#!/usr/bin/env python3
"""execution_tracker.py — resident agent: track filings/actions to completion. $0.

There is no PH court-filing API and the system never files — so this TRACKS the lifecycle of each
planned action (planned → drafted → approved → filed → confirmed) in `case_actions`, flags items
stuck past their stage (approved-but-not-filed past the due date; filed-but-unconfirmed > 14 days),
and cross-references `filing_alerts` for a court order/resolution that may confirm one of our filings
landed. Operators/Leo log actions; this watches them so nothing approved quietly fails to get filed,
or sits filed-without-confirmation, before Aug 12. Stale items alert the operator via tg_send (S14).

  python3 scripts/execution_tracker.py                         # check + alert stale
  python3 scripts/execution_tracker.py --add MATTER "desc" [--due YYYY-MM-DD]
  python3 scripts/execution_tracker.py --set <id> <status>     # planned|drafted|approved|filed|confirmed
  python3 scripts/execution_tracker.py --report
"""
import subprocess
import sys

import psycopg2

from agent_alert import emit  # unified decision log (scripts/ is on sys.path when run as a script)
try:  # outward-action chokepoint (deploy_717) — a mark-FILED is a T3 outward claim
    import outward_guard
except Exception:
    outward_guard = None

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
TG_SEND = "/root/landtek/scripts/tg_send.py"
STAGES = ["planned", "drafted", "approved", "filed", "confirmed"]


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True
    return c


def _ensure(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS case_actions (
        id serial PRIMARY KEY, matter_code text, description text,
        status text DEFAULT 'planned', due_date date, notes text,
        created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now())""")


def check(cur, notify):
    cur.execute("""SELECT id, matter_code, description, status, due_date,
        (now()::date - due_date) past_due, (now() - updated_at > interval '14 days') stale
        FROM case_actions WHERE status NOT IN ('confirmed')""")
    alerts = []
    for cid, mc, desc, st, due, past_due, stale in cur.fetchall():
        if st == "approved" and due and past_due is not None and past_due > 0:
            msg = f"[{mc}] APPROVED but not filed, {past_due}d past due: {desc}"
            alerts.append(msg)
            emit("execution_tracker", "execution", msg[:160], matter=mc, severity="high",
                 dedup_key=f"exec:{cid}:approved_past_due")
        elif st == "filed" and stale:
            # has a court filing landed for this matter since? (possible confirmation)
            cur.execute("""SELECT 1 FROM filing_alerts WHERE matter_code=%s AND received > now()-interval '30 days'
                           AND subject ~* 'order|resolution|decision' LIMIT 1""", (mc,))
            hint = " (a recent order/resolution exists — verify if it confirms)" if cur.fetchone() else ""
            msg = f"[{mc}] FILED >14d, awaiting confirmation: {desc}{hint}"
            alerts.append(msg)
            emit("execution_tracker", "execution", msg[:160], matter=mc, severity="medium",
                 dedup_key=f"exec:{cid}:filed_unconfirmed")
    if notify and alerts:
        msg = "Execution tracker: " + alerts[0] + (f" (+{len(alerts)-1} more)" if len(alerts) > 1 else "")
        try:
            subprocess.run(["python3", TG_SEND, "6513067717", "execution_tracker", msg[:280]],
                           capture_output=True, timeout=30)
        except Exception:
            pass
    return alerts


def report(cur):
    cur.execute("SELECT status, count(*) FROM case_actions GROUP BY 1 ORDER BY 2 DESC")
    rows = cur.fetchall()
    print("=" * 64); print("EXECUTION TRACKER — case action ledger"); print("=" * 64)
    print("  by status:", dict(rows) or "(no actions logged yet)")
    cur.execute("""SELECT id, matter_code, status, coalesce(due_date::text,'-'), left(description,46)
                   FROM case_actions WHERE status<>'confirmed' ORDER BY due_date NULLS LAST LIMIT 15""")
    for cid, mc, st, due, desc in cur.fetchall():
        print(f"  [{cid}] {mc:18} {st:9} due {due:12} {desc}")


def main():
    a = sys.argv
    c = _conn(); cur = c.cursor()
    _ensure(cur)
    if "--add" in a:
        i = a.index("--add"); mc, desc = a[i + 1], a[i + 2]
        due = a[a.index("--due") + 1] if "--due" in a else None
        cur.execute("INSERT INTO case_actions (matter_code,description,due_date) VALUES (%s,%s,%s) RETURNING id",
                    (mc, desc, due))
        print(f"✓ action {cur.fetchone()[0]} logged for {mc}")
    elif "--set" in a:
        i = a.index("--set"); cid, st = int(a[i + 1]), a[i + 2]
        if st not in STAGES:
            print(f"status must be one of {STAGES}"); return
        # Outward chokepoint (deploy_717): marking FILED asserts an outward filing happened (T3).
        # Shadow logs it; block would hold. (Block-mode for filing awaits operator-vs-agent origin.)
        if st == "filed" and outward_guard is not None:
            try:
                _d, _gi = outward_guard.guard("filing", f"action:{cid}", source="execution_tracker",
                                              preview=f"mark case_action {cid} FILED")
            except Exception:
                _d = "allow"
            if _d == "hold":
                print(f"[mark-filed] HELD by outward_guard (order #{_gi.get('order')}) — status unchanged"); return
        cur.execute("UPDATE case_actions SET status=%s, updated_at=now() WHERE id=%s", (st, cid))
        print(f"✓ action {cid} → {st}" if cur.rowcount else "no such action")
    elif "--report" in a:
        report(cur)
    else:
        alerts = check(cur, notify=True)
        print(f"[execution-tracker] {len(alerts)} stale action(s)")
        for x in alerts:
            print("  ⚠ " + x)
        report(cur)


if __name__ == "__main__":
    main()
