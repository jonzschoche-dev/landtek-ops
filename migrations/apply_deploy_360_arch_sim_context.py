#!/usr/bin/env python3
"""deploy_360 — inject architecture context blocks during simulation.

deploy_331 correctly stripped only heavy consts (title_chain, evidence_trail,
realtime_flow) from sim execs. Later refresh scripts over-stripped OBJECTIVES,
CLIENT_HISTORY, MWK_PENDING_MATTERS, MWK_PRIORITIES, and MWK_CV26360_HARD_FACTS —
so architecture probes graded Leo with zero matter/spine context.

Fix: always inject the lightweight architecture blocks; keep heavy-strip for sim.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ARCH_STRIPS = [
    ("${isSimulation ? '' : OBJECTIVES_TEXT}", "${OBJECTIVES_TEXT}"),
    ("${isSimulation ? '' : CLIENT_HISTORY_TEXT}", "${CLIENT_HISTORY_TEXT}"),
    ("${isSimulation ? '' : MWK_PENDING_MATTERS_TEXT}", "${MWK_PENDING_MATTERS_TEXT}"),
    ("${isSimulation ? '' : MWK_PRIORITIES_TEXT}", "${MWK_PRIORITIES_TEXT}"),
    ("${isSimulation ? '' : MWK_CV26360_HARD_FACTS_TEXT}", "${MWK_CV26360_HARD_FACTS_TEXT}"),
]
MARKER = "deploy_360_arch_sim_context"


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT nodes, connections FROM workflow_entity WHERE id=%s FOR UPDATE",
            (WORKFLOW_ID,),
        )
        nodes, conns = cur.fetchone()
        cb = next(n for n in nodes if n.get("name") == "Context Builder")
        code = cb["parameters"]["jsCode"]

        if MARKER in code:
            print(f"✓ {MARKER} already applied")
            conn.rollback()
            return

        new_code = code
        applied = 0
        for old, new in ARCH_STRIPS:
            if old in new_code:
                new_code = new_code.replace(old, new, 1)
                applied += 1

        if applied == 0:
            print("⚠ no architecture sim-strips found — manual check needed")
            conn.rollback()
            return

        new_code = new_code.rstrip() + f"\n// {MARKER} — architecture blocks always injected\n"
        cb["parameters"]["jsCode"] = new_code

        cur.execute(
            "INSERT INTO leo_workflow_snapshots (workflow_id, reason, nodes_json, connections_json, notes) "
            "VALUES (%s,%s,%s::jsonb,%s::jsonb,%s) RETURNING id",
            (WORKFLOW_ID, MARKER, json.dumps(nodes), json.dumps(conns), "arch_sim_context"),
        )
        sid = cur.fetchone()[0]
        cur.execute("UPDATE workflow_entity SET nodes=%s WHERE id=%s", (json.dumps(nodes), WORKFLOW_ID))
        cur.execute(
            """
            INSERT INTO deploy_log (deploy_id, summary) VALUES (
              'deploy_360',
              'Architecture sim context: inject OBJECTIVES/CLIENT_HISTORY/MWK blocks during simulation; '
              'keep deploy_331 heavy-strip for title_chain/evidence_trail/realtime_flow only.'
            )
            ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
            """
        )
        conn.commit()

        subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts/sync_workflow_history.py"), WORKFLOW_ID],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        subprocess.run(["docker", "restart", "n8n-n8n-1"], check=True, capture_output=True, timeout=60)
        print(f"✓ deploy_360: un-stripped {applied} architecture blocks (snapshot #{sid})")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()