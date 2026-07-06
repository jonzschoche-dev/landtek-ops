#!/usr/bin/env python3
"""outward_shadow_report.py — phone-friendly readout of what outward_guard WOULD do (shadow phase).

This is the review surface for the shadow->block exit-criteria. Run it after the guard has seen real
traffic and confirm, before flipping outward_guard_config.mode to 'block':
  1. ZERO false-holds  — no 'would_hold' row is actually internal/operator traffic.
  2. ZERO false-passes — every real outward send shows as 'would_hold' (not 'internal_skip').
  3. Sane volume + target distribution (no surprise egress path we missed).

  python3 scripts/outward_shadow_report.py            # last 24h summary
  python3 scripts/outward_shadow_report.py --hours 72  # wider window
  python3 scripts/outward_shadow_report.py --holds     # list the would-hold targets (the block set)
"""
import os
import sys
import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def main():
    hours = int(sys.argv[sys.argv.index("--hours") + 1]) if "--hours" in sys.argv else 24
    show_holds = "--holds" in sys.argv
    c = psycopg2.connect(DSN); cur = c.cursor()

    cur.execute("SELECT mode FROM outward_guard_config WHERE id=1")
    row = cur.fetchone()
    mode = row[0] if row else "shadow"

    cur.execute(
        "SELECT would_decision, count(*) FROM outward_shadow_log "
        "WHERE ts > now() - (%s || ' hours')::interval GROUP BY would_decision ORDER BY 2 DESC",
        (hours,),
    )
    rows = cur.fetchall()
    total = sum(n for _, n in rows)
    print(f"outward_guard: mode={mode} · last {hours}h · {total} sends seen")
    for dec, n in rows:
        print(f"  {dec:22} {n}")

    # would_hold = the outward sends that block mode would gate — grouped by target + source
    cur.execute(
        "SELECT channel, source, guard_target, count(*) FROM outward_shadow_log "
        "WHERE would_decision='would_hold' AND ts > now() - (%s || ' hours')::interval "
        "GROUP BY 1,2,3 ORDER BY 4 DESC LIMIT 40",
        (hours,),
    )
    holds = cur.fetchall()
    print(f"\nwould-HOLD (block set): {len(holds)} distinct target/source")
    if show_holds:
        for ch, src, tgt, n in holds:
            print(f"  [{ch}] {tgt}  <- {src}  x{n}")
    elif holds:
        print("  (run with --holds to list them)")

    cur.close(); c.close()


if __name__ == "__main__":
    main()
