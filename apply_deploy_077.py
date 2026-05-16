#!/usr/bin/env python3
"""Deploy 077 — Improve Leo's conversation handling (memory + Rule D + Rule B).

Incident transcript (2026-05-16 08:36):
  Leo: "do you have plans to come to Naga anytime soon?"
  Don Qi: "I'll be with attorney Botor"
  Leo: "Will you be heading to Naga with Attorney Botor soon? Do you have a date in mind?"
  Don Qi: "Tentative meeting by the end of next week"
  Leo: "Is this the meeting with Attorney Botor in Naga? And do you have a preferred day or time?"

Three failures revealed:
  (1) Leo asked 3 follow-up questions in a row, not converging — feels like
      interrogation. Should have accepted "tentative end of next week" as
      sufficient and stopped.
  (2) Leo never set pending_inquiry_resolution despite Don Qi giving a clear
      answer to the open inquiry. Reason: Context Builder loads pendingInquiries
      into a variable but NEVER injects it into the agentInput string. Rule D
      has been dead since deploy_038 added it.
  (3) Leo forgot prior context (yesterday's conversations 91/126/129 establish
      Atty Botor = guardianship lawyer, meeting was about citizenship/estate).
      Cause: recent_conversations LIMIT is 4 — too narrow.

Fixes:
  A. Context Builder JS: inject 'PENDING INQUIRIES (you may be receiving an answer)'
     block into agentInput.
  B. Execute a SQL query: bump recent_conversations LIMIT 4 -> 15.
  C. AI Agent system prompt: add a 'Conversation efficiency' subsection to Rule B:
       - max 1 follow-up question per turn
       - accept tentative/approximate answers as sufficient
       - if pendingInquiries shows a match, RESOLVE first (Rule D), don't pile follow-ups
     Also strengthen Rule D's matching guidance.
  D. DB cleanup: mark the 5 stale 'when in Naga' inquiries as superseded by
     Don Qi's actual answer (already captured in chat_note id 54).

Risk: prompt + Code node changes. Validated on staging before prod.
"""
import json
import os
import sys
import argparse
import time

sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

WF_NAME = "Leos Workflow"

# ── (A) Context Builder patch: insert pendingInquiries block into agentInput ──
# The current template ends with the documents block. We append a new section.
# The Context Builder also gets a small change in how it composes pendingInquiriesBlock.
CB_AGENT_INPUT_OLD = """RECENT DOCUMENTS UPLOADED BY THIS CLIENT (last 4 with extracted content):
${documentsBlock}"""

CB_AGENT_INPUT_NEW = """RECENT DOCUMENTS UPLOADED BY THIS CLIENT (last 4 with extracted content):
${documentsBlock}

PENDING INQUIRIES (Jonathan asked you to relay these to this client; if their current message answers ANY of them, you MUST set pending_inquiry_resolution per Rule D):
${pendingInquiries.length === 0 ? '(none)' : pendingInquiries.map(p => `[id:${p.id}] asked ${p.asked_at}: "${p.question_text}" — already relayed as: "${p.relayed_message}"`).join('\\n')}"""

# ── (B) SQL query change: LIMIT 4 -> LIMIT 15 in recent_conversations ────
SQL_OLD = "      ORDER BY timestamp DESC\n      LIMIT 4"
SQL_NEW = "      ORDER BY timestamp DESC\n      LIMIT 15"

# ── (C) AI Agent system prompt additions ──────────────────────────────────
# Insert after Rule B's existing required actions list. Find the marker:
RULE_B_MARKER = "Never give only a basic acknowledgment like \"File received.\" Always investigate to bring full clarity to the relationship, the client's needs, and organizational necessities — **within the active client's scope only**."

RULE_B_ADDITION = """

### Conversation efficiency (added 2026-05-16 — Rule B subsection)

**Max ONE follow-up question per turn.** If a client gives you any actionable answer — even tentative or approximate ("end of next week", "tentative", "I think Tuesday", "with my lawyer") — accept it as sufficient and STOP asking for more precision. Capture what they said via chat_note_to_save + calendar_event_to_save (if a date/event is implied), then close the loop.

Do NOT chain follow-ups like:
- "Will you be heading to Naga soon?"
- "Do you have a date in mind?"
- "Is this the meeting we discussed?"
- "Do you have a preferred day or time?"
This pattern feels like an interrogation. Pick ONE most useful clarifying question per turn, or none if the answer is already actionable.

**If `pendingContext.pendingInquiries[]` shows a question matching the topic of the client's message, RESOLVE the inquiry FIRST (Rule D) before any follow-up.** The inquiry resolution path is the priority — once Jonathan knows the answer, you can probe for detail later if needed."""

# Strengthen Rule D's matching guidance.
RULE_D_OLD = "2. **Judge whether the current client message is the answer** — semantically, not just by keyword. Score your confidence 0..1."

RULE_D_NEW = """2. **Judge whether the current client message is the answer** — semantically, not just by keyword. Score your confidence 0..1. Be LIBERAL in matching: a tentative or partial answer still counts. If the inquiry asked "when will X happen" and the client says "end of next week" or "tentative Tuesday" or "around the 15th", that's confidence ~0.85+ — RESOLVE it. Only return < 0.7 if the client message is unrelated to the inquiry topic. The cost of a false-positive resolution (Jonathan gets a relayed answer that's incomplete) is far less than a false-negative (Jonathan never learns the client answered)."""


def patch_context_builder(node):
    js = node["parameters"]["jsCode"]
    if CB_AGENT_INPUT_OLD not in js:
        # Maybe already patched
        if "PENDING INQUIRIES (Jonathan asked you to relay" in js:
            return False
        raise ValueError("Context Builder agentInput template not found in expected form")
    js = js.replace(CB_AGENT_INPUT_OLD, CB_AGENT_INPUT_NEW)
    node["parameters"]["jsCode"] = js
    return True


def patch_sql_query(node):
    q = node["parameters"]["query"]
    if SQL_OLD not in q:
        if "LIMIT 15" in q:
            return False
        raise ValueError("Execute a SQL query: LIMIT 4 not found in expected form")
    q = q.replace(SQL_OLD, SQL_NEW)
    node["parameters"]["query"] = q
    return True


def patch_ai_agent(node):
    prompt = node["parameters"]["options"]["systemMessage"]
    changed = False
    if "Conversation efficiency (added 2026-05-16 — Rule B subsection)" not in prompt:
        if RULE_B_MARKER not in prompt:
            raise ValueError("Rule B marker not found in AI Agent prompt")
        prompt = prompt.replace(RULE_B_MARKER, RULE_B_MARKER + RULE_B_ADDITION)
        changed = True
    if RULE_D_OLD in prompt:
        prompt = prompt.replace(RULE_D_OLD, RULE_D_NEW)
        changed = True
    elif "Be LIBERAL in matching" not in prompt:
        # Rule D marker missing — manual review
        raise ValueError("Rule D marker not found in AI Agent prompt")
    node["parameters"]["options"]["systemMessage"] = prompt
    return changed


def cleanup_stale_inquiries(dsn):
    """Mark the 5 'when in Naga' stale inquiries as resolved via Don Qi's actual answer."""
    conn = psycopg2.connect(**dsn); conn.autocommit = True
    cur = conn.cursor()
    # Find the most recent chat_note that captures Don Qi's actual answer
    cur.execute("""
        SELECT id, content FROM chat_notes
         WHERE content ILIKE '%tentative meeting%' AND content ILIKE '%next week%'
         ORDER BY id DESC LIMIT 1;
    """)
    row = cur.fetchone()
    if row:
        chat_note_id, content = row
        # Note: pending_inquiries.status enum is {open, answered, closed, expired}
        # — not 'resolved'. Use 'answered' to match the schema's CHECK constraint.
        cur.execute("""
            UPDATE pending_inquiries
               SET status = 'answered',
                   response_text = %s,
                   responded_at = now(),
                   ai_match_confidence = 0.85,
                   closed_reason = 'backfilled from chat_note '||%s::text||' via deploy_077'
             WHERE target_chat_id = '8575986732'
               AND question_text ILIKE '%%when he will be in Naga%%'
               AND status = 'open'
             RETURNING id;
        """, (content[:500], chat_note_id))
        ids = [r[0] for r in cur.fetchall()]
        print(f"  ✓ marked stale inquiries as resolved: {ids}")
    else:
        print(f"  ⚠ no chat_note found matching 'tentative meeting end of next week' — leaving inquiries open")
    cur.close(); conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["staging", "prod"], required=True)
    args = parser.parse_args()

    if args.target == "staging":
        DSN = dict(host="127.0.0.1", port=5433, dbname="n8n", user="n8n", password="n8npassword")
    else:
        DSN = dict(host="172.18.0.3", port=5432, dbname="n8n", user="n8n", password="n8npassword")
    print(f"  target={args.target}  dsn={DSN['host']}:{DSN['port']}")

    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name=%s", (WF_NAME,))
    wf_id, nodes, conns = cur.fetchone()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_077_{args.target}_{ts}.json"
    os.makedirs("/root/landtek/snapshots", exist_ok=True)
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes, "connections": conns}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    cb = next((n for n in nodes if n["name"] == "Context Builder"), None)
    if cb and patch_context_builder(cb):
        print("  ✓ Context Builder: pendingInquiries block injected into agentInput")
    else:
        print("  ⚠ Context Builder: already patched or marker missing")

    sql = next((n for n in nodes if n["name"] == "Execute a SQL query"), None)
    if sql and patch_sql_query(sql):
        print("  ✓ Execute a SQL query: recent_conversations LIMIT 4 -> 15")
    else:
        print("  ⚠ Execute a SQL query: already patched or marker missing")

    aia = next((n for n in nodes if n["name"] == "AI Agent"), None)
    if aia and patch_ai_agent(aia):
        print("  ✓ AI Agent prompt: Rule B (efficiency) + Rule D (liberal matching) patched")
    else:
        print("  ⚠ AI Agent prompt: already patched")

    cur.close(); conn.close()

    if args.target == "staging":
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute(
            'UPDATE workflow_entity SET nodes=%s::jsonb, "updatedAt"=now() WHERE id=%s',
            (json.dumps(nodes), wf_id))
        cur.execute("""UPDATE workflow_history SET nodes=%s::json
                         WHERE "workflowId"=%s
                           AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""",
                    (json.dumps(nodes), wf_id, wf_id))
        cur.execute('UPDATE workflow_entity SET active=false, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); time.sleep(2)
        cur.execute('UPDATE workflow_entity SET active=true, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()
        print("  ✓ staging workflow updated + reactivated")
    else:
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes)

    # Cleanup (D) — only on prod (staging gets a fresh restore each bring-up)
    if args.target == "prod":
        print("  → cleanup stale inquiries (Don Qi 'when in Naga' x 5)")
        cleanup_stale_inquiries(DSN)


if __name__ == "__main__":
    main()
