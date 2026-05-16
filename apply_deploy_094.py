#!/usr/bin/env python3
"""Deploy 094 — One question per turn + answer-tracking loop.

Per Jonathan's directive: "one question at a time for telegram chats,
make sure there is a place for the reply so that LEO is learning from
the boss or client what's expected."

Implementation:

A. Prompt: when Leo asks a clarifying question, it MUST be ONE question
   only (highest priority), ending with the explicit reply marker:
   "👉 Reply with your answer."

B. AI output schema gains `pending_question_to_log: { question_text,
   topic, context }` — when emitted, downstream workflow logs the
   question in pending_questions table with asked_of_telegram_id =
   current chat.

C. AI output schema gains `pending_question_resolution: { id,
   answer_text }` — when a sender's message answers an open pending
   question, Leo sets this and the workflow marks the row answered.

D. Workflow:
   - New Postgres node "Fetch Pending Questions For Sender" — gets
     up-to-3 open questions for the current sender, sorted by priority
     + asked_at.
   - Context Builder injects pendingQuestionsForSender into agentInput.
   - New nodes after Parse Agent1: handle pending_question_to_log
     (INSERT) and pending_question_resolution (UPDATE).

For educate_leo: instead of sending all 7 clarification_questions in
one DM, log them to pending_questions and send ONLY the top one. As
Jonathan answers, the next ones surface naturally.
"""
import json, os, sys, uuid, argparse, time
sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

WF_NAME = "Leos Workflow"
POSTGRES_CRED = {"id": "kPUGFA1HrZZFWnzI", "name": "Postgres account 2"}

# ── SQL queries ───────────────────────────────────────────────────────────
FETCH_PQ_SQL = """(SELECT id, question, context, topic, priority, asked_by, created_at::text AS asked_at
  FROM pending_questions
 WHERE asked_of_telegram_id = '{{ $('Telegram Trigger').first().json.message.from.id }}'::text
   AND status = 'pending'
 ORDER BY priority::integer ASC NULLS LAST, created_at ASC
 LIMIT 3)
UNION ALL SELECT NULL::int, NULL::text, NULL::text, NULL::text, NULL::text, NULL::text, NULL::text;"""

INSERT_PQ_SQL = """INSERT INTO pending_questions (
  asked_of_telegram_id, asked_by, case_file, topic, question, context, source, priority, status
)
VALUES (
  '{{ $json.pending_question_to_log.asked_of_telegram_id || $json.senderId }}'::text,
  'leo'::text,
  NULLIF('{{ $json.case_file }}', 'Unknown')::text,
  NULLIF('{{ $json.pending_question_to_log.topic }}', '')::text,
  '{{ $json.pending_question_to_log.question_text }}'::text,
  NULLIF('{{ $json.pending_question_to_log.context }}', '')::text,
  'ai_agent',
  '3',
  'pending'
) RETURNING id;"""

MARK_ANSWERED_SQL = """UPDATE pending_questions
   SET status = 'answered',
       answer = '{{ $json.pending_question_resolution.answer_text }}'::text,
       answered_at = now(),
       answered_by = '{{ $json.senderId }}'::text
 WHERE id = {{ $json.pending_question_resolution.id }}
 RETURNING id, question;"""


def build_nodes(base_pos):
    x, y = base_pos
    return [
        # Fetch pending questions BEFORE Context Builder
        {
            "id": str(uuid.uuid4()),
            "name": "Fetch Pending Questions",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.6,
            "position": [x + 220, y + 220],
            "parameters": {"operation": "executeQuery", "query": FETCH_PQ_SQL, "options": {}},
            "credentials": {"postgres": POSTGRES_CRED},
        },
        # Output-side nodes — gated by IF
        {
            "id": str(uuid.uuid4()),
            "name": "If Has Question To Log",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [x + 600, y + 700],
            "parameters": {
                "options": {},
                "conditions": {
                    "options": {"version": 2, "caseSensitive": True, "typeValidation": "loose"},
                    "combinator": "and",
                    "conditions": [{
                        "id": str(uuid.uuid4()),
                        "operator": {"type": "string", "operation": "notEmpty", "singleValue": True},
                        "leftValue": "={{ String(($json.pending_question_to_log || {}).question_text || '') }}",
                        "rightValue": "",
                    }],
                },
            },
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Insert Pending Question",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.6,
            "position": [x + 800, y + 700],
            "onError": "continueRegularOutput",
            "parameters": {"operation": "executeQuery", "query": INSERT_PQ_SQL, "options": {}},
            "credentials": {"postgres": POSTGRES_CRED},
        },
        {
            "id": str(uuid.uuid4()),
            "name": "If Has Question Resolution",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [x + 600, y + 900],
            "parameters": {
                "options": {},
                "conditions": {
                    "options": {"version": 2, "caseSensitive": True, "typeValidation": "loose"},
                    "combinator": "and",
                    "conditions": [{
                        "id": str(uuid.uuid4()),
                        "operator": {"type": "number", "operation": "gt"},
                        "leftValue": "={{ Number(($json.pending_question_resolution || {}).id || 0) }}",
                        "rightValue": 0,
                    }],
                },
            },
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Mark Pending Question Answered",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.6,
            "position": [x + 800, y + 900],
            "onError": "continueRegularOutput",
            "parameters": {"operation": "executeQuery", "query": MARK_ANSWERED_SQL, "options": {}},
            "credentials": {"postgres": POSTGRES_CRED},
        },
    ]


# ── Context Builder patch ─────────────────────────────────────────────────
CB_FETCH_BLOCK = """// ── pendingContext (deploy 074 — Back-channel Context Injection) ───────"""

CB_FETCH_INJECT = """// ── pendingQuestions (deploy 094 — One question at a time) ────────────
let pendingQuestions = [];
try {
  const items = $('Fetch Pending Questions').all();
  pendingQuestions = items.map(i => i.json).filter(r => r && r.id);
} catch (e) {
  pendingQuestions = [];
}

"""

CB_INPUT_INJECT_ANCHOR = """OPERATOR CONTEXT (use naturally in your reply, do NOT mention Jonathan):"""

CB_QUESTIONS_BLOCK = """
PENDING QUESTIONS LEO HAS ASKED YOU AND IS AWAITING YOUR ANSWER (oldest first):
${pendingQuestions.length === 0 ? '(none)' : pendingQuestions.map(q => `[id:${q.id}] (priority ${q.priority}) asked ${q.asked_at}: "${q.question}"${q.context ? ' — context: ' + q.context : ''}`).join('\\n')}

"""

CB_RETURN_ANCHOR = "    pendingContext,"
CB_RETURN_NEW = "    pendingContext,\n    pendingQuestions,"


def patch_context_builder(node):
    js = node["parameters"]["jsCode"]
    if "pendingQuestions" in js:
        return False
    if CB_FETCH_BLOCK not in js:
        raise ValueError("Context Builder marker not found")
    js = js.replace(CB_FETCH_BLOCK, CB_FETCH_INJECT + CB_FETCH_BLOCK)
    if CB_INPUT_INJECT_ANCHOR not in js:
        raise ValueError("agentInput operator-context marker not found")
    js = js.replace(CB_INPUT_INJECT_ANCHOR, CB_QUESTIONS_BLOCK + CB_INPUT_INJECT_ANCHOR)
    if CB_RETURN_ANCHOR in js and CB_RETURN_NEW not in js:
        js = js.replace(CB_RETURN_ANCHOR, CB_RETURN_NEW)
    node["parameters"]["jsCode"] = js
    return True


# ── AI Agent prompt additions ─────────────────────────────────────────────
PROMPT_SCHEMA_ANCHOR = '"entities_to_register": ['

PROMPT_SCHEMA_ADDITION = '''"pending_question_to_log": {"question_text": "", "topic": "", "context": ""},
  "pending_question_resolution": {"id": 0, "answer_text": ""},
  '''

PROMPT_RULE_ANCHOR = "### Entity capture per turn (added 2026-05-16 — deploy_082)"

PROMPT_RULE_ADDITION = """### ONE question per turn + answer tracking (added 2026-05-16 — deploy_094)

**Cardinal rule**: when you need to ASK a clarifying question, ask ONE question only — the highest-priority one. Never stack 2-3 questions in a single reply. Wait for the answer, capture it, then ask the next.

End every question with the explicit reply marker:
```
👉 Reply with your answer.
```

When you ask, ALSO emit `pending_question_to_log` so the system tracks it:
```json
"pending_question_to_log": {
  "question_text": "<verbatim question you asked the user>",
  "topic": "<short topic, e.g. 'naga-meeting-date' or 'guardianship-counsel'>",
  "context": "<one-line why you're asking — for your own future reference>"
}
```

**Answering loop**: When you process a message, check `pendingQuestions` in your input. If the sender's current message looks like an answer to any open question (semantic match — be liberal):

1. Pick the OLDEST matching question.
2. Emit `pending_question_resolution`:
   ```json
   "pending_question_resolution": {
     "id": <pendingQuestions[*].id>,
     "answer_text": "<verbatim or condensed answer>"
   }
   ```
3. Use the answer to inform your response and capture into chat_note_to_save with topic='legal_strategy' or 'communications'.
4. If the answer ALSO unblocks an action_item, mark it via your reply.

**Multiple open questions**: only resolve the ONE the current message answers. The others stay open. If the sender ignores prior questions and changes topic, do NOT re-prompt them in the same turn — your job is to capture what they DID say. Asking again can wait for an opportunity.

**Source-of-questions**:
- Asked by Leo during conversation -> `asked_by = 'leo'`
- Asked by Jonathan as a relay (Rule C) -> use pending_inquiries instead, not pending_questions
- Asked by educate_leo offline -> `asked_by = 'educate_leo'`

If you emit a question that exceeds 200 characters, you're asking too much — split it or rephrase.

"""


def patch_prompt(node):
    p = node["parameters"]["options"]["systemMessage"]
    changed = False
    if "pending_question_to_log" not in p:
        if PROMPT_SCHEMA_ANCHOR not in p:
            raise ValueError("Schema anchor entities_to_register not found")
        p = p.replace(PROMPT_SCHEMA_ANCHOR, PROMPT_SCHEMA_ADDITION + PROMPT_SCHEMA_ANCHOR)
        changed = True
    if "ONE question per turn + answer tracking" not in p:
        if PROMPT_RULE_ANCHOR not in p:
            raise ValueError("Rule anchor not found")
        p = p.replace(PROMPT_RULE_ANCHOR, PROMPT_RULE_ADDITION + "\n" + PROMPT_RULE_ANCHOR)
        changed = True
    node["parameters"]["options"]["systemMessage"] = p
    return changed


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
    snap = f"/root/landtek/snapshots/leos_workflow_pre_094_{args.target}_{ts}.json"
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes, "connections": conns}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    pa = next((n for n in nodes if n["name"] == "Parse Agent1"), None)
    base_pos = pa.get("position", [400, 0])

    existing = {n["name"] for n in nodes}
    new_names = ["Fetch Pending Questions", "If Has Question To Log", "Insert Pending Question",
                 "If Has Question Resolution", "Mark Pending Question Answered"]
    to_add = [n for n in build_nodes(base_pos) if n["name"] not in existing]
    nodes.extend(to_add)
    print(f"  ✓ added {len(to_add)} nodes")

    # Wire input side: Fetch Pending Context -> Fetch Pending Questions -> Context Builder
    if "Fetch Pending Context" in conns:
        fpc_main = conns["Fetch Pending Context"].get("main", [[]])
        # Redirect Fetch Pending Context downstream to Fetch Pending Questions
        for branch in fpc_main:
            for t in branch:
                if t.get("node") == "Context Builder":
                    t["node"] = "Fetch Pending Questions"
        conns["Fetch Pending Context"] = {"main": fpc_main}
    conns["Fetch Pending Questions"] = {"main": [[{"node": "Context Builder", "type": "main", "index": 0}]]}
    print("  ✓ wired: Fetch Pending Context -> Fetch Pending Questions -> Context Builder")

    # Wire output side: Parse Agent1 -> If Has Question To Log / If Has Question Resolution
    pa_main = conns.get("Parse Agent1", {}).get("main", [[]])
    for new_if in ["If Has Question To Log", "If Has Question Resolution"]:
        if not any(t.get("node") == new_if for t in pa_main[0]):
            pa_main[0].append({"node": new_if, "type": "main", "index": 0})
    conns["Parse Agent1"] = {"main": pa_main}
    conns["If Has Question To Log"] = {"main": [
        [{"node": "Insert Pending Question", "type": "main", "index": 0}],
        [],
    ]}
    conns["If Has Question Resolution"] = {"main": [
        [{"node": "Mark Pending Question Answered", "type": "main", "index": 0}],
        [],
    ]}
    print("  ✓ wired output IFs -> Insert + Mark Answered")

    # Patch Context Builder
    cb = next((n for n in nodes if n["name"] == "Context Builder"), None)
    if cb and patch_context_builder(cb):
        print("  ✓ Context Builder: pendingQuestions injected")

    # Patch AI Agent prompt
    aia = next((n for n in nodes if n["name"] == "AI Agent"), None)
    if aia and patch_prompt(aia):
        print("  ✓ AI Agent prompt: ONE question + reply marker + answer-tracking schema")

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
