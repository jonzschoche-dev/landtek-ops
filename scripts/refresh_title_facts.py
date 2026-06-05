#!/usr/bin/env python3
"""refresh_title_facts.py — regenerate Context Builder TITLE_CHAIN_FACTS_TEXT.

Reads the live `title_chain` table and rewrites the hardcoded
TITLE_CHAIN_FACTS_TEXT const in the Context Builder JS so Leo always
sees the current verified chain — including new derivatives confirmed
by heightened OCR runs.

Includes:
  - All verified parent→child edges for case_file='MWK-001'
  - Explicit separate-matter entries (T-30683, T-4494)
  - MMK ≠ MWK invariant

Idempotent: skips workflow update if generated const matches current.
Takes a snapshot to leo_workflow_snapshots before changing.
Cron daily at 06:00 UTC.
"""
from __future__ import annotations
import json, os, re, subprocess, sys, time
from collections import defaultdict
import psycopg2, psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"


SEPARATE_MATTERS = [
    ("T-30683", "Manguisoc Mercedes",
     "held in undivided interest by the four MWK heirs; NOT a verified derivative of T-4497; treat as its own matter."),
    ("T-4494", "Cabanbanan San Vicente",
     "separate property; NOT a verified derivative of T-4497; treat as its own matter."),
]

MMK_INVARIANT = (
    "MWK = Mary Worrick Keesey (the verified spelling — 307 corpus occurrences "
    "including her birth certificate and the RTC Order caption). MMK is a "
    "distinct identifier and must NOT be conflated with MWK or with Mary "
    "Worrick Keesey (deploy_275 invariant)."
)


def fetch_chain(cur) -> dict:
    """Returns {parent_title: [child_title, …]} for verified edges in MWK-001."""
    cur.execute("""
        SELECT parent_title, child_title
          FROM title_chain
         WHERE provenance_level = 'verified'
           AND case_file = 'MWK-001'
         ORDER BY parent_title, child_title
    """)
    chain = defaultdict(list)
    for r in cur.fetchall():
        chain[r["parent_title"]].append(r["child_title"])
    return chain


def render_facts(chain: dict) -> str:
    lines = [
        "",
        "TITLE CHAIN FACTS (VERIFIED — from title_chain WHERE provenance_level='verified' AND case_file='MWK-001'):",
        "",
    ]
    # Sort parents by tree-significance: T-4497 first, then its children, then everything else
    PRIORITY = ["T-4497", "T-32916", "T-32917", "T-31298"]
    ordered = [p for p in PRIORITY if p in chain] + sorted(
        [p for p in chain.keys() if p not in PRIORITY]
    )
    for parent in ordered:
        kids = chain[parent]
        kids_str = ", ".join(kids)
        lines.append(f"  {parent}  →  {kids_str}")
    lines.append("")
    lines.append("SEPARATE MATTERS (these are NOT derivatives of T-4497):")
    for tct, name, note in SEPARATE_MATTERS:
        lines.append(f"  • {tct} ({name}) — {note}")
    lines.append("")
    lines.append("INVARIANT — MMK ≠ MWK:")
    lines.append(f"  {MMK_INVARIANT}")
    lines.append("")
    lines.append("When answering \"is X a derivative of T-4497?\":")
    lines.append("  - If X appears as direct or sub-derivative above: YES, it IS a derivative.")
    lines.append("  - If X appears in SEPARATE MATTERS: NO, it is a separate matter (cite the reason).")
    lines.append("  - If X appears nowhere: say \"I don't have a verified record of T-X in the title chain; treat as unverified.\"")
    lines.append("NEVER affirm or deny derivative relationships not backed by this list.")
    return "\n".join(lines)


def patch_const(code: str, new_body: str) -> tuple[str, bool]:
    """Replace TITLE_CHAIN_FACTS_TEXT value with new_body. Returns (new_code, changed)."""
    m = re.search(
        r"(const TITLE_CHAIN_FACTS_TEXT\s*=\s*`)([^`]*)(`;)",
        code, re.DOTALL,
    )
    if not m:
        raise RuntimeError("TITLE_CHAIN_FACTS_TEXT const not found in Context Builder")
    old_body = m.group(2)
    if old_body.strip() == new_body.strip():
        return (code, False)
    new_code = code[: m.start(2)] + new_body + code[m.end(2):]
    return (new_code, True)


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        chain = fetch_chain(cur)
        body = render_facts(chain)
        print(f"[refresh_title_facts] {len(chain)} parents, "
              f"{sum(len(v) for v in chain.values())} verified edges")

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
            print("[refresh_title_facts] const already current — no-op")
            conn.rollback(); return

        # snapshot
        cur.execute(
            "INSERT INTO leo_workflow_snapshots (workflow_id, reason, nodes_json, connections_json, notes) "
            "VALUES (%s,%s,%s::jsonb,%s::jsonb,%s) RETURNING id",
            (WORKFLOW_ID, "refresh_title_facts auto-regen",
             json.dumps(nodes), json.dumps(conns), "title_facts_refresh"),
        )
        sid = cur.fetchone()["id"]
        print(f"[refresh_title_facts] snapshot #{sid}")

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
        print(f"[refresh_title_facts] applied; rollback snapshot #{sid}")
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
