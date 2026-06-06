#!/usr/bin/env python3
"""leo_proposal_verify.py — measure attributable improvement (deploy_305).

Usage:
    python3 scripts/leo_proposal_verify.py <proposal_id>

What it does:
  1. Loads applied proposal #ID; requires status='applied'.
  2. Re-reads sim runs against target probes from AFTER applied_at.
       (If <5 runs per target probe, prints "not enough data — wait longer".)
  3. Computes post_apply_pass_rate.
  4. Compares to baseline_pass_rate.
  5. Updates proposal: status='verified' (+ deltas) and pages Jonathan with the
     before/after, naming the proposal and the actual numbers.

The pass-rate delta is the only valid evidence Leo got smarter. If it's
positive and statistically meaningful, the proposal "worked." If neutral or
negative, the proposer needs better signal next round.
"""
from __future__ import annotations
import json
import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
try:
    from tg_send import send as tg_send
except Exception:
    tg_send = None

DSN      = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN = "6513067717"


def post_apply_rates(cur, target_probes: list[str], applied_at):
    cur.execute("""
        SELECT p.name,
               COUNT(*)                     AS runs,
               COUNT(*) FILTER (WHERE s.passed) AS passes
          FROM leo_qa_sim_payloads s
          JOIN leo_qa_probes p ON p.id = s.probe_id
         WHERE p.name = ANY(%s) AND s.posted_at > %s
         GROUP BY p.name
    """, (target_probes, applied_at))
    return {r["name"]: (r["runs"], r["passes"]) for r in cur.fetchall()}


def page(text: str):
    if tg_send is None: return
    try:
        tg_send(JONATHAN, text, source="watchdog",
                recipient_name="Jonathan", override_rate_limit=True)
    except Exception:
        pass


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    pid = int(sys.argv[1])
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT * FROM leo_improvement_proposals WHERE id=%s", (pid,))
    p = cur.fetchone()
    if not p:
        print(f"proposal #{pid} not found"); sys.exit(2)
    if p["status"] != "applied":
        print(f"proposal #{pid} status is {p['status']!r} — verifier expects 'applied'")
        sys.exit(2)
    if not p["applied_at"]:
        print("no applied_at timestamp on proposal"); sys.exit(2)

    targets = p["target_probes"] or []
    if not targets:
        print("proposal has no target_probes"); sys.exit(2)

    rates = post_apply_rates(cur, targets, p["applied_at"])
    total_runs = sum(r for r, _ in rates.values())
    total_pass = sum(s for _, s in rates.values())
    min_per_probe = min((r for r, _ in rates.values()), default=0)

    if min_per_probe < 3:
        msg = (f"⚠️ proposal #{pid} — too little post-apply data yet "
               f"(min {min_per_probe} runs / probe). Try again in 30 min.")
        print(msg); page(msg); sys.exit(0)

    new_rate = round(total_pass / max(total_runs, 1), 4)
    baseline = p["baseline_pass_rate"]
    delta = (new_rate - (baseline or 0)) if baseline is not None else None

    cur.execute("""
        UPDATE leo_improvement_proposals
           SET status            = 'verified',
               verified_at       = now(),
               post_apply_pass_rate = %s,
               notes = COALESCE(notes,'') || %s
         WHERE id = %s
    """, (new_rate,
          f"\n[verify] runs={total_runs} passes={total_pass} delta={delta}",
          pid))

    print(f"━━━ Proposal #{pid} verified ━━━")
    print(f"  baseline_pass_rate:    {baseline}")
    print(f"  post_apply_pass_rate:  {new_rate}")
    print(f"  delta:                 {delta:+.3f}" if delta is not None else "  delta:  n/a")
    print(f"  total post-apply runs: {total_runs}  ({total_pass} passes)")
    print(f"  per-probe breakdown:")
    for name, (runs, passes) in rates.items():
        print(f"    {name:50s}  {passes}/{runs}")

    glyph = "✅" if (delta or 0) > 0.10 else ("➖" if abs(delta or 0) < 0.10 else "❌")
    msg = (
        f"{glyph} <b>Proposal #{pid} verified</b>\n"
        f"<i>{p['failure_pattern']}</i>\n"
        f"pass rate {baseline} → {new_rate}  ({delta:+.2f})\n"
        f"runs: {total_runs}  on {len(targets)} probes"
    )
    page(msg)
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
