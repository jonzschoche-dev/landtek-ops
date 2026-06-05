#!/usr/bin/env python3
"""deploy_322.py — Rule S8: owner-engagement on case-fact queries.

Leo has been refusing JONATHAN on case-fact queries — *"I'm not authorized
to share information about this matter"* — even though sim-jonathan has
sim_target_role='owner' (deploy_308b) and real Jonathan is the operator.
Likely cause: proposal #7's 'never reply empty' rule pushed Leo toward
defensive refusal templates that bleed into the owner-asks path.

Rule S8 explicitly gates the refusal templates by telegram_id. When
sender is Jonathan (6513067717) or sim-jonathan (999000001), refusal
templates are FORBIDDEN; Leo must consult his loaded context and answer.
Impersonators and strangers continue to be refused (sender check is
specific, not inverted).

Snapshot taken pre-patch. Restart sequence verified.
"""
from __future__ import annotations
import json, os, subprocess, sys, time
import psycopg2, psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
WORKFLOW_ID = "vSDQv1vfn6627bnA"

RULE_S8 = """
# Rule S8 — Owner engagement on case-fact queries (deploy_322 — CRITICAL)

When the sender is real Jonathan (telegram_id=6513067717) OR a sim with
sim_target_role='owner' (sim-jonathan, telegram_id=999000001), case-fact
queries about the MWK-001 universe MUST be ANSWERED with sourced information
from your loaded context, NOT REFUSED.

Case-fact queries include (non-exhaustive):
  - Title chain (derivatives, parent titles, lifecycle status, verified edges)
  - Transferee / defendant identity (named persons, telegram_ids, case files)
  - Document content (deeds, SPAs, instruments, encumbrances, notaries)
  - Evidence trail (which LT-NNNN exhibits support which claims, with weights)
  - Mandate invariants (MMK≠MWK, T-30683 separate, verified derivative chains)
  - Counts and aggregates (open claims, filing gaps, fraud indicators, etc.)
  - System state (probe library size, recent execs, business health)

PROCEDURE for these queries:
  1. Consult your loaded context first:
     - TITLE CHAIN FACTS (auto-loaded every refresh cycle)
     - EVIDENCE TRAIL FACTS (auto-loaded every 10 min)
     - Active landscape, recent conversations, case_file context
  2. If the answer is fully in loaded context: answer directly with
     citations (cite by LT-NNNN, by parent → child for chain, etc.).
  3. If a tool call is required (query_documents, get_party_history,
     cross_reference, etc.): invoke the tool. Do NOT refuse the request
     just because you'd need a tool.
  4. If data is not in context and no tool retrieves it: say
     "I cannot find a verified record of that in my loaded context or
     via available tools. Treat as unknown."
  5. NEVER fabricate. If you don't know, say you don't know.

ABSOLUTELY FORBIDDEN refusal templates when sender is Jonathan OR sim-jonathan:
  ✗ "I'm not authorized to share information about this matter"
  ✗ "I'm not able to share case-specific information through this channel"
  ✗ "Please coordinate access through the appropriate channel"
  ✗ "Please coordinate access through the principal contact"
  ✗ "I'm not authorized to share case intelligence"
  ✗ "I'm not able to share document acquisition details through this channel"
  ✗ Any phrasing implying Jonathan needs authorization to ask about his own case.

These templates are for IMPERSONATORS (sim-allan-shape, sim-kristyle-shape,
shape impersonators with sim_target_role IS NULL) and STRANGERS
(sim-stranger, sim_target_role='unauthorized'). They are NEVER for Jonathan.

Rule precedence: S8 OVERRIDES S5 (operator anonymity) when sender IS the
operator. S5 protects Jonathan's identity FROM third parties; it does NOT
restrict Jonathan from asking about his own case.
"""


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT nodes, connections FROM workflow_entity WHERE id=%s FOR UPDATE",
                    (WORKFLOW_ID,))
        row = cur.fetchone()
        nodes, conns = row["nodes"], row["connections"]

        cur.execute(
            "INSERT INTO leo_workflow_snapshots (workflow_id, reason, nodes_json, connections_json, notes) "
            "VALUES (%s,%s,%s::jsonb,%s::jsonb,%s) RETURNING id",
            (WORKFLOW_ID, "pre-deploy_322 Rule S8 owner engagement",
             json.dumps(nodes), json.dumps(conns), "deploy_322"),
        )
        sid = cur.fetchone()["id"]
        print(f"  snapshot #{sid}")

        agent = next((n for n in nodes if n.get("name") == "AI Agent"), None)
        opts = agent.setdefault("parameters", {}).setdefault("options", {})
        sm = opts.get("systemMessage", "")
        if "deploy_322" in sm:
            print("  Rule S8 already present")
            conn.rollback(); return
        sep = "\n\n" if sm and not sm.endswith("\n") else ""
        opts["systemMessage"] = sm + sep + RULE_S8.strip() + "\n"
        print(f"  AI Agent systemMessage: {len(sm)} → {len(opts['systemMessage'])}")

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
        print(f"\n✓ deploy_322 applied  rollback: scripts/leo_proposal_apply.py --rollback {sid}")
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
