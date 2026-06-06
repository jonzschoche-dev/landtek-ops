#!/usr/bin/env python3
"""refresh_evidence_facts.py — regenerate Context Builder EVIDENCE_TRAIL_FACTS_TEXT.

Reads live claims + v_evidence_trail_per_claim + v_filing_gaps and rewrites
the EVIDENCE_TRAIL_FACTS_TEXT const in Context Builder JS so Leo sees the
current claim → evidence map every turn.

Includes:
  - All open claims with their supporting LT-NNNN list
  - Current filing gaps (claims needing more primary exhibits)
  - Doc count per role (just totals so Leo knows the inventory shape)

Cron every 10 minutes — reflects Jonathan's categorization work quickly.
Snapshot taken before any change (rollback via leo_workflow_snapshots).
"""
from __future__ import annotations
import json, os, re, subprocess, sys, time
import psycopg2, psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"


def fetch_evidence(cur) -> dict:
    cur.execute("""
        SELECT id, case_file, claim_text, short_label, status, priority, supporting_docs
          FROM v_evidence_trail_per_claim
         WHERE status = 'open'
         ORDER BY priority DESC, id
    """)
    claims = cur.fetchall()
    cur.execute("""
        SELECT c.short_label, d.id AS doc_id, d.lt_number, et.weight, et.relation_kind
          FROM evidence_trail et
          JOIN claims c ON c.id = et.claim_id
          JOIN documents d ON d.id = et.supporting_doc_id
         WHERE et.provenance_level = 'verified'
           AND c.case_file = 'MWK-001'
         ORDER BY c.priority DESC, et.weight
    """)
    verified_exhibits = cur.fetchall()
    cur.execute("SELECT claim_id, short_label, primary_count, strong_or_better FROM v_filing_gaps")
    gaps = cur.fetchall()
    cur.execute("""
        SELECT doc_role, COUNT(*) AS n
          FROM documents
         WHERE doc_role IS NOT NULL
         GROUP BY doc_role
         ORDER BY n DESC
    """)
    roles = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM documents WHERE lt_number IS NOT NULL")
    docs_total = cur.fetchone()["count"]
    return {"claims": claims, "gaps": gaps, "roles": roles, "docs_total": docs_total,
            "verified_exhibits": verified_exhibits}


def render_facts(d: dict) -> str:
    lines = [
        "",
        "EVIDENCE TRAIL — current claim → exhibit map (from v_evidence_trail_per_claim, refreshed every 10 min):",
        "",
    ]
    for c in d["claims"]:
        label = c["short_label"] or f"claim_{c['id']}"
        docs = c["supporting_docs"] or []
        lines.append(f"  [{label}] (priority {c['priority']}) {c['claim_text']}")
        if not docs:
            lines.append(f"      ⚠️ NO EXHIBITS YET LINKED — this claim is unsupported in the trail")
        else:
            for ex in docs[:8]:
                w = ex.get("weight") or "?"
                lt = ex.get("lt_number") or f"doc_{ex.get('doc_id')}"
                rel = ex.get("relation") or "?"
                lines.append(f"      {w:<10s} {lt}  ({rel}) {ex.get('filename','')[:60]}")
        lines.append("")

    if d["gaps"]:
        lines.append("ACTIVE FILING GAPS (open claims with <2 primary exhibits):")
        for g in d["gaps"]:
            lines.append(f"  • [{g['short_label']}] primary={g['primary_count']} "
                         f"strong+={g['strong_or_better']}")
        lines.append("")

    if d["roles"]:
        lines.append(f"DOC INVENTORY ({d['docs_total']} total docs with LT-NNNN):")
        for r in d["roles"]:
            lines.append(f"  {r['doc_role']:25s} {r['n']}")
        unassessed = d["docs_total"] - sum(r["n"] for r in d["roles"])
        if unassessed > 0:
            lines.append(f"  not_yet_assessed         {unassessed}")
        lines.append("")

    if d.get("verified_exhibits"):
        lines.append("VERIFIED EXHIBITS ONLY (provenance_level=verified — cite these as facts):")
        for ex in d["verified_exhibits"]:
            lt = ex.get("lt_number") or f"doc#{ex['doc_id']}"
            lines.append(f"  [{ex['short_label']}] {ex['weight']} {lt} ({ex['relation_kind']})")
        lines.append("")

    lines.append("HARD-FACTS RULE (deploy_347):")
    lines.append("  - State as FACT only exhibits in VERIFIED EXHIBITS above or doc# with execution_status executed/government_issued.")
    lines.append("  - Claim→exhibit links with inferred_strong provenance = HYPOTHESIS — say 'not verified on record'.")
    lines.append("  - If no verified exhibit: say 'no verified exhibit linked' — DO NOT guess.")
    lines.append("  - NEVER fabricate LT-NNNN or doc# identifiers.")
    return "\n".join(lines)


def patch_const(code: str, body: str) -> tuple[str, bool]:
    """Replace EVIDENCE_TRAIL_FACTS_TEXT value; insert if missing."""
    if "const EVIDENCE_TRAIL_FACTS_TEXT" in code:
        m = re.search(
            r"(const EVIDENCE_TRAIL_FACTS_TEXT\s*=\s*`)([^`]*)(`;)",
            code, re.DOTALL,
        )
        if not m:
            raise RuntimeError("EVIDENCE_TRAIL_FACTS_TEXT marker found but value pattern broken")
        if m.group(2).strip() == body.strip():
            return (code, False)
        return (code[: m.start(2)] + body + code[m.end(2):], True)

    # First insertion — put it right after TITLE_CHAIN_FACTS_TEXT const
    title_const_end = code.find("`;", code.find("const TITLE_CHAIN_FACTS_TEXT"))
    if title_const_end < 0:
        raise RuntimeError("TITLE_CHAIN_FACTS_TEXT const not found; can't anchor evidence facts")
    insertion_point = title_const_end + 2  # after `;
    new_const = "\n\nconst EVIDENCE_TRAIL_FACTS_TEXT = `" + body + "`;\n"
    code = code[:insertion_point] + new_const + code[insertion_point:]

    # Also inject interpolation into agentInput template — right before closing backtick
    ret_anchor = "`;\n\nreturn [{"
    if ret_anchor in code and "${EVIDENCE_TRAIL_FACTS_TEXT}" not in code:
        code = code.replace(ret_anchor, "\n${EVIDENCE_TRAIL_FACTS_TEXT}\n" + ret_anchor, 1)
    return (code, True)


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        d = fetch_evidence(cur)
        body = render_facts(d)
        print(f"[refresh_evidence_facts] {len(d['claims'])} claims, "
              f"{len(d['gaps'])} gaps, {d['docs_total']} docs")

        cur.execute("SELECT nodes, connections FROM workflow_entity WHERE id=%s FOR UPDATE",
                    (WORKFLOW_ID,))
        row = cur.fetchone()
        nodes, conns = row["nodes"], row["connections"]
        cb = next((n for n in nodes if n.get("name") == "Context Builder"), None)
        if not cb:
            raise RuntimeError("Context Builder missing")
        code = cb["parameters"]["jsCode"]
        new_code, changed = patch_const(code, body)
        if not changed:
            print("[refresh_evidence_facts] no change"); conn.rollback(); return

        cur.execute(
            "INSERT INTO leo_workflow_snapshots (workflow_id, reason, nodes_json, connections_json, notes) "
            "VALUES (%s,%s,%s::jsonb,%s::jsonb,%s) RETURNING id",
            (WORKFLOW_ID, "refresh_evidence_facts auto-regen",
             json.dumps(nodes), json.dumps(conns), "evidence_facts_refresh"),
        )
        sid = cur.fetchone()["id"]
        print(f"[refresh_evidence_facts] snapshot #{sid}")

        cb["parameters"]["jsCode"] = new_code
        cur.execute('UPDATE workflow_entity SET nodes=%s, "updatedAt"=now() WHERE id=%s',
                    (json.dumps(nodes), WORKFLOW_ID))
        conn.commit()

        subprocess.run(["python3","/root/landtek/scripts/sync_workflow_history.py",WORKFLOW_ID],
                       check=True, capture_output=True, text=True, timeout=30)
        subprocess.run(["docker","restart","n8n-n8n-1"], check=True, capture_output=True, timeout=60)
        deadline = time.time() + 60
        while time.time() < deadline:
            r = subprocess.run(["curl","-sf","http://localhost:5678/healthz"],
                               capture_output=True, timeout=5)
            if r.returncode == 0:
                break
            time.sleep(2)
        print(f"[refresh_evidence_facts] applied; rollback snapshot #{sid}")
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
