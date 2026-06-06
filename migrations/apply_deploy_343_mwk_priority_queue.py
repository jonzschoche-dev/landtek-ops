#!/usr/bin/env python3
"""apply_deploy_343_mwk_priority_queue.py — autonomous MWK priority ranking.

  (1) Fix v_client_goals to include obligations keyed by case_file (MWK-CV26360 bug)
  (2) Document ranker in deploy_log
  (3) Companion: scripts/mwk_priority_ranker.py + refresh_mwk_priorities.py

No schema tables — ranking is computed from existing spine on each run.
"""
from __future__ import annotations
import os
import subprocess
import sys

import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()

    print("deploy_343 — MWK autonomous priority queue")
    print("=" * 60)

    cur.execute("""
        CREATE OR REPLACE VIEW v_client_goals AS
        SELECT ('obligation_' || o.id::text) AS goal_id,
               COALESCE(
                 NULLIF(o.client_code, ''),
                 CASE WHEN o.case_file = 'MWK-001' THEN 'MWK-001'
                      WHEN o.case_file = 'Paracale-001' THEN 'Paracale-001'
                      ELSE o.client_code END
               ) AS client_code,
               'landtek_duty'::text AS goal_kind,
               o.short_label,
               o.description,
               o.status,
               o.priority,
               o.matter_code,
               'landtek_obligations'::text AS source_table,
               o.id::text AS source_id
          FROM landtek_obligations o
         WHERE o.status IN ('open','in_progress','blocked')
        UNION ALL
        SELECT ('need_' || n.id::text) AS goal_id,
               n.client_code,
               'client_outcome'::text AS goal_kind,
               n.short_label,
               n.description,
               n.status,
               n.priority,
               NULL::text AS matter_code,
               'client_needs'::text AS source_table,
               n.id::text AS source_id
          FROM client_needs n
         WHERE n.status IN ('open','escalated')
    """)
    print("  ✓ v_client_goals (case_file-aware client_code)")

    cur.execute("""
        INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_343',
         'MWK autonomous priority queue: mwk_priority_ranker.py ranks deadlines+matters+evidence_gaps+obligations+fraud from DB (tier×1000+days). refresh_mwk_priorities.py → MWK_PRIORITIES_TEXT. v_client_goals fixed for MWK obligations keyed as MWK-CV26360.')
        ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
    """)

    cur.execute("SELECT COUNT(*) FROM v_client_goals WHERE client_code = 'MWK-001'")
    print(f"  MWK-001 goals visible: {cur.fetchone()[0]}")

    cur.close()
    conn.close()

    print("\n[preview] Top 8 priorities:")
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "mwk_priority_ranker.py"), "--top", "8"],
        check=False,
    )


if __name__ == "__main__":
    main()