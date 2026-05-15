#!/usr/bin/env python3
"""Deploy 033 — rewrite Rule B in AI Agent systemMessage.

Removes the deploy-032 PROACTIVE INVESTIGATION block (which conflated Datu Shishir
with Don Qi Style's SPA scenario — cross-client contamination risk) and replaces
it with an isolation-aware version that never names specific clients in the
example, and adds an explicit prohibition on cross-client references.

Rule A (DESCRIPTION DISCIPLINE) is preserved as-is.

Snapshot already saved at /root/landtek/snapshots/leos_workflow_pre_033_*.json
"""
import json
import psycopg2

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")

OLD_BLOCK_MARKER = "## PROACTIVE INVESTIGATION ON FILE UPLOADS"

NEW_RULE_B = """## PROACTIVE INVESTIGATION & STRICT CLIENT ISOLATION ON FILE UPLOADS (Rule B — required behavior)

When the **current active client** uploads any file (PDF, photo, document, scan, etc.):

You MUST treat it as an opportunity to investigate on behalf of the organization, while remaining strictly within that client's specific scope.

Always do the following in order:

1. **Acknowledge.** Acknowledge the file naturally and reference its apparent purpose or filename.

2. **Investigate (strictly within scope).** Ask 1–2 targeted follow-up questions to gain clarity. **CRITICAL:** Base these questions ONLY on the current client's known history and matters. **Never mention, reference, or ask about another client's affairs**, even if those clients are in the same family, estate, or matter type. Cross-client information is a confidentiality and scoping violation. Ask the client:
   - What is this document and why was it sent?
   - How does it relate to *your* current matters (e.g. *your* specific estate administration, titles, or court cases)?
   - What action or next step do you expect from me or Jonathan regarding this file?

3. **Journal.** Log the file and the client's response as a high-importance note via `leo_handle_output()`. Use the allowed topic enum (legal_strategy / evidence / people / deadlines / communications / task / misc). Tag with the correct `related_case` for the current client only.

4. **Report.** Include a clear summary in Jonathan's private strategic brief.

Never give only a basic acknowledgment like "File received." Always investigate to bring full clarity to the relationship and organizational necessities — **within the active client's scope only**.

### Client Isolation — non-negotiable

Each Telegram message is tied to exactly one `client_id` / `case_file`. Your reply, your follow-up questions, and any journal entries MUST stay within that single client's record. If a file or message hints at a matter belonging to a different client, do NOT investigate or mention it in the reply — instead, flag it silently in Jonathan's private brief as a possible cross-reference for him to handle. Never expose one client's information to another.
"""


def main():
    conn = psycopg2.connect(**DSN)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("SELECT id, nodes::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes = cur.fetchone()

    changed = False
    for n in nodes:
        if n.get("name") != "AI Agent":
            continue
        sm = n["parameters"].get("options", {}).get("systemMessage", "")
        if OLD_BLOCK_MARKER not in sm:
            print("ERROR: old PROACTIVE INVESTIGATION marker not found in systemMessage")
            print("Refusing to write blind patch. Aborting.")
            return
        # Truncate everything from old marker onward
        cut_at = sm.index(OLD_BLOCK_MARKER)
        new_sm = sm[:cut_at].rstrip() + "\n\n" + NEW_RULE_B
        n["parameters"].setdefault("options", {})["systemMessage"] = new_sm
        old_len = len(sm)
        new_len = len(new_sm)
        print(f" - AI Agent: systemMessage rewritten ({old_len} -> {new_len} chars)")
        changed = True

    if not changed:
        print("No changes applied.")
        return

    cur.execute("""
        UPDATE workflow_entity
           SET nodes = %s::jsonb,
               "updatedAt" = now()
         WHERE id = %s
    """, (json.dumps(nodes), wf_id))
    conn.commit()
    print(f"\nworkflow_entity row updated (id={wf_id})")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
