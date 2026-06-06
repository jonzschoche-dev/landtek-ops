#!/usr/bin/env python3
"""deploy_358 — Simulator must improve the system (closed loop).

Companion scripts:
  simulator_improvement_loop.py  — fail → $0 refresh → re-verify
  holes/c3_simulator_regression.py — chronic failures → holes_findings P0

Re-seeds remediation_hint on architecture probes from YAML.
"""
import json
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from landtek_core import db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    path = os.path.join(ROOT, "probes", "architecture_probe_library.yaml")
    with open(path) as f:
        data = yaml.safe_load(f)
    probes = data.get("probes") or []

    with db() as cur:
        for p in probes:
            cur.execute(
                """
                UPDATE leo_qa_probes
                   SET definition = definition || %s::jsonb,
                       notes = COALESCE(%s, notes)
                 WHERE name = %s
                """,
                (
                    json.dumps(
                        {
                            "remediation_hint": p.get("remediation_hint"),
                            "harm_if_broken": p.get("harm_if_broken"),
                        }
                    ),
                    p.get("harm_if_broken"),
                    p["name"],
                ),
            )

        cur.execute("""
            CREATE OR REPLACE VIEW v_simulator_probe_trend AS
            SELECT ssr.probe_name,
                   COUNT(*) FILTER (WHERE ssr.passed) AS passes,
                   COUNT(*) FILTER (WHERE NOT ssr.passed) AS fails,
                   COUNT(DISTINCT ssr.session_id) AS sessions,
                   MAX(ss.started_at) FILTER (WHERE NOT ssr.passed) AS last_fail,
                   MAX(ss.started_at) FILTER (WHERE ssr.passed) AS last_pass
              FROM simulator_session_results ssr
              JOIN simulator_sessions ss ON ss.id = ssr.session_id
             WHERE ss.started_at > now() - interval '30 days'
             GROUP BY ssr.probe_name
             ORDER BY fails DESC, ssr.probe_name
        """)

        cur.execute("""
            INSERT INTO deploy_log (deploy_id, summary) VALUES (
              'deploy_358',
              'Simulator improvement loop: fail→refresh→re-verify; C3_simulator_regression '
              'holes routine; v_simulator_probe_trend. Simulator worthless without pass-rate lift.'
            )
            ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
        """)

    print("✓ deploy_358: simulator improvement loop wired")
    print("  python3 scripts/simulator_improvement_loop.py --session <id> --full")


if __name__ == "__main__":
    main()