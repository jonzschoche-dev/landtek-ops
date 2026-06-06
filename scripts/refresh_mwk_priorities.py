#!/usr/bin/env python3
"""refresh_mwk_priorities.py — wire MWK priority queue into Leo Context Builder.

Every 10 min: regenerates MWK_PRIORITIES_TEXT (SQL-only ranker, $0 tokens).
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from mwk_priority_ranker import build_queue, render_leo_const  # noqa: E402


def patch_const(code: str, body: str) -> tuple[str, bool]:
    if "const MWK_PRIORITIES_TEXT" in code:
        m = re.search(r"(const MWK_PRIORITIES_TEXT\s*=\s*`)([^`]*)(`;)", code, re.DOTALL)
        if not m:
            raise RuntimeError("MWK_PRIORITIES_TEXT pattern broken")
        if m.group(2).strip() == body.strip():
            return (code, False)
        return (code[: m.start(2)] + body + code[m.end(2):], True)

    anchor = "const OBJECTIVES_TEXT"
    if anchor not in code:
        raise RuntimeError("OBJECTIVES_TEXT not found — deploy_332 must be live")
    obj_end = code.find("`;", code.find(anchor))
    insertion = obj_end + 2
    new_const = "\n\nconst MWK_PRIORITIES_TEXT = `" + body + "`;\n"
    code = code[:insertion] + new_const + code[insertion:]
    ret_anchor = "`;\n\nreturn [{"
    if ret_anchor in code and "${MWK_PRIORITIES_TEXT}" not in code:
        code = code.replace(
            ret_anchor,
            "\n${MWK_PRIORITIES_TEXT}\n" + ret_anchor,
            1,
        )
    return (code, True)


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        queue = build_queue(cur)
        body = render_leo_const(queue)
        cur.execute(
            "SELECT nodes, connections FROM workflow_entity WHERE id=%s FOR UPDATE",
            (WORKFLOW_ID,),
        )
        row = cur.fetchone()
        if not row:
            print("[refresh_mwk_priorities] workflow_entity missing — stdout only")
            print(body)
            conn.rollback()
            return
        nodes, conns = row["nodes"], row["connections"]
        cb = next((n for n in nodes if n.get("name") == "Context Builder"), None)
        if not cb:
            raise RuntimeError("Context Builder missing")
        code = cb["parameters"]["jsCode"]
        new_code, changed = patch_const(code, body)
        if not changed:
            print(f"[refresh_mwk_priorities] no change ({datetime.now(timezone.utc).isoformat()})")
            conn.rollback()
            return
        cur.execute(
            "INSERT INTO leo_workflow_snapshots (workflow_id, reason, nodes_json, connections_json, notes) "
            "VALUES (%s,%s,%s::jsonb,%s::jsonb,%s) RETURNING id",
            (WORKFLOW_ID, "refresh_mwk_priorities", json.dumps(nodes), json.dumps(conns), "mwk_priorities"),
        )
        sid = cur.fetchone()["id"]
        cb["parameters"]["jsCode"] = new_code
        cur.execute(
            "UPDATE workflow_entity SET nodes=%s WHERE id=%s",
            (json.dumps(nodes), WORKFLOW_ID),
        )
        conn.commit()
        landtek = "/root/landtek" if os.path.isdir("/root/landtek") else ROOT
        subprocess.run(
            ["python3", os.path.join(landtek, "scripts/sync_workflow_history.py"), WORKFLOW_ID],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        subprocess.run(["docker", "restart", "n8n-n8n-1"], check=True, capture_output=True, timeout=60)
        deadline = time.time() + 60
        while time.time() < deadline:
            if subprocess.run(
                ["curl", "-sf", "http://localhost:5678/healthz"],
                capture_output=True,
                timeout=5,
            ).returncode == 0:
                break
            time.sleep(2)
        print(f"[refresh_mwk_priorities] applied snapshot #{sid} ({len(queue)} items ranked)")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()