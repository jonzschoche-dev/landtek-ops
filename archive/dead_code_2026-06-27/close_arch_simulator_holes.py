#!/usr/bin/env python3
"""Close stale C3 holes for architecture probes that now pass (session #2 12/12)."""
from __future__ import annotations

import os

import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

ARCH_PROBES = [
    "arch.arta_0747_op_deadline",
    "arch.gmail_38220_citation",
    "arch.mediation_impasse_cv26360",
    "arch.promo_not_on_spine",
    "arch.email_legal_event_policy",
    "arch.del_rosario_1210_may",
    "arch.dual_arta_manifestations",
    "arch.no_barandon_blocker_0747",
]


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()
    for name in ARCH_PROBES:
        cur.execute(
            """
            UPDATE holes_findings
               SET status = 'remediated',
                   remediated_at = now(),
                   remediated_via = 'manual_arch_12of12',
                   remediated_by = 'deploy_360_session2'
             WHERE status = 'open'
               AND routine_name = 'C3_simulator_regression'
               AND metadata->>'probe_name' = %s
            """,
            (name,),
        )
        print(f"  {name}: closed {cur.rowcount} finding(s)")
    cur.execute("SELECT COUNT(*) FROM holes_findings WHERE status='open'")
    print(f"open holes remaining: {cur.fetchone()[0]}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()