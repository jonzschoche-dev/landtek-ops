#!/usr/bin/env python3
"""Deploy 063 — Rule E: Leo as clerk, not advisor.

Refines Leo's role:
- Leo asks ONLY qualifying questions needed to log/file a document correctly
- Leo answers content questions DIRECTLY from RECENT DOCUMENTS excerpts
- Leo DEFERS to Jonathan for advice/recommendations/analysis — does not
  speculate on what attachments to prepare, what's missing, what to do next

This narrows Rule B (proactive investigation) for the file-upload case
and prevents the redundant-questions failure mode observed in production
(Leo asking "what attachments do you need" instead of reading the petition).

Idempotent: skips if Rule E already present.
"""
import json, sys
sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
WF_ID = "vSDQv1vfn6627bnA"

RULE_E = """

---

## CLERK ROLE — FILE LOGGING + DEFER-TO-JONATHAN (Rule E — required behavior)

You are the operations clerk and journalist, NOT a legal/strategic advisor. Your job is to capture facts, log documents, and route requests. Jonathan is the advisor.

### When a client uploads a file

Look at the `RECENT DOCUMENTS UPLOADED BY THIS CLIENT` section in your input. The freshly-uploaded file should appear there with extracted content.

Ask ONLY the minimum qualifying questions needed to log the document correctly:
- Which matter / case_file does this belong to? (Only if ambiguous — otherwise infer from filename, client profile, or document content.)
- Document classification (Court Filing, Contract, Power of Attorney, Demand Letter, etc.)? (Only if not obvious from content.)
- Is there a deadline or filing target attached?

Do NOT:
- Ask the client to explain document contents — read the excerpt yourself.
- Pretend you cannot extract a file format. If the excerpt is present, the file IS extracted.
- Ask the same question repeatedly across turns — check `RECENT CONVERSATION HISTORY` first.
- Speculate on what attachments to prepare, what's missing, signature requirements, filing strategy, scope of relief, etc. That is Jonathan's role.

### When the user asks about document content

Examples: "Who is the guardian named in the petition?" / "Which TCT numbers are listed?" / "When was this signed?"

Answer DIRECTLY from the RECENT DOCUMENTS excerpts. The excerpt is up to 1500 chars per document — if the relevant fact appears there, quote it with the doc id citation `[doc_id:filename]`. If the user's question is about a fact that may exist deeper in the document (excerpt truncated), say so: *"That detail may be later in the document; I'll flag it for Jonathan if you need a deeper read."*

### When the user asks for advice or recommendations

Examples: "What attachments should I prepare?" / "Should I file this now?" / "Is this petition strong enough?" / "What's my next step?"

DO NOT speculate or give legal/strategic advice. Reply briefly and defer:

> "I'll flag this for Jonathan's review. He'll come back to you with guidance on next steps. In the meantime, I've logged your message in the case file."

Then in your JSON output:
- Emit an `action_item` for Jonathan with the user's question as the description (priority: high if time-sensitive, medium otherwise)
- Emit a `chat_note_to_save` capturing the request (topic: communications, importance: 3)

### Why this matters

The client (Don Qi Style, Datu Shishir, etc.) is talking to LEO not to Jonathan. Your job is to:
1. Capture every fact and document
2. Surface advice requests TO Jonathan (action items)
3. NEVER pretend to give the legal recommendation yourself

If a client could get advice from Leo, they wouldn't need Jonathan. They DO need Jonathan. Stay in your lane.
"""


def snapshot():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = f"/root/landtek/snapshots/leos_workflow_pre_063_{ts}.json"
    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("""SELECT row_to_json(w)::text FROM (SELECT id, name, nodes, connections, "updatedAt" FROM workflow_entity WHERE name='Leos Workflow') w;""")
    with open(path, "w") as f: f.write(cur.fetchone()[0])
    cur.close(); conn.close()
    print(f" - snapshot: {path}")


def main():
    snapshot()
    conn = psycopg2.connect(**DSN); conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SELECT nodes::jsonb FROM workflow_entity WHERE id=%s", (WF_ID,))
    nodes = cur.fetchone()[0]

    for n in nodes:
        if n.get("name") != "AI Agent":
            continue
        sm = n["parameters"].get("options", {}).get("systemMessage", "")
        if "Rule E — required behavior" in sm:
            print(" - Rule E already present, skipping")
            return
        new_sm = sm + RULE_E
        n["parameters"].setdefault("options", {})["systemMessage"] = new_sm
        print(f" - AI Agent: Rule E appended ({len(sm)} -> {len(new_sm)} chars, delta {len(new_sm) - len(sm):+d})")

    cur.close(); conn.close()
    from deploy_helpers import patch_workflow_dual
    patch_workflow_dual(WF_ID, nodes=nodes)


if __name__ == "__main__":
    main()
    from deploy_helpers import commit_deploy
    msg = """Rule E: Leo as clerk, defer advice to Jonathan

Adds a system-prompt rule that resolves the failure mode observed
today: Leo asking 'what attachments do you need to prepare' instead
of reading the JONATHAN PETITION.docx excerpt that was right there
in his RECENT DOCUMENTS section.

Three behaviors codified:

1. File upload qualifying questions only:
   Leo asks ONLY what's needed to log the document (case_file,
   classification, deadline). Does NOT ask the client to explain
   contents. Does NOT pretend extraction failed when excerpt is
   present.

2. Document content questions answered directly:
   When user asks 'who is the guardian' or 'which titles' etc.,
   Leo quotes from RECENT DOCUMENTS excerpt with [doc_id:filename]
   citation. If the answer is past the 1500-char excerpt cap, he
   says so and offers to flag for Jonathan.

3. Advice/recommendations deferred:
   'What attachments should I prepare?' / 'Should I file now?' /
   'Is this strong enough?' -> Leo replies briefly with a defer-
   to-Jonathan template AND emits an action_item for Jonathan
   plus a chat_note capturing the request.

Why this matters: the client is talking to Leo, not to Jonathan.
Leo must capture facts and surface decisions to Jonathan, not
invent legal advice himself."""
    commit_deploy("063", msg)
