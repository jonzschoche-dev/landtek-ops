#!/usr/bin/env python3
"""leo_proposal_auto_verify.py — auto-run the verifier on ready proposals.

Cron every 30 minutes. Finds any proposal with status='applied' that has
sat for ≥ 30 minutes since applied_at AND has ≥ 3 sim runs per target probe
since applied_at. Invokes leo_proposal_verify.py for it.

Jonathan still APPLIES proposals manually (deploy_305 invariant), but once
applied, the verify step is mechanical and runs without him having to remember.
"""
from __future__ import annotations
import os, subprocess, sys
import psycopg2, psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    # Proposals applied at least 30 min ago, status='applied'
    cur.execute("""
        SELECT id, target_probes, applied_at
          FROM leo_improvement_proposals
         WHERE status = 'applied'
           AND applied_at < now() - interval '30 minutes'
         ORDER BY applied_at ASC
    """)
    ready = cur.fetchall()
    if not ready:
        print("[auto-verify] no proposals due")
        return
    for p in ready:
        # Need ≥ 3 runs per target probe since applied_at
        cur.execute("""
            SELECT COUNT(DISTINCT name) FILTER (WHERE runs >= 3) AS qualified,
                   COUNT(DISTINCT name) AS targets
              FROM (
                SELECT pr.name, COUNT(s.id) AS runs
                  FROM unnest(%s::text[]) AS pr(name)
                  LEFT JOIN leo_qa_probes pp ON pp.name = pr.name
                  LEFT JOIN leo_qa_sim_payloads s
                    ON s.probe_id = pp.id AND s.posted_at > %s
                 GROUP BY pr.name
              ) t
        """, (p["target_probes"], p["applied_at"]))
        r = cur.fetchone()
        if (r["qualified"] or 0) < (r["targets"] or 1):
            print(f"[auto-verify] proposal {p['id']} not enough data "
                  f"({r['qualified']}/{r['targets']} target probes hit ≥3 runs)")
            continue
        # Trigger the verifier
        print(f"[auto-verify] running verifier for proposal #{p['id']}")
        subprocess.run(
            ["python3", "/root/landtek/scripts/leo_proposal_verify.py", str(p["id"])],
            capture_output=False,
        )


if __name__ == "__main__":
    main()
