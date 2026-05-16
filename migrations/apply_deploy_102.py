#!/usr/bin/env python3
"""Deploy 102 — Wire chat_notes + assets into Context Builder.

Per Jonathan: "is this data being incorporated into the RAG yet?"
Answer was 'partially — synthesis yes, notes + assets no'. This closes
that gap.

Changes:
  A. Two new Postgres nodes after Fetch Pending Questions:
       - Fetch Chat Notes (top 15 by importance + recency, case-scoped)
       - Fetch Case Assets (top 15 by area_sqm + status, case-scoped)
  B. Context Builder reads both and injects into agentInput as:
       CASE NOTES (operator observations, evidence flags, prior decisions)
       CASE ASSETS (structured property ledger — TCT/OCT/declarations)
  C. AI Agent prompt addition: tells Leo these sections exist and how to use.
"""
import json, os, sys, uuid, argparse, time
sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

WF_NAME = "Leos Workflow"
POSTGRES_CRED = {"id": "kPUGFA1HrZZFWnzI", "name": "Postgres account 2"}

# Use case_file derived from clientRow (case_file = c.case_file)
FETCH_CHAT_NOTES_SQL = """(SELECT id, related_case AS case_file, topic, importance, summary,
        LEFT(content, 600) AS content_excerpt, created_at::text AS created_at
   FROM chat_notes
  WHERE related_case = (
    SELECT case_file FROM clients
     WHERE telegram_id = '{{ $('Telegram Trigger').first().json.message.from.id }}'::text
     LIMIT 1
  )
  ORDER BY importance DESC NULLS LAST, id DESC
  LIMIT 15)
UNION ALL SELECT NULL::int, NULL::text, NULL::text, NULL::int, NULL::text, NULL::text, NULL::text;"""

FETCH_ASSETS_SQL = """(SELECT id, asset_type, canonical_id, case_file, area_sqm, current_status,
        current_holder, LEFT(notes, 300) AS notes_excerpt, provenance_level
   FROM assets
  WHERE case_file = (
    SELECT case_file FROM clients
     WHERE telegram_id = '{{ $('Telegram Trigger').first().json.message.from.id }}'::text
     LIMIT 1
  )
  ORDER BY area_sqm DESC NULLS LAST, id DESC
  LIMIT 15)
UNION ALL SELECT NULL::int, NULL::text, NULL::text, NULL::text, NULL::real, NULL::text, NULL::text, NULL::text, NULL::text;"""


def build_new_nodes(base_pos):
    x, y = base_pos
    return [
        {
            "id": str(uuid.uuid4()),
            "name": "Fetch Chat Notes",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.6,
            "position": [x + 100, y + 100],
            "parameters": {"operation": "executeQuery", "query": FETCH_CHAT_NOTES_SQL, "options": {}},
            "credentials": {"postgres": POSTGRES_CRED},
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Fetch Case Assets",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.6,
            "position": [x + 300, y + 100],
            "parameters": {"operation": "executeQuery", "query": FETCH_ASSETS_SQL, "options": {}},
            "credentials": {"postgres": POSTGRES_CRED},
        },
    ]


# ── Context Builder JS additions ──────────────────────────────────────────
CB_FETCH_BLOCK_NEW = """// ── caseNotes + caseAssets (deploy_102 — full RAG integration) ────────
let caseNotes = [];
try {
  caseNotes = $('Fetch Chat Notes').all().map(i => i.json).filter(r => r && r.id);
} catch (e) {}
let caseAssets = [];
try {
  caseAssets = $('Fetch Case Assets').all().map(i => i.json).filter(r => r && r.id);
} catch (e) {}

// ── pendingQuestions (deploy 094 — One question at a time) ────────────"""

CB_OLD_PQ = """// ── pendingQuestions (deploy 094 — One question at a time) ────────────"""

CB_INPUT_ANCHOR = """RECENT CONVERSATION HISTORY (last 4):"""

# Note: deploy_077 changed limit to 15 but anchor string still says (last 4)
CB_INPUT_ANCHOR_15 = """RECENT CONVERSATION HISTORY (last 15):"""

CB_AGENT_INPUT_NEW_SECTIONS = """
CASE NOTES (operator observations, evidence flags, prior decisions — use these to anchor your response in established context):
${caseNotes.length === 0 ? '(none for this case)' : caseNotes.slice(0,10).map(n => `[note:${n.id}] (${n.topic||'?'}, imp ${n.importance||'?'}): ${n.summary || (n.content_excerpt || '').slice(0,120)}`).join('\\n')}

CASE ASSETS (structured property ledger — refer by canonical_id when discussing):
${caseAssets.length === 0 ? '(none)' : caseAssets.slice(0,10).map(a => `${a.canonical_id} [${a.asset_type}, ${a.current_status||'?'}, area=${a.area_sqm||'?'}sqm, ${a.provenance_level}] ${a.notes_excerpt || ''}`).join('\\n')}

"""

CB_RETURN_ANCHOR = "    pendingQuestions,"
CB_RETURN_NEW = "    pendingQuestions,\n    caseNotes,\n    caseAssets,"


def patch_context_builder(node):
    js = node["parameters"]["jsCode"]
    changed = False
    if "caseNotes" not in js:
        if CB_OLD_PQ not in js:
            raise ValueError("Context Builder pendingQuestions marker not found")
        js = js.replace(CB_OLD_PQ, CB_FETCH_BLOCK_NEW)
        changed = True
    # Inject new sections into agentInput (look for either 4 or 15 limit anchor)
    if "CASE NOTES (operator observations" not in js:
        anchor = CB_INPUT_ANCHOR_15 if CB_INPUT_ANCHOR_15 in js else CB_INPUT_ANCHOR
        if anchor not in js:
            raise ValueError("agentInput RECENT CONVERSATION anchor not found")
        js = js.replace(anchor, CB_AGENT_INPUT_NEW_SECTIONS + anchor)
        changed = True
    if CB_RETURN_ANCHOR in js and "caseNotes,\n    caseAssets" not in js:
        js = js.replace(CB_RETURN_ANCHOR, CB_RETURN_NEW)
        changed = True
    node["parameters"]["jsCode"] = js
    return changed


PROMPT_ANCHOR = "### ONE question per turn + answer tracking (added 2026-05-16 — deploy_094)"

PROMPT_ADDITION = """### CASE NOTES + CASE ASSETS in your input (added 2026-05-16 — deploy_102)

Two new sections in your agentInput give you DEEP case context:

**CASE NOTES** (top 10 of 15 fetched, sorted by importance DESC):
  - Each has [note:id], topic, importance (1-5), and summary/content excerpt
  - These are operator observations, evidence flags, decisions, and prior chat-notes
  - WHEN ANSWERING: cite specific notes by id ("Per note:54, Don Qi confirmed...")
  - WHEN INVESTIGATING: scan for prior notes about the topic BEFORE asking a new question

**CASE ASSETS** (top 10 of 15 fetched, sorted by area_sqm DESC):
  - Each entry: <canonical_id> [type, status, area, provenance] notes
  - These are the structured property ledger — TCTs, OCTs, declarations
  - WHEN DISCUSSING PROPERTIES: refer by canonical_id (TCT-4497) AND cite the area/status
  - WHEN A NEW DOC ARRIVES: check if its referenced TCTs match existing assets
  - For status='contested' assets: treat with extra care, flag in chat_note

These join your existing context (clientRow.client_intelligence_summary,
recent_documents, recent conversations, pendingInquiries, pendingContext,
pendingQuestions). The case notes + assets are the granular substrate
that lets you give specific, evidence-backed answers — exactly what
Jonathan asked for ("understanding all the assets, the law, and the
evidence at a granular level")."""


def patch_prompt(node):
    p = node["parameters"]["options"]["systemMessage"]
    if "CASE NOTES + CASE ASSETS in your input" in p:
        return False
    if PROMPT_ANCHOR not in p:
        raise ValueError("ONE-question rule anchor not found")
    p = p.replace(PROMPT_ANCHOR, PROMPT_ANCHOR + "\n\n" + PROMPT_ADDITION + "\n")
    node["parameters"]["options"]["systemMessage"] = p
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["staging", "prod"], required=True)
    args = ap.parse_args()
    DSN = dict(host="172.18.0.3", port=5432, dbname="n8n", user="n8n", password="n8npassword") if args.target == "prod" else dict(host="127.0.0.1", port=5433, dbname="n8n", user="n8n", password="n8npassword")
    print(f"  target={args.target}")

    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name=%s", (WF_NAME,))
    wf_id, nodes, conns = cur.fetchone()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_102_{args.target}_{ts}.json"
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes, "connections": conns}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    fpq = next((n for n in nodes if n["name"] == "Fetch Pending Questions"), None)
    if not fpq:
        sys.exit("FATAL: Fetch Pending Questions not found")
    base_pos = fpq.get("position", [400, 0])

    existing = {n["name"] for n in nodes}
    to_add = [n for n in build_new_nodes(base_pos) if n["name"] not in existing]
    nodes.extend(to_add)
    print(f"  ✓ added {len(to_add)} nodes")

    # Wire: Fetch Pending Questions -> Fetch Chat Notes -> Fetch Case Assets -> Context Builder
    fpq_main = conns.get("Fetch Pending Questions", {}).get("main", [[]])
    # Redirect Fetch Pending Questions -> Fetch Chat Notes
    for branch in fpq_main:
        for t in branch:
            if t.get("node") == "Context Builder":
                t["node"] = "Fetch Chat Notes"
    conns["Fetch Pending Questions"] = {"main": fpq_main}
    conns["Fetch Chat Notes"] = {"main": [[{"node": "Fetch Case Assets", "type": "main", "index": 0}]]}
    conns["Fetch Case Assets"] = {"main": [[{"node": "Context Builder", "type": "main", "index": 0}]]}
    print("  ✓ wired: Fetch Pending Questions -> Fetch Chat Notes -> Fetch Case Assets -> Context Builder")

    cb = next((n for n in nodes if n["name"] == "Context Builder"), None)
    if cb and patch_context_builder(cb):
        print("  ✓ Context Builder: caseNotes + caseAssets injected into agentInput")

    aia = next((n for n in nodes if n["name"] == "AI Agent"), None)
    if aia and patch_prompt(aia):
        print("  ✓ AI Agent prompt: CASE NOTES + CASE ASSETS guidance added")

    cur.close(); conn.close()
    if args.target == "prod":
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes, connections=conns)
    else:
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute('UPDATE workflow_entity SET nodes=%s::jsonb, connections=%s::jsonb, "updatedAt"=now() WHERE id=%s', (json.dumps(nodes), json.dumps(conns), wf_id))
        cur.execute("""UPDATE workflow_history SET nodes=%s::json, connections=%s::json WHERE "workflowId"=%s AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""", (json.dumps(nodes), json.dumps(conns), wf_id, wf_id))
        cur.execute('UPDATE workflow_entity SET active=false WHERE id=%s', (wf_id,))
        conn.commit(); time.sleep(2)
        cur.execute('UPDATE workflow_entity SET active=true WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()
        print("  ✓ staging done")


if __name__ == "__main__":
    main()
