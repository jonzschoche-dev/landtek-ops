#!/usr/bin/env python3
"""Deploy 268 - block 'checking now' / 'let me look' replies without tool calls.

POSTMORTEM trigger (May 25 4:10 AM): Jonathan asked "any documentation
about sustainable development on Inocalla property?" Leo's actual reply:
"Checking our document index for anything related to sustainable
development or community plans on the Inocalla property now."

He NEVER called query_documents or cross_reference. The DB had at least 5
direct-hit docs (doc#490 Maharlika eco-wellness, doc#485 Green World MOU,
doc#481 cultural exchange, doc#479 Paracale Gold, doc#478 MGB). Leo
promised to check and never did.

This deploy adds a HARD prompt rule:
  - If the user message asks for documents/papers/records/evidence and Leo
    emits a placeholder like 'checking now' / 'let me look' / 'I'll
    pull up' WITHOUT having called a tool in this turn, that is
    FORBIDDEN. Leo must call the tool BEFORE replying.

Also adds sync_workflow_history at the end so the change actually takes
effect (workflow_entity changes don't reach n8n's executing version).

Idempotent. Audited via app.actor='jonathan_deploy_268'.
"""
import json
import subprocess
import sys

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
WORKFLOW_ID = "vSDQv1vfn6627bnA"

NEW_RULE = """

# NO EMPTY PROMISES RULE (deploy_268 - 2026-05-25)

If the user's message asks you to find, check, retrieve, look up, pull up,
or verify documents/records/papers/evidence:

  1. You MUST call the appropriate tool (query_documents, cross_reference,
     get_party_history, Search Documents Tool, get_thread) BEFORE emitting
     telegram_reply_to_client.

  2. Replies like 'Checking now...', 'Let me look that up', "I'll pull up
     the docs", 'One moment while I search' WITHOUT a prior tool call in
     the SAME turn are FORBIDDEN. Either:
       (a) you have already called the tool and have results -> give the
           results in your reply, or
       (b) you have not called the tool -> call it now, then reply.

  3. Never end a reply with a forward-looking commitment ('I'll get back
     to you', 'will follow up') unless an action_item is emitted that
     captures the followup. A promise without an action_item is a leak.

  4. The single exception: if the user's question is genuinely ambiguous
     and you need clarification, set needs_clarification=true and ask the
     clarification_question. That's not an empty promise; it's a
     legitimate request.

This rule overrides any prior 'be brief / acknowledge quickly' guidance.
A complete-but-late reply beats a quick-but-empty one.

"""


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'jonathan_deploy_268'")

    print("Deploy 268 - block empty 'checking now' replies")
    print("=" * 60)

    cur.execute("SELECT nodes FROM workflow_entity WHERE id = %s", (WORKFLOW_ID,))
    row = cur.fetchone()
    nodes = row["nodes"] if isinstance(row["nodes"], list) else json.loads(row["nodes"])

    patched = False
    for n in nodes:
        if n.get("name") == "AI Agent" and n.get("type") == "@n8n/n8n-nodes-langchain.agent":
            opts = n.setdefault("parameters", {}).setdefault("options", {})
            old = opts.get("systemMessage", "")
            if "NO EMPTY PROMISES RULE (deploy_268" in old:
                print("  rule already present (no-op)")
                patched = True
                break
            # Insert just before STANDING BRIEF (so it precedes briefing rules)
            anchor = "# STANDING BRIEF"
            if anchor in old:
                new = old.replace(anchor, NEW_RULE.strip() + "\n\n" + anchor, 1)
            else:
                new = old.rstrip() + "\n" + NEW_RULE
            opts["systemMessage"] = new
            print(f"  AI Agent prompt: {len(old)} -> {len(new)} chars")
            patched = True

    if not patched:
        print("  AI Agent not found")
        sys.exit(1)

    cur.execute(
        "UPDATE workflow_entity SET nodes = %s::json, \"updatedAt\" = now() WHERE id = %s",
        (json.dumps(nodes), WORKFLOW_ID),
    )
    conn.commit()
    cur.close()
    conn.close()
    print("  workflow_entity updated")

    print("\n  syncing workflow_history (so the change actually takes effect)...")
    r = subprocess.run(["python3", "/root/landtek/scripts/sync_workflow_history.py", WORKFLOW_ID],
                       capture_output=True, text=True)
    print("  " + r.stdout.strip())
    if r.returncode != 0:
        print("  sync FAILED:", r.stderr)
        sys.exit(1)

    print("\n  smoke test...")
    r = subprocess.run(["python3", "/root/landtek/scripts/post_deploy_smoke.py"],
                       capture_output=True, text=True)
    print("  " + r.stdout.strip().replace("\n", "\n  "))


if __name__ == "__main__":
    main()
