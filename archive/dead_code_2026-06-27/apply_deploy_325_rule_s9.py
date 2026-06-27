#!/usr/bin/env python3
"""deploy_325_flow.py — Rule S9 + 8 flow-awareness probes.

Rule S9: when Jonathan greets / asks open-endedly ("what's up?", "status?",
"any updates?"), Leo MUST surface the REAL-TIME FLOW context proactively —
pending decisions first, imminent items next, velocity as a footnote.

8 probes test flow awareness across the cycle.
"""
from __future__ import annotations
import json, os, subprocess, sys, time
import psycopg2, psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
WORKFLOW_ID = "vSDQv1vfn6627bnA"

RULE_S9 = """
# Rule S9 — Proactive flow awareness (deploy_325)

Leo has REAL-TIME FLOW data refreshed every 5 minutes covering pending
decisions, imminent deadlines, recent activity, and velocity signals.

When Jonathan opens a session with an open-ended question — "what's
going on?", "any updates?", "what needs me?", "status?", or simply "hi"
followed by no specific ask — you MUST proactively summarize from the
REAL-TIME FLOW section, structured as:

  1. PENDING DECISIONS — lead here. Count + breakdown of:
     - Leo improvement proposals pending
     - Evidence trail proposals pending
     - Doc role proposals ready to approve
  2. IMMINENT — only if anything is < 14 days out:
     - Pretrial timeline
     - Calendar events
     - Open pending inquiries about to expire
  3. RECENT ACTIVITY — only if non-trivial (>0 real-client messages,
     new docs, new emails).
  4. VELOCITY — short footer: bonafide pass rate trend, proposals
     applied/verified in last 24h.

Concise. ~4-7 lines total unless he asks for more.

Do NOT surface this for case-specific queries — only when the question
is open-ended or about general state. Case-specific queries still get
case-specific answers per Rule S8.

When asked "what changed since I last logged in?" or "what did I miss?":
  - The REAL-TIME FLOW counts are CURRENT TOTALS, not deltas.
  - If you need delta information ("what's new in last hour"), state
    that your current snapshot is a point-in-time. Don't fabricate
    deltas you don't have.
"""


PROBES = [
    ("flow.open_ended_status_query",
     "999000001", "warn", "engage_helpfully",
     "Hey Leo — what's going on right now?",
     ["pending"],
     ["I'm not authorized", "I cannot share status"]),
    ("flow.what_needs_me_now",
     "999000001", "warn", "engage_helpfully",
     "What needs my attention right now?",
     ["pending"],
     ["nothing", "all clear"]),
    ("flow.any_updates_query",
     "999000001", "warn", "engage_helpfully",
     "Any updates I should know about?",
     ["pending"],
     ["I'm not authorized"]),
    ("flow.imminent_deadlines_status",
     "999000001", "warn", "engage_helpfully",
     "Status check — any imminent deadlines or events I should prep for?",
     ["pretrial", "days"],
     ["no deadlines", "nothing on the horizon"]),
    ("flow.proposals_awaiting_decision",
     "999000001", "warn", "engage_helpfully",
     "How many Opus proposals are awaiting my decision right now?",
     ["proposal"],
     ["I cannot share", "I'm not authorized"]),
    ("flow.evidence_proposals_status",
     "999000001", "warn", "engage_helpfully",
     "What's the status on evidence trail proposals from the doc → claim mapper?",
     ["evidence", "proposal"],
     ["I'm not authorized"]),
    ("flow.recent_real_activity_summary",
     "999000001", "warn", "engage_helpfully",
     "Summarize real-client activity in the last 24 hours.",
     ["client"],
     ["I'm not authorized to share"]),
    ("flow.bonafide_engagement_trend",
     "999000001", "info", "engage_helpfully",
     "How is the bonafide engagement rate trending?",
     ["pass rate", "engage"],
     ["I cannot share metrics"]),
]


def patch_rule(nodes):
    for n in nodes:
        if n.get("name") == "AI Agent":
            opts = n.setdefault("parameters", {}).setdefault("options", {})
            sm = opts.get("systemMessage", "")
            if "deploy_325" in sm: return False
            sep = "\n\n" if sm and not sm.endswith("\n") else ""
            opts["systemMessage"] = sm + sep + RULE_S9.strip() + "\n"
            return True
    raise RuntimeError("AI Agent missing")


def insert_probes(cur):
    n = 0
    for name, sender, sev, intent, prompt, expected, forbidden in PROBES:
        cur.execute("""
            INSERT INTO leo_qa_probes (name, rail, cadence_min, definition, severity, category, intent, notes)
            VALUES (%s, 'sim', 60, %s::jsonb, %s, 'evidence_trail', %s, %s)
            ON CONFLICT (name) DO NOTHING RETURNING id
        """, (name,
              json.dumps({
                  "kind": "simulator_prompt",
                  "origin": "hand_authored_flow_awareness",
                  "prompt_text": prompt,
                  "sim_sender_telegram_id": sender,
                  "expected_substrings": [s.lower() for s in expected],
                  "forbidden_substrings": [s.lower() for s in forbidden],
                  "rationale": "Real-time flow awareness probe",
              }), sev, intent,
              "deploy_325 flow awareness probe"))
        if cur.fetchone(): n += 1
    return n


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT nodes, connections FROM workflow_entity WHERE id=%s FOR UPDATE",
                    (WORKFLOW_ID,))
        row = cur.fetchone(); nodes, conns = row["nodes"], row["connections"]
        cur.execute(
            "INSERT INTO leo_workflow_snapshots (workflow_id, reason, nodes_json, connections_json, notes) "
            "VALUES (%s,%s,%s::jsonb,%s::jsonb,%s) RETURNING id",
            (WORKFLOW_ID, "pre-deploy_325 Rule S9",
             json.dumps(nodes), json.dumps(conns), "deploy_325"),
        )
        sid = cur.fetchone()["id"]; print(f"  snapshot #{sid}")
        changed = patch_rule(nodes); print(f"  Rule S9 added: {changed}")
        cur.autocommit = True
        n_probes = insert_probes(cur); print(f"  flow probes inserted: {n_probes}")
        if changed:
            cur.execute('UPDATE workflow_entity SET nodes=%s, "updatedAt"=now() WHERE id=%s',
                        (json.dumps(nodes), WORKFLOW_ID))
            conn.commit()
            subprocess.run(["python3","/root/landtek/scripts/sync_workflow_history.py",WORKFLOW_ID],
                           check=True, capture_output=True, text=True, timeout=30)
            subprocess.run(["docker","restart","n8n-n8n-1"], check=True, capture_output=True, timeout=60)
            deadline = time.time() + 60
            while time.time() < deadline:
                if subprocess.run(["curl","-sf","http://localhost:5678/healthz"],
                                  capture_output=True, timeout=5).returncode == 0: break
                time.sleep(2)
        print(f"\n✓ deploy_325 applied  rollback #{sid}")
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
