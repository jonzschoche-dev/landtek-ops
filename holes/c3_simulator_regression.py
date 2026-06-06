"""holes.c3_simulator_regression — simulator failures must drive fixes.

Reads simulator_session_results + leo_qa_sim_payloads. Emits holes_findings when:
  1. A probe failed in the latest session (actionable regression)
  2. Same probe failed ≥3 sessions without a remediated finding (chronic)

Companion: scripts/simulator_improvement_loop.py runs $0 context refreshes
then re-verifies failed probes — the closed loop.
"""
from __future__ import annotations

from holes.base import Routine, run_cli


class C3_SimulatorRegression(Routine):
    name = "C3_simulator_regression"
    version = "v1"
    hole_type = "discipline_drift"
    cadence = "daily"
    severity_default = "P1"
    description = (
        "Simulator ran but system did not improve — chronic probe failures "
        "and unremediated architecture regressions."
    )

    def find_holes(self, cur):
        cur.execute("""
            SELECT ssr.probe_name,
                   ssr.fail_reason,
                   ssr.passed,
                   ss.id AS session_id,
                   ss.started_at,
                   p.definition->>'harm_if_broken' AS harm,
                   p.definition->>'remediation_hint' AS remediation_hint,
                   p.severity AS probe_severity
              FROM simulator_session_results ssr
              JOIN simulator_sessions ss ON ss.id = ssr.session_id
              LEFT JOIN leo_qa_probes p ON p.name = ssr.probe_name
             WHERE ss.status = 'done'
               AND ss.started_at > now() - interval '48 hours'
               AND ssr.passed = false
             ORDER BY ss.started_at DESC, ssr.probe_name
        """)
        recent_fails = cur.fetchall()
        seen_latest: set[str] = set()
        for row in recent_fails:
            if row["probe_name"] in seen_latest:
                continue
            seen_latest.add(row["probe_name"])
            fix = row["remediation_hint"] or (
                "Run: python3 scripts/simulator_improvement_loop.py --session "
                f"{row['session_id']} --full"
            )
            self.emit(
                severity="P1" if row["probe_severity"] == "critical" else "P2",
                description=(
                    f"Simulator FAIL [{row['probe_name']}]: "
                    f"{(row['fail_reason'] or 'unknown')[:200]}"
                ),
                matter_code=_matter_from_probe(row["probe_name"]),
                suggested_fix=fix,
                fix_command=(
                    "python3 scripts/simulator_improvement_loop.py "
                    f"--probe {row['probe_name']} --full"
                ),
                auto_remediable=True,
                metadata={
                    "session_id": row["session_id"],
                    "probe_name": row["probe_name"],
                    "harm_if_broken": row["harm"],
                },
                hash_parts={"probe_name": row["probe_name"], "kind": "latest_fail"},
            )

        cur.execute("""
            WITH per_probe AS (
              SELECT ssr.probe_name,
                     COUNT(DISTINCT ssr.session_id) AS fail_sessions,
                     MAX(ss.started_at) AS last_fail
                FROM simulator_session_results ssr
                JOIN simulator_sessions ss ON ss.id = ssr.session_id
               WHERE ss.status = 'done'
                 AND ss.started_at > now() - interval '14 days'
                 AND ssr.passed = false
               GROUP BY ssr.probe_name
              HAVING COUNT(DISTINCT ssr.session_id) >= 3
            )
            SELECT pp.probe_name, pp.fail_sessions, pp.last_fail
              FROM per_probe pp
             WHERE NOT EXISTS (
                   SELECT 1 FROM holes_findings hf
                    WHERE hf.routine_name = %s
                      AND hf.status = 'remediated'
                      AND hf.metadata->>'probe_name' = pp.probe_name
                      AND hf.remediated_at > pp.last_fail - interval '7 days'
                 )
        """, (self.name,))
        for row in cur.fetchall():
            self.emit(
                severity="P0",
                description=(
                    f"CHRONIC simulator regression: {row['probe_name']} failed "
                    f"{row['fail_sessions']} sessions in 14d — system not improving."
                ),
                suggested_fix=(
                    "Inspect Leo context const for this probe; update "
                    "refresh_mwk_* scripts or hard_facts; then "
                    f"simulator_improvement_loop.py --probe {row['probe_name']} --full"
                ),
                metadata={
                    "probe_name": row["probe_name"],
                    "fail_sessions": row["fail_sessions"],
                    "kind": "chronic",
                },
                hash_parts={"probe_name": row["probe_name"], "kind": "chronic"},
            )


def _matter_from_probe(name: str) -> str | None:
    if "0747" in name:
        return "MWK-ARTA-0747"
    if "1210" in name:
        return "MWK-ARTA-1210"
    if "cv26360" in name or "mediation" in name:
        return "MWK-CV26360"
    if "dilg" in name:
        return "MWK-ARTA-DILG"
    return None


if __name__ == "__main__":
    run_cli(C3_SimulatorRegression)