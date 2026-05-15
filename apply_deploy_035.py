#!/usr/bin/env python3
"""Deploy 035 — merge broader matter-type list into live Rule B while preserving
the STRICT CLIENT ISOLATION clause.

Source A (broader matter list): /root/landtek/leo_proactive_file_rule.py (from deploy 033 cowork)
Source B (isolation clause):    currently live in AI Agent systemMessage (from in-place deploy 033)

Result: a single Rule B block in the live prompt that has both.

Snapshot saved at /root/landtek/snapshots/leos_workflow_pre_035_*.json
"""
import json
import psycopg2
import datetime

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")

OLD_RULE_B_HEADER = "## PROACTIVE INVESTIGATION & STRICT CLIENT ISOLATION ON FILE UPLOADS"

MERGED_RULE_B = """## PROACTIVE INVESTIGATION & STRICT CLIENT ISOLATION ON FILE UPLOADS (Rule B — required behavior)

When the **current active client** uploads any file (PDF, photo, document, scan, contract, voice, video, etc.):

You MUST treat it as an opportunity to investigate on behalf of the organization — while remaining strictly within that client's specific scope. This rule applies to EVERY file upload from EVERY client.

### Required actions, in order

1. **Acknowledge.** Acknowledge the file naturally and reference its apparent purpose or filename.

2. **Investigate — strictly within scope.** Ask at least 1–2 targeted, natural follow-up questions to gain clarity. **CRITICAL:** Base these questions ONLY on the current client's known history and matters. **Never mention, reference, or ask about another client's affairs**, even if those clients are in the same family, estate, or matter type. Cross-client information is a confidentiality and scoping violation. Cover questions across these dimensions, but only within this client's known matters:
   - What is this document and why was it sent?
   - How does it relate to *your* current matters (e.g. *your* specific estate administration, titles, court cases, guardianship, mining, investments, construction, contracts, or other ongoing matters)?
   - What action or next step do you expect from me or Jonathan regarding this file?
   - Does this trigger any organizational needs (filing, indexing, legal review, OCR queue, conflict check, calendar entry)?

3. **Journal.** Log the file and the client's response as a high-importance note via `leo_handle_output()`. Use the allowed topic enum (legal_strategy / evidence / people / deadlines / communications / task / misc). Tag with the correct `related_case` for the **current client only**.

4. **Report.** Include a clear summary in Jonathan's private strategic brief.

Never give only a basic acknowledgment like "File received." Always investigate to bring full clarity to the relationship, the client's needs, and organizational necessities — **within the active client's scope only**.

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
        if OLD_RULE_B_HEADER not in sm:
            print("ERROR: old Rule B header not found — refusing blind patch")
            return

        cut_at = sm.index(OLD_RULE_B_HEADER)
        new_sm = sm[:cut_at].rstrip() + "\n\n" + MERGED_RULE_B
        n["parameters"].setdefault("options", {})["systemMessage"] = new_sm
        old_len = len(sm)
        new_len = len(new_sm)
        print(f" - AI Agent: Rule B merged ({old_len} -> {new_len} chars, delta {new_len - old_len:+d})")
        changed = True

    if not changed:
        print("No changes applied.")
        return

    cur.execute("""
        UPDATE workflow_entity SET nodes=%s::jsonb, "updatedAt"=now() WHERE id=%s
    """, (json.dumps(nodes), wf_id))
    conn.commit()
    print(f"\nworkflow_entity row updated (id={wf_id})")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
