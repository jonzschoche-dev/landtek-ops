#!/usr/bin/env python3
"""sim_trend.py — is Leo getting smarter?

Three independent signals:

  1. Daily pass-rate trend (7d)
     If we're improving, the % column trends up. Steady or declining means
     no learning is happening — probes are getting harder OR Leo is stuck.

  2. Probe state transitions
     For every probe with ≥4 runs, compare the first half to the second half:
       - GRADUATED  = first half mostly fail, second half mostly pass → Leo learned this.
       - REGRESSED  = first half mostly pass, second half mostly fail → bad: lost ground.
       - STABLE     = same status across both halves.
       - FLICKERING = mixed and unreliable.
     Net learning = #graduated − #regressed. A positive number is the only
     direct evidence the system is getting smarter on real test material.

  3. Cumulative knowledge
     Number of distinct probes Leo has ever passed at least once, day by day.
     Should be monotonically non-decreasing. If it plateaus, we've stopped
     surfacing things Leo can solve.

Usage:
  python3 /root/landtek/scripts/sim_trend.py            # 7-day default
  python3 /root/landtek/scripts/sim_trend.py 14         # custom window
"""
from __future__ import annotations
import os
import sys
from datetime import datetime, timezone
import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

def hr(t):
    pad = max(0, 78 - len(t) - 5)
    return f"\n━━━ {t} {'━' * pad}"

def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 7
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print(f"\n┌{'─'*76}┐")
    print(f"│ Leo Smartness Trend — last {days} days  ({datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC})".ljust(77) + "│")
    print(f"└{'─'*76}┘")

    # === 1. Daily pass-rate trend ===
    print(hr("1. Daily pass-rate trend"))
    cur.execute(f"""
        SELECT date_trunc('day', posted_at)::date AS day,
               COUNT(*) AS runs,
               COUNT(*) FILTER (WHERE passed) AS pass,
               ROUND(100.0 * COUNT(*) FILTER (WHERE passed) / NULLIF(COUNT(*), 0), 1) AS pct
          FROM leo_qa_sim_payloads
         WHERE posted_at > now() - interval '{days} days'
         GROUP BY 1 ORDER BY 1
    """)
    rows = cur.fetchall()
    if not rows:
        print("  (no runs yet)")
    else:
        # Find the bar scale
        max_runs = max(r["runs"] for r in rows) or 1
        print(f"  {'day':<12s}  {'runs':>6s}  {'pass':>5s}  {'%':>6s}   {'bar':<30s}")
        for r in rows:
            bar_len = int(20 * (r["pct"] or 0) / 100)
            bar = "█" * bar_len + "·" * (20 - bar_len)
            print(f"  {str(r['day']):<12s}  {r['runs']:>6d}  {r['pass']:>5d}  {(r['pct'] or 0):>5.1f}%   {bar}")
        # Slope (simple): first vs last
        first_pct = rows[0]["pct"] or 0
        last_pct = rows[-1]["pct"] or 0
        delta = last_pct - first_pct
        glyph = "↑" if delta > 1 else ("↓" if delta < -1 else "→")
        print(f"\n  slope:  {first_pct:.1f}% → {last_pct:.1f}%   delta={delta:+.1f}pp  {glyph}")

    # === 2. Probe state transitions (graduations / regressions) ===
    print(hr("2. Probe state transitions (in window)"))
    # For each probe with ≥4 runs in window, split runs into first half vs second half
    # by row number, compute pass rate of each, classify.
    cur.execute(f"""
        WITH ranked AS (
          SELECT s.probe_id, p.name, s.passed, s.posted_at,
                 ROW_NUMBER() OVER (PARTITION BY s.probe_id ORDER BY s.posted_at) AS rn,
                 COUNT(*) OVER (PARTITION BY s.probe_id) AS total
            FROM leo_qa_sim_payloads s
            JOIN leo_qa_probes p ON p.id = s.probe_id
           WHERE s.posted_at > now() - interval '{days} days'
        ),
        split AS (
          SELECT probe_id, name, total,
                 SUM(CASE WHEN rn <= total/2 AND passed THEN 1 ELSE 0 END)::float
                   / NULLIF(total/2, 0) AS first_pass_rate,
                 SUM(CASE WHEN rn > total/2 AND passed THEN 1 ELSE 0 END)::float
                   / NULLIF(total - total/2, 0) AS second_pass_rate
            FROM ranked
           GROUP BY probe_id, name, total
          HAVING total >= 4
        )
        SELECT name, total,
               ROUND(first_pass_rate::numeric, 2)  AS p1,
               ROUND(second_pass_rate::numeric, 2) AS p2,
               CASE
                 WHEN second_pass_rate - first_pass_rate >= 0.40 THEN 'GRADUATED'
                 WHEN first_pass_rate  - second_pass_rate >= 0.40 THEN 'REGRESSED'
                 WHEN first_pass_rate = second_pass_rate         THEN 'STABLE'
                 ELSE 'FLICKERING'
               END AS state
          FROM split
         ORDER BY (second_pass_rate - first_pass_rate) DESC NULLS LAST
    """)
    rows = cur.fetchall()
    graduated = [r for r in rows if r["state"] == "GRADUATED"]
    regressed = [r for r in rows if r["state"] == "REGRESSED"]
    flickering = [r for r in rows if r["state"] == "FLICKERING"]
    stable    = [r for r in rows if r["state"] == "STABLE"]

    print(f"  graduated:  {len(graduated):3d}   (probes Leo learned to pass)")
    print(f"  regressed:  {len(regressed):3d}   (probes Leo used to pass and now fails)")
    print(f"  stable:     {len(stable):3d}   (consistent across window)")
    print(f"  flickering: {len(flickering):3d}   (mixed, unreliable signal)")
    print(f"\n  NET LEARNING SCORE:  {len(graduated) - len(regressed):+d}")

    if graduated:
        print(f"\n  Top graduations:")
        for r in graduated[:5]:
            print(f"    ↑ {r['name']:50s}  {r['p1']} → {r['p2']}  ({r['total']} runs)")
    if regressed:
        print(f"\n  Regressions (these need eyes):")
        for r in regressed[:5]:
            print(f"    ↓ {r['name']:50s}  {r['p1']} → {r['p2']}  ({r['total']} runs)")

    # === 3. Cumulative knowledge curve ===
    print(hr("3. Cumulative knowledge — distinct probes ever passed, by day"))
    cur.execute(f"""
        WITH first_pass AS (
          SELECT probe_id, MIN(posted_at)::date AS first_pass_day
            FROM leo_qa_sim_payloads
           WHERE passed
           GROUP BY probe_id
        ),
        days AS (
          SELECT generate_series(
            (now() - interval '{days} days')::date,
            now()::date,
            interval '1 day'
          )::date AS day
        )
        SELECT d.day,
               (SELECT COUNT(*) FROM first_pass WHERE first_pass_day <= d.day) AS cum_passed
          FROM days d
         ORDER BY d.day
    """)
    rows = cur.fetchall()
    if rows:
        max_c = max(r["cum_passed"] for r in rows) or 1
        for r in rows:
            bar_len = int(30 * r["cum_passed"] / max_c)
            bar = "█" * bar_len
            print(f"  {str(r['day']):<12s}  cum: {r['cum_passed']:4d}   {bar}")
        first_c = rows[0]["cum_passed"]
        last_c  = rows[-1]["cum_passed"]
        print(f"\n  knowledge gained in window: +{last_c - first_c} distinct probes learned")

    # === 4. Coverage growth — library size ===
    print(hr("4. Probe library growth"))
    cur.execute(f"""
        SELECT date_trunc('day', added_at)::date AS day,
               COUNT(*) FILTER (WHERE definition->>'origin' = 'opus_generated') AS opus,
               COUNT(*) FILTER (WHERE COALESCE(definition->>'origin','hand') != 'opus_generated') AS hand
          FROM leo_qa_probes
         WHERE rail='sim' AND added_at > now() - interval '{days} days'
         GROUP BY 1 ORDER BY 1
    """)
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"  {str(r['day']):<12s}  +{r['opus']:3d} Opus  +{r['hand']:3d} hand")
    else:
        print("  (no new probes added in window)")

    print()
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
