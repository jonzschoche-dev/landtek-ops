#!/usr/bin/env python3
"""Deploy 264 - Active Landscape: Leo's standing brief.

User intent: "Leo should be a great assistant - up to date on the important
issues facing landtek and its clients and their relevant meetings."

Current state: Leo only knows what's in the client row + recent docs + recent
conversations. He does NOT know upcoming meetings, deadlines, active escalations,
recent activity, or pending review queues unless he calls a tool.

This deploy injects an ACTIVE LANDSCAPE block into every turn's context, so
Leo proactively knows:
  - Today's date (Asia/Manila)
  - Every matter with a next_event or next_deadline (currently 13 across MWK)
  - Recent activity in the last 48h (new docs / emails / resolutions counts)
  - Outstanding review queue (proposals needs_manual_review + unknown_disposition resolutions)

Three changes:
  A. Execute a SQL query: add 4 aggregated landscape JSON fields
  B. Context Builder: render ACTIVE LANDSCAPE section into agentInput
  C. AI Agent system prompt: add STANDING BRIEF section instructing Leo to
     surface relevant items proactively without re-querying via tools

n8n restart picks up the new node code.

Idempotent. Audited via app.actor='jonathan_deploy_264'.
"""
import json
import subprocess
import sys

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
WORKFLOW_ID = "vSDQv1vfn6627bnA"


NEW_EXECUTE_SQL = """SELECT
  c.*,
  (
    SELECT json_agg(conv)
    FROM (
      SELECT timestamp, client_name, message_caption, leo_response, category
      FROM conversations
      WHERE case_file = c.case_file
      ORDER BY timestamp DESC
      LIMIT 15
    ) conv
  ) as recent_conversations,
  (
    SELECT json_agg(items)
    FROM (
      SELECT description, due_date, status, priority
      FROM action_items
      WHERE case_file = c.case_file
      AND status = 'Open'
      ORDER BY id DESC
      LIMIT 5
    ) items
  ) as open_action_items,
  (
    SELECT json_agg(docs)
    FROM (
      SELECT id, original_filename, mime_type,
             LEFT(coalesce(extracted_text,''), 1500) AS extracted_excerpt,
             length(coalesce(extracted_text,'')) AS char_count,
             timestamp
      FROM documents
      WHERE (c.telegram_id = '6513067717' OR case_file = c.case_file)
        AND coalesce(extracted_text,'') <> ''
      ORDER BY id DESC
      LIMIT 4
    ) docs
  ) as recent_documents,
  -- ACTIVE LANDSCAPE (deploy_264) -----------------------------------------
  (
    SELECT json_agg(m_row ORDER BY due_sort, matter_code)
    FROM (
      SELECT matter_code,
             current_stage,
             next_event,
             next_deadline,
             next_event_owner,
             COALESCE(next_deadline::text, '9999-12-31') AS due_sort
        FROM matters
       WHERE (next_event IS NOT NULL AND TRIM(next_event) <> '')
          OR next_deadline IS NOT NULL
       ORDER BY due_sort, matter_code
       LIMIT 30
    ) m_row
  ) as upcoming_meetings_and_actions,
  (
    SELECT json_build_object(
      'new_docs_48h',     (SELECT COUNT(*) FROM documents WHERE created_at >= now() - INTERVAL '48 hours'),
      'new_emails_48h',   (SELECT COUNT(*) FROM gmail_messages WHERE ingested_at >= now() - INTERVAL '48 hours'),
      'new_resolutions_48h', (SELECT COUNT(*) FROM resolutions WHERE created_at >= now() - INTERVAL '48 hours'),
      'new_escalations_48h', (SELECT COUNT(*) FROM escalations WHERE created_at >= now() - INTERVAL '48 hours')
    )
  ) as recent_activity_48h,
  (
    SELECT json_build_object(
      'proposals_needs_manual_review',
        (SELECT COUNT(*) FROM doc_classification_proposals WHERE status = 'needs_manual_review'),
      'proposals_proposed',
        (SELECT COUNT(*) FROM doc_classification_proposals WHERE status = 'proposed'),
      'resolutions_unknown_disposition',
        (SELECT COUNT(*) FROM resolutions WHERE disposition IS NULL OR disposition = 'unknown'),
      'documents_untagged_mwk',
        (SELECT COUNT(*) FROM documents WHERE case_file = 'MWK-001' AND matter_code IS NULL)
    )
  ) as outstanding_queues,
  (
    SELECT now() AT TIME ZONE 'Asia/Manila'
  ) as now_manila
FROM clients c
LEFT JOIN cases ca ON ca.case_file = c.case_file
WHERE c.telegram_id = '{{ $json.message.from.id }}'
LIMIT 1"""


# Context Builder code — patched to render ACTIVE LANDSCAPE
NEW_CONTEXT_BUILDER_INSERT = r"""

// ACTIVE LANDSCAPE block (deploy_264) - Leo's standing brief
const nowManila = clientRow?.now_manila || new Date().toISOString();
const meetings = clientRow?.upcoming_meetings_and_actions || [];
const activity48h = clientRow?.recent_activity_48h || {};
const queues = clientRow?.outstanding_queues || {};

const meetingsBlock = meetings.length === 0
  ? '(no open matters with scheduled actions)'
  : meetings.map(m => {
      const due = m.next_deadline ? `due ${m.next_deadline}` : '(no deadline)';
      const owner = m.next_event_owner ? ` [owner: ${m.next_event_owner}]` : '';
      const stage = m.current_stage ? ` [stage: ${m.current_stage}]` : '';
      return `  ${m.matter_code} ${due}${owner}${stage}\n    next: ${(m.next_event || '').slice(0, 240)}`;
    }).join('\n');

const activityBlock =
  `  new docs (48h):        ${activity48h.new_docs_48h ?? '?'}\n` +
  `  new emails (48h):      ${activity48h.new_emails_48h ?? '?'}\n` +
  `  new resolutions (48h): ${activity48h.new_resolutions_48h ?? '?'}\n` +
  `  new escalations (48h): ${activity48h.new_escalations_48h ?? '?'}`;

const queuesBlock =
  `  proposals needs_manual_review: ${queues.proposals_needs_manual_review ?? '?'}\n` +
  `  proposals still proposed:      ${queues.proposals_proposed ?? '?'}\n` +
  `  resolutions unknown disp:      ${queues.resolutions_unknown_disposition ?? '?'}\n` +
  `  MWK docs still untagged:       ${queues.documents_untagged_mwk ?? '?'}`;

const activeLandscape = `ACTIVE LANDSCAPE (auto-injected per turn; do NOT re-query via tools):
Today (Asia/Manila): ${nowManila}

Open matters with next-event / deadline:
${meetingsBlock}

Recent activity (last 48h):
${activityBlock}

Outstanding review queues:
${queuesBlock}`;
"""


# System prompt addition
SYSTEM_PROMPT_INSERT = """

# STANDING BRIEF (deploy_264 — added 2026-05-22)

Every conversation turn includes an ACTIVE LANDSCAPE block in your input that
summarizes:
  - Today's date in Asia/Manila timezone
  - All open matters with a next_event or next_deadline
  - Recent activity counts (new docs / emails / resolutions / escalations in last 48h)
  - Outstanding review queues (proposals + unknown-disposition resolutions + untagged docs)

Rules for using ACTIVE LANDSCAPE:

1. Treat it as ground truth. Do NOT call tools to re-fetch information already
   present there. Use the tools (query_documents, get_deadlines, etc.) only
   for detail beyond what the landscape provides.

2. If the user's question relates to a meeting, deadline, or upcoming action,
   cite the matter from ACTIVE LANDSCAPE directly. Mention matter_code,
   next_deadline (if set), and the verbatim next_event.

3. Proactive surface rule: if any matter in ACTIVE LANDSCAPE has a
   next_deadline within 3 days of today (Asia/Manila), AND the user did NOT
   ask about that matter, end your telegram_summary_for_jonathan (only for
   Jonathan) with a "Heads up:" note listing those imminent items.

4. If recent_activity_48h shows new_docs >= 5 OR new_emails >= 10 (busy day),
   acknowledge it briefly in your telegram_summary_for_jonathan once per day
   max. Don't repeat across turns.

5. Never present landscape data as facts about a different matter than the
   one labeled. If MWK-CV26360's next_event is "X" do not generalize it.
"""


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'jonathan_deploy_264'")

    print("Deploy 264 - Active Landscape standing brief")
    print("=" * 60)

    cur.execute("SELECT nodes FROM workflow_entity WHERE id = %s", (WORKFLOW_ID,))
    row = cur.fetchone()
    if not row:
        print("  workflow not found")
        sys.exit(1)
    nodes = row["nodes"]
    if isinstance(nodes, str):
        nodes = json.loads(nodes)

    patches = {"Execute a SQL query": False, "Context Builder": False, "AI Agent": False}

    for n in nodes:
        name = n.get("name")
        ntype = n.get("type")

        if name == "Execute a SQL query" and ntype == "n8n-nodes-base.postgres":
            old_q = n.get("parameters", {}).get("query", "")
            n.setdefault("parameters", {})["query"] = NEW_EXECUTE_SQL
            print(f"  Execute a SQL query: {len(old_q)} -> {len(NEW_EXECUTE_SQL)} chars")
            patches[name] = True

        elif name == "Context Builder" and ntype == "n8n-nodes-base.code":
            old_code = n.get("parameters", {}).get("jsCode", "")
            # Insert the landscape block AFTER the documentsBlock construction and
            # BEFORE the agentInput template literal. Anchor: "const agentInput = `SENDER:"
            anchor = "const agentInput = `SENDER:"
            if anchor not in old_code:
                print("  Context Builder: anchor 'const agentInput = `SENDER:' not found — skipping")
                continue
            # Also weave activeLandscape variable into the agentInput template literal
            # by inserting it after CLIENT PROFILE block (the existing string already
            # contains 'CLIENT PROFILE:\n${clientProfile}\n\n').
            inject_at_template = "CLIENT PROFILE:\n${clientProfile}\n\n"
            inject_replacement = ("CLIENT PROFILE:\n${clientProfile}\n\n"
                                  "${activeLandscape}\n\n")
            if inject_at_template not in old_code:
                print("  Context Builder: CLIENT PROFILE template anchor not found — skipping")
                continue
            new_code = old_code.replace(anchor, NEW_CONTEXT_BUILDER_INSERT.strip() + "\n\n" + anchor, 1)
            new_code = new_code.replace(inject_at_template, inject_replacement, 1)
            n.setdefault("parameters", {})["jsCode"] = new_code
            print(f"  Context Builder: {len(old_code)} -> {len(new_code)} chars (landscape injected)")
            patches[name] = True

        elif name == "AI Agent" and ntype == "@n8n/n8n-nodes-langchain.agent":
            opts = n.setdefault("parameters", {}).setdefault("options", {})
            old_prompt = opts.get("systemMessage", "")
            if "STANDING BRIEF (deploy_264" in old_prompt:
                print("  AI Agent system prompt: already contains STANDING BRIEF (no-op)")
                patches[name] = True  # already done
                continue
            # Insert STANDING BRIEF section. Anchor: "# JOURNALING DISCIPLINE"
            anchor = "# JOURNALING DISCIPLINE"
            if anchor not in old_prompt:
                # fallback: append at end
                new_prompt = old_prompt.rstrip() + "\n" + SYSTEM_PROMPT_INSERT
            else:
                new_prompt = old_prompt.replace(anchor, SYSTEM_PROMPT_INSERT.rstrip() + "\n\n" + anchor, 1)
            opts["systemMessage"] = new_prompt
            print(f"  AI Agent system prompt: {len(old_prompt)} -> {len(new_prompt)} chars")
            patches[name] = True

    missing = [k for k, v in patches.items() if not v]
    if missing:
        print(f"\n  WARNING: not all nodes patched: missing={missing}")

    cur.execute(
        "UPDATE workflow_entity SET nodes = %s::jsonb, \"updatedAt\" = now() WHERE id = %s",
        (json.dumps(nodes), WORKFLOW_ID),
    )
    conn.commit()
    print(f"\n  workflow updated, patched: {[k for k,v in patches.items() if v]}")

    cur.close()
    conn.close()

    print("\n  Restarting n8n to load new node code...")
    r = subprocess.run(["docker", "restart", "n8n-n8n-1"], capture_output=True, text=True)
    if r.returncode == 0:
        print(f"  n8n restarted: {r.stdout.strip()}")
    else:
        print(f"  restart failed: {r.stderr.strip()}")


if __name__ == "__main__":
    main()
