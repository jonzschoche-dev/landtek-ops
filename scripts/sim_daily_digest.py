#!/usr/bin/env python3
"""sim_daily_digest.py — daily simulator state push to Jonathan (deploy_309).

Cron at 23:00 UTC (7:00 AM Manila). Pulls 24h of simulator state and pushes
a single tg_send message to Jonathan summarizing:

  - Throughput               (runs/24h, pass rate, projected/day)
  - Net learning score       (graduated - regressed in last 24h)
  - Top failing probes       (3 worst by fail count)
  - Pending Opus proposals   (count + most recent rationale)
  - Pending verifies         (applied proposals waiting on the verifier)
  - Sim leak incidents       (should be 0)
  - Mandate-invariant status (deploy_307 probes — critical-severity health)
  - Probe library composition

If everything's nominal, the message is short. If anything's off, it surfaces
in the digest. Source='watchdog', rate-limit exempt so it always lands.
"""
from __future__ import annotations
import os, sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
try:
    from tg_send import send as tg_send
except Exception:
    tg_send = None

DSN      = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN = "6513067717"


def section(rows):
    return "\n".join(rows)


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    parts = []

    # === Throughput ===
    cur.execute("""
        SELECT COUNT(*)                                        AS runs,
               COUNT(*) FILTER (WHERE passed)                  AS pass,
               COUNT(*) FILTER (WHERE leo_reply_text IS NULL)  AS no_reply
          FROM leo_qa_sim_payloads
         WHERE posted_at > now() - interval '24 hours'
    """)
    r = cur.fetchone()
    runs, pass_n, no_reply = r["runs"], r["pass"], r["no_reply"]
    pct = round(100*pass_n/max(runs,1), 1)
    parts.append(f"<b>24h:</b> {runs} runs · {pass_n} pass ({pct}%) · {no_reply} no-reply")

    # === Net learning score ===
    cur.execute("""
        WITH ranked AS (
          SELECT s.probe_id, s.passed, s.posted_at,
                 ROW_NUMBER() OVER (PARTITION BY s.probe_id ORDER BY s.posted_at) AS rn,
                 COUNT(*) OVER (PARTITION BY s.probe_id) AS total
            FROM leo_qa_sim_payloads s
           WHERE s.posted_at > now() - interval '24 hours'
        ), split AS (
          SELECT probe_id, total,
                 SUM(CASE WHEN rn <= total/2 AND passed THEN 1 ELSE 0 END)::float
                   / NULLIF(total/2,0) AS p1,
                 SUM(CASE WHEN rn > total/2 AND passed THEN 1 ELSE 0 END)::float
                   / NULLIF(total - total/2,0) AS p2
            FROM ranked
           GROUP BY probe_id, total
          HAVING total >= 4
        )
        SELECT COUNT(*) FILTER (WHERE p2 - p1 >= 0.40) AS graduated,
               COUNT(*) FILTER (WHERE p1 - p2 >= 0.40) AS regressed
          FROM split
    """)
    r = cur.fetchone()
    grad, regr = r["graduated"] or 0, r["regressed"] or 0
    glyph = "↑" if grad > regr else ("↓" if regr > grad else "→")
    parts.append(f"<b>Learning:</b> {grad} graduated, {regr} regressed  {glyph}{grad-regr:+d}")

    # === Mandate-invariant status (deploy_307 probes) ===
    cur.execute("""
        SELECT p.name, COUNT(*) AS runs, COUNT(*) FILTER (WHERE s.passed) AS pass
          FROM leo_qa_sim_payloads s
          JOIN leo_qa_probes p ON p.id = s.probe_id
         WHERE p.name LIKE 'mandate.%'
           AND s.posted_at > now() - interval '24 hours'
         GROUP BY p.name
         ORDER BY p.name
    """)
    rows = cur.fetchall()
    if rows:
        body = []
        for r in rows:
            g = "✓" if r["pass"] == r["runs"] else "✗"
            body.append(f"  {g} {r['name'].replace('mandate.','')} {r['pass']}/{r['runs']}")
        parts.append("<b>Mandate invariants:</b>\n" + "\n".join(body))

    # === Top failing probes ===
    cur.execute("""
        SELECT p.name, COUNT(*) AS runs,
               COUNT(*) FILTER (WHERE NOT s.passed) AS fail,
               MAX(s.fail_reason) AS last_fail
          FROM leo_qa_sim_payloads s
          JOIN leo_qa_probes p ON p.id = s.probe_id
         WHERE s.posted_at > now() - interval '24 hours'
         GROUP BY p.name
        HAVING COUNT(*) FILTER (WHERE NOT s.passed) > 0
         ORDER BY fail DESC LIMIT 3
    """)
    rows = cur.fetchall()
    if rows:
        body = []
        for r in rows:
            short = (r["last_fail"] or "")[:55]
            body.append(f"  • {r['name'][:42]} ({r['fail']}/{r['runs']}) {short}")
        parts.append("<b>Worst probes:</b>\n" + "\n".join(body))

    # === Pending Opus proposals ===
    cur.execute("""
        SELECT COUNT(*) AS pending,
               COUNT(*) FILTER (WHERE status='applied') AS applied
          FROM leo_improvement_proposals
    """)
    r = cur.fetchone()
    cur.execute("""
        SELECT id, failure_pattern, baseline_pass_rate, target_probes
          FROM leo_improvement_proposals
         WHERE status='pending'
         ORDER BY proposed_at DESC LIMIT 1
    """)
    top = cur.fetchone()
    if r["pending"] or r["applied"]:
        body = [f"<b>Opus proposals:</b> {r['pending']} pending · {r['applied']} applied awaiting verify"]
        if top:
            body.append(f"  Top: <code>#{top['id']}</code> — <i>{top['failure_pattern'][:80]}</i>")
            body.append(f"  Apply: <code>scripts/leo_proposal_apply.py {top['id']}</code>")
        parts.append("\n".join(body))

    # === Leak incidents ===
    cur.execute("""
        SELECT COUNT(*) AS n
          FROM sim_leak_incidents
         WHERE detected_at > now() - interval '24 hours'
    """)
    n = cur.fetchone()["n"]
    if n:
        parts.append(f"🚨 <b>Leak incidents 24h:</b> {n}")
    else:
        parts.append("<b>Leaks:</b> clean (0)")

    # === Probe library ===
    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE active) AS active,
               COUNT(*) FILTER (WHERE definition->>'origin' = 'opus_generated') AS opus
          FROM leo_qa_probes WHERE rail='sim'
    """)
    r = cur.fetchone()
    parts.append(f"<b>Library:</b> {r['active']} active probes ({r['opus']} Opus-generated)")

    # === Header ===
    header = f"📊 <b>Sim Daily — {datetime.now(timezone.utc):%Y-%m-%d}</b>"
    text = header + "\n\n" + "\n\n".join(parts)

    if tg_send is None:
        print(text); return
    try:
        tg_send(JONATHAN, text, source="watchdog",
                recipient_name="Jonathan", override_rate_limit=True)
        print(f"[digest] sent ({len(text)} chars)")
    except Exception as e:
        print(f"[digest] send failed: {e}", file=sys.stderr)
        print(text)
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
