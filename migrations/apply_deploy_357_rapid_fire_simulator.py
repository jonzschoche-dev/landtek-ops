#!/usr/bin/env python3
"""deploy_357 — Rapid-fire architecture simulator.

Jonathan: establish simulator for rapid-fire inquiries to improve architecture.

1. simulator_sessions + simulator_session_results — burst run audit
2. Seed probes/architecture_probe_library.yaml → leo_qa_probes (rail=sim)
3. v_simulator_sessions_24h — pass-rate dashboard
4. systemd: leo-rapid-fire.timer (architecture burst 2×/day)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from landtek_core import db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_arch_probes() -> list[dict]:
    path = os.path.join(ROOT, "probes", "architecture_probe_library.yaml")
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("probes") or []


def main():
    probes = load_arch_probes()
    pack = "architecture"

    with db() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS simulator_sessions (
                id           serial PRIMARY KEY,
                started_at   timestamptz NOT NULL DEFAULT now(),
                completed_at timestamptz,
                pack         text NOT NULL,
                burst_size   integer NOT NULL DEFAULT 0,
                passed       integer,
                failed       integer,
                status       text NOT NULL DEFAULT 'running',
                details      jsonb
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_sim_sessions_started
              ON simulator_sessions(started_at DESC)
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS simulator_session_results (
                id           bigserial PRIMARY KEY,
                session_id   integer NOT NULL REFERENCES simulator_sessions(id) ON DELETE CASCADE,
                probe_id     integer REFERENCES leo_qa_probes(id),
                probe_name   text NOT NULL,
                payload_id   bigint REFERENCES leo_qa_sim_payloads(id),
                passed       boolean NOT NULL,
                fail_reason  text,
                recorded_at  timestamptz NOT NULL DEFAULT now()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_sim_session_results_session
              ON simulator_session_results(session_id)
        """)
        cur.execute("""
            CREATE OR REPLACE VIEW v_simulator_sessions_24h AS
            SELECT s.id,
                   s.pack,
                   s.started_at,
                   s.completed_at,
                   s.burst_size,
                   s.passed,
                   s.failed,
                   CASE WHEN s.burst_size > 0
                        THEN round(100.0 * s.passed / s.burst_size, 1)
                        ELSE NULL END AS pass_pct
              FROM simulator_sessions s
             WHERE s.started_at > now() - interval '24 hours'
               AND s.status = 'done'
             ORDER BY s.started_at DESC
        """)

        inserted = updated = 0
        for p in probes:
            defn = {
                "kind": "simulator_prompt",
                "pack": pack,
                "prompt_text": (p["prompt"] or "").strip(),
                "sim_sender_telegram_id": p["sender_id"],
                "expected_substrings": p.get("expected_all") or [],
                "expected_any": p.get("expected_any") or [],
                "forbidden_substrings": p.get("forbidden") or [],
                "harm_if_broken": p.get("harm_if_broken"),
                "remediation_hint": p.get("remediation_hint"),
            }
            cur.execute(
                """
                INSERT INTO leo_qa_probes (name, rail, cadence_min, definition, severity, notes, active)
                VALUES (%s, 'sim', 0, %s, %s, %s, true)
                ON CONFLICT (name) DO UPDATE SET
                    definition = EXCLUDED.definition,
                    severity   = EXCLUDED.severity,
                    notes      = EXCLUDED.notes,
                    active     = true
                RETURNING xmax = 0 AS is_new
                """,
                (
                    p["name"],
                    json.dumps(defn),
                    p.get("severity", "warn"),
                    p.get("harm_if_broken", ""),
                ),
            )
            if cur.fetchone()["is_new"]:
                inserted += 1
            else:
                updated += 1

        cur.execute("""
            INSERT INTO deploy_log (deploy_id, summary) VALUES (
              'deploy_357',
              'Rapid-fire architecture simulator: 12 arch probes, simulator_sessions audit, '
              'rapid_fire_simulator.py burst CLI, leo-rapid-fire.timer 2x/day.'
            )
            ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
        """)

    # Install systemd units on VPS
    unit_src = os.path.join(ROOT, "infra", "systemd")
    if os.path.isdir(unit_src):
        for name in ("leo-rapid-fire.service", "leo-rapid-fire.timer"):
            src = os.path.join(unit_src, name)
            if os.path.isfile(src):
                shutil.copy2(src, f"/etc/systemd/system/{name}")

    subprocess.run(["systemctl", "daemon-reload"], check=False)
    # Timer installed but disabled — L4 bursts are on-demand, not scheduled.
    subprocess.run(["systemctl", "disable", "leo-rapid-fire.timer"], check=False)
    subprocess.run(["systemctl", "stop", "leo-rapid-fire.timer"], check=False)

    print(
        f"✓ deploy_357: rapid-fire simulator "
        f"arch_probes inserted={inserted} updated={updated} "
        f"total={len(probes)}"
    )
    print("  CLI: python3 scripts/rapid_fire_simulator.py --pack architecture --burst 12")
    print("  Timer: leo-rapid-fire.timer installed DISABLED (use rapid_fire on-demand)")


if __name__ == "__main__":
    main()