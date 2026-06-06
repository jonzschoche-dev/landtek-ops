#!/usr/bin/env python3
"""refresh_mwk_hard_facts.py — verified-only CV-26360 facts for Leo Context Builder.

Per Jonathan 2026-06-06: agent acts on hard facts, no guessing.
Injects MWK_CV26360_HARD_FACTS_TEXT — matter row, verified chat_notes,
verified assessments, completed deadlines. No inferred_strong content.
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


def fetch_hard_facts(cur) -> dict:
    cur.execute("""
        SELECT matter_code, current_stage, next_event, next_deadline, stage_notes,
               docket_number, court_or_agency, lead_counsel, status
          FROM matters WHERE matter_code = 'MWK-CV26360'
    """)
    matter = cur.fetchone()

    cur.execute("""
        SELECT id, created_at, content, citation_ref
          FROM (
            SELECT cn.id, cn.created_at, cn.content,
                   'chat_notes#' || cn.id ||
                   COALESCE(' tg_msg=' || cn.telegram_msg_id, '') AS citation_ref
              FROM chat_notes cn
             WHERE cn.archived IS NOT TRUE
               AND cn.provenance_level = 'verified'
               AND cn.importance >= 4
               AND (cn.related_case = 'MWK-001'
                    OR cn.content ILIKE '%26-360%'
                    OR cn.content ILIKE '%26360%')
             ORDER BY cn.created_at DESC
             LIMIT 8
          ) q
    """)
    notes = cur.fetchall()

    cur.execute("""
        SELECT subject_id, assessment_text, implication
          FROM assessments
         WHERE client_code = 'MWK-001'
           AND provenance_level = 'verified'
           AND confidence = 'verified'
           AND (assessment_text ILIKE '%26360%'
                OR assessment_text ILIKE '%26-360%'
                OR assessment_text ILIKE '%mediation%')
         ORDER BY created_at DESC
         LIMIT 5
    """)
    assessments = cur.fetchall()

    cur.execute("""
        SELECT id, title, due_date, status
          FROM case_deadlines
         WHERE case_file = 'MWK-001'
           AND (title ILIKE '%26360%' OR title ILIKE '%mediation%' OR title ILIKE '%pretrial%')
         ORDER BY due_date
         LIMIT 6
    """)
    deadlines = cur.fetchall()

    cur.execute("""
        SELECT et.claim_id, c.short_label, d.id AS doc_id, d.smart_filename, et.weight
          FROM evidence_trail et
          JOIN claims c ON c.id = et.claim_id
          JOIN documents d ON d.id = et.supporting_doc_id
         WHERE c.case_file = 'MWK-001'
           AND et.provenance_level = 'verified'
           AND c.short_label IN ('Cesar_SPA_revoked_2005', 'Balane_title_void_chain')
         ORDER BY c.id, et.weight
    """)
    verified_exhibits = cur.fetchall()

    return {
        "matter": matter,
        "notes": notes,
        "assessments": assessments,
        "deadlines": deadlines,
        "exhibits": verified_exhibits,
    }


def render_facts(d: dict) -> str:
    at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "",
        f"MWK CV-26360 HARD FACTS (verified-only, refreshed {at}):",
        "RULE: Act ONLY on items below. If not listed → say 'not on record' — DO NOT infer.",
        "",
    ]
    m = d.get("matter")
    if m:
        lines.append(f"MATTER {m['matter_code']} [{m['status']}]")
        lines.append(f"  stage: {m['current_stage']}")
        lines.append(f"  next: {m['next_event']}")
        if m.get("next_deadline"):
            lines.append(f"  deadline: {m['next_deadline']}")
        if m.get("stage_notes"):
            lines.append(f"  notes: {(m['stage_notes'] or '')[:240]}")
        lines.append("")

    if d["notes"]:
        lines.append("VERIFIED OPERATOR REPORTS:")
        for n in d["notes"]:
            lines.append(f"  [{n['citation_ref']}] {(n['content'] or '')[:220]}")
        lines.append("")

    if d["assessments"]:
        lines.append("VERIFIED ASSESSMENTS:")
        for a in d["assessments"]:
            lines.append(f"  chat_note#{a['subject_id']}: {a['assessment_text'][:200]}")
        lines.append("")

    if d["deadlines"]:
        lines.append("DEADLINES (DB status):")
        for dl in d["deadlines"]:
            lines.append(f"  #{dl['id']} {dl['due_date']} [{dl['status']}] {dl['title'][:80]}")
        lines.append("")

    if d["exhibits"]:
        lines.append("VERIFIED EXHIBITS (evidence_trail provenance=verified):")
        for ex in d["exhibits"]:
            lines.append(
                f"  [{ex['short_label']}] {ex['weight']} doc#{ex['doc_id']} "
                f"{(ex['smart_filename'] or '')[:60]}"
            )
        lines.append("")

    lines.append("INFERRED content is intentionally OMITTED. Query DB if operator asks for draft hypotheses.")
    return "\n".join(lines)


def patch_const(code: str, body: str) -> tuple[str, bool]:
    const = "MWK_CV26360_HARD_FACTS_TEXT"
    if f"const {const}" in code:
        m = re.search(rf"(const {const}\s*=\s*`)([^`]*)(`;)", code, re.DOTALL)
        if not m:
            raise RuntimeError(f"{const} pattern broken")
        if m.group(2).strip() == body.strip():
            return (code, False)
        return (code[: m.start(2)] + body + code[m.end(2):], True)

    anchor = "const MWK_PRIORITIES_TEXT"
    if anchor not in code:
        anchor = "const OBJECTIVES_TEXT"
    pos = code.find(anchor)
    if pos < 0:
        raise RuntimeError("No anchor for MWK_CV26360_HARD_FACTS_TEXT")
    end = code.find("`;", pos) + 2
    new_const = f"\n\nconst MWK_CV26360_HARD_FACTS_TEXT = `{body}`;\n"
    code = code[:end] + new_const + code[end:]
    ret_anchor = "`;\n\nreturn [{"
    inject = "${isSimulation ? '' : MWK_CV26360_HARD_FACTS_TEXT}"
    if ret_anchor in code and inject not in code:
        code = code.replace(
            ret_anchor,
            f"\n{inject}\n" + ret_anchor,
            1,
        )
    return (code, True)


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        d = fetch_hard_facts(cur)
        body = render_facts(d)
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
            print("[refresh_mwk_hard_facts] no change")
            conn.rollback()
            return
        cur.execute(
            "INSERT INTO leo_workflow_snapshots (workflow_id, reason, nodes_json, connections_json, notes) "
            "VALUES (%s,%s,%s::jsonb,%s::jsonb,%s) RETURNING id",
            (WORKFLOW_ID, "refresh_mwk_hard_facts", json.dumps(nodes), json.dumps(conns), "hard_facts"),
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
        print(f"[refresh_mwk_hard_facts] applied snapshot #{sid}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()