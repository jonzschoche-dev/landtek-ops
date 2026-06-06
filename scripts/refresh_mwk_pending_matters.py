#!/usr/bin/env python3
"""refresh_mwk_pending_matters.py — ARTA + OP + civil matter registry for Leo.

Jonathan 2026-06-06: agent unaware of pending ARTA and OP cases.
OBJECTIVES_TEXT only shows case_file aggregates; MWK_CV26360_HARD_FACTS is
CV-only. This block lists every active matter row from DB (hard facts).
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


def fetch_pending(cur) -> dict:
    cur.execute("""
        SELECT matter_code, title, status, current_stage, court_or_agency,
               docket_number, next_event, next_deadline, lead_counsel
          FROM matters
         WHERE case_file = 'MWK-001'
           AND status = 'active'
         ORDER BY
           CASE
             WHEN matter_code LIKE 'MWK-ARTA%' THEN 1
             WHEN matter_code LIKE 'MWK-OP%' THEN 2
             WHEN matter_code LIKE 'MWK-CV%' THEN 3
             ELSE 4
           END,
           matter_code
    """)
    matters = cur.fetchall()

    cur.execute("""
        SELECT id, short_label, description, priority, status, matter_code
          FROM landtek_obligations
         WHERE case_file = 'MWK-001'
           AND status IN ('open', 'in_progress', 'blocked')
         ORDER BY priority DESC, id
    """)
    obligations = cur.fetchall()

    cur.execute("""
        SELECT id, smart_filename, doc_date_norm, execution_status
          FROM documents
         WHERE case_file = 'MWK-001'
           AND (smart_filename ILIKE '%OP%ARTA%'
                OR smart_filename ILIKE '%PETITION%OP%'
                OR id IN (702, 703, 972))
         ORDER BY id
    """)
    op_docs = cur.fetchall()

    return {"matters": matters, "obligations": obligations, "op_docs": op_docs}


def _track(mc: str, agency: str | None) -> str:
    if mc.startswith("MWK-ARTA"):
        return "ARTA"
    if mc.startswith("MWK-OP") or (agency and "president" in (agency or "").lower()):
        return "OP"
    if mc.startswith("MWK-CV"):
        return "CIVIL"
    if mc == "MWK-ESTATE":
        return "ESTATE"
    return "OTHER"


def render_pending(d: dict) -> str:
    at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "",
        f"MWK PENDING MATTERS — registered DB rows (refreshed {at}):",
        "RULE: When Jonathan asks about pending cases, ARTA, or OP — answer FROM THIS BLOCK.",
        "Each line is a matters row. Cite matter_code. Do not invent dockets not listed here.",
        "",
    ]

    by_track: dict[str, list] = {}
    for m in d["matters"]:
        by_track.setdefault(_track(m["matter_code"], m.get("court_or_agency")), []).append(m)

    for track in ("ARTA", "OP", "CIVIL", "ESTATE", "OTHER"):
        rows = by_track.get(track)
        if not rows:
            continue
        lines.append(f"── {track} ({len(rows)} active) ──")
        for m in rows:
            due = f" | due {m['next_deadline']}" if m.get("next_deadline") else ""
            docket = m.get("docket_number") or "—"
            stage = m.get("current_stage") or "—"
            agency = (m.get("court_or_agency") or "")[:50]
            lines.append(f"  {m['matter_code']} | {docket} | {stage}{due}")
            lines.append(f"    agency: {agency}")
            lines.append(f"    title: {(m.get('title') or '')[:100]}")
            if m.get("next_event"):
                lines.append(f"    next: {m['next_event'][:200]}")
        lines.append("")

    if d["op_docs"]:
        lines.append("── OP / ARTA-1210 PRIMARY DOCS (corpus) ──")
        for doc in d["op_docs"]:
            lines.append(
                f"  doc#{doc['id']} [{doc.get('execution_status') or '?'}] "
                f"{(doc.get('smart_filename') or '')[:70]}"
            )
        lines.append("")

    if d["obligations"]:
        lines.append("── OPEN OBLIGATIONS (landtek_obligations) ──")
        for o in d["obligations"]:
            mc = o.get("matter_code") or "(unlinked)"
            lines.append(
                f"  #{o['id']} P{o['priority']} [{mc}] {o['short_label']}: "
                f"{(o.get('description') or '')[:160]}"
            )
        lines.append("")

    arta_n = len(by_track.get("ARTA", []))
    lines.append(
        f"SUMMARY: {arta_n} active ARTA dockets; "
        f"OP track includes MWK-ARTA-1210 (Bagong Pilipinas) + MWK-OP-PETITION if registered."
    )
    lines.append("Resolved/closed ARTA (-0690, -0792) are NOT listed — status=closed in DB.")
    return "\n".join(lines)


def patch_const(code: str, body: str) -> tuple[str, bool]:
    const = "MWK_PENDING_MATTERS_TEXT"
    if f"const {const}" in code:
        m = re.search(rf"(const {const}\s*=\s*`)([^`]*)(`;)", code, re.DOTALL)
        if not m:
            raise RuntimeError(f"{const} pattern broken")
        if m.group(2).strip() == body.strip():
            return (code, False)
        return (code[: m.start(2)] + body + code[m.end(2):], True)

    anchor = "const MWK_CV26360_HARD_FACTS_TEXT"
    if anchor not in code:
        anchor = "const MWK_PRIORITIES_TEXT"
    pos = code.find(anchor)
    end = code.find("`;", pos) + 2
    new_const = f"\n\nconst {const} = `{body}`;\n"
    code = code[:end] + new_const + code[end:]

    inject = "${isSimulation ? '' : MWK_PENDING_MATTERS_TEXT}"
    agent_anchor = "${isSimulation ? '' : MWK_PRIORITIES_TEXT}"
    if agent_anchor in code and inject not in code:
        code = code.replace(agent_anchor, f"{inject}\n\n{agent_anchor}", 1)
    return (code, True)


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        d = fetch_pending(cur)
        body = render_pending(d)
        cur.execute(
            "SELECT nodes, connections FROM workflow_entity WHERE id=%s FOR UPDATE",
            (WORKFLOW_ID,),
        )
        row = cur.fetchone()
        if not row:
            print(body)
            conn.rollback()
            return
        nodes, conns = row["nodes"], row["connections"]
        cb = next((n for n in nodes if n.get("name") == "Context Builder"), None)
        if not cb:
            raise RuntimeError("Context Builder missing")
        new_code, changed = patch_const(cb["parameters"]["jsCode"], body)
        if not changed:
            print("[refresh_mwk_pending_matters] no change")
            conn.rollback()
            return
        cur.execute(
            "INSERT INTO leo_workflow_snapshots (workflow_id, reason, nodes_json, connections_json, notes) "
            "VALUES (%s,%s,%s::jsonb,%s::jsonb,%s) RETURNING id",
            (WORKFLOW_ID, "refresh_mwk_pending_matters", json.dumps(nodes), json.dumps(conns), "pending_matters"),
        )
        sid = cur.fetchone()["id"]
        cb["parameters"]["jsCode"] = new_code
        cur.execute("UPDATE workflow_entity SET nodes=%s WHERE id=%s", (json.dumps(nodes), WORKFLOW_ID))
        conn.commit()
        landtek = "/root/landtek" if os.path.isdir("/root/landtek") else ROOT
        subprocess.run(
            [sys.executable, os.path.join(landtek, "scripts/sync_workflow_history.py"), WORKFLOW_ID],
            check=True, capture_output=True, text=True, timeout=30,
        )
        subprocess.run(["docker", "restart", "n8n-n8n-1"], check=True, capture_output=True, timeout=60)
        print(f"[refresh_mwk_pending_matters] applied snapshot #{sid} "
              f"({len(d['matters'])} active matters)")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()