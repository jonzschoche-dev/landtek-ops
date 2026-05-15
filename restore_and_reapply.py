#!/usr/bin/env python3
"""Restore Leos Workflow from pre_035 snapshot, then re-apply 035 + 036.

Recovers from the n8n UI auto-save wipe that happened at 2026-05-15 00:17:50 UTC.

Source snapshot: /root/landtek/snapshots/leos_workflow_pre_035_20260515T001001Z.json
  contains: deploys 032 (templates+RuleA+RuleB-basic), 033 (RuleB isolation-aware),
            034 (Insert Chat/Cal + raw_llm_output), 034b (Log Leo Interaction fallback)

Then on top of restored state:
  - apply 035 (merge broader matter list into Rule B)
  - apply 036 (append Jonathan-leakage clause)
"""
import json
import psycopg2

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
SNAPSHOT_PATH = "/root/landtek/snapshots/leos_workflow_pre_035_20260515T001001Z.json"

# ── Deploy 035 — merge broader matter list into Rule B ─────────────────────
OLD_RULE_B_HEADER_035 = "## PROACTIVE INVESTIGATION & STRICT CLIENT ISOLATION ON FILE UPLOADS"

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

# ── Deploy 036 — append explicit Jonathan-leakage clause ───────────────────
ANCHOR_036 = "Never expose one client's information to another."
APPEND_036 = (
    " Never assume or leak information from Jonathan's matters or any other "
    "client to the talking client — including his strategy, instructions, "
    "communications, deadlines, or activities on unrelated matters."
)


def apply_035(sm):
    if OLD_RULE_B_HEADER_035 not in sm:
        raise RuntimeError("035: Rule B header not found in restored prompt — bad snapshot?")
    cut_at = sm.index(OLD_RULE_B_HEADER_035)
    return sm[:cut_at].rstrip() + "\n\n" + MERGED_RULE_B


def apply_036(sm):
    if ANCHOR_036 not in sm:
        raise RuntimeError("036: anchor not found after 035 — bad merge?")
    return sm.replace(ANCHOR_036, ANCHOR_036 + APPEND_036, 1)


def main():
    # Load snapshot
    with open(SNAPSHOT_PATH) as f:
        snap = json.loads(f.read())

    snap_nodes = snap["nodes"]
    snap_conns = snap["connections"]

    # Coerce nodes/connections if they came in as strings (psql escapes)
    if isinstance(snap_nodes, str):
        snap_nodes = json.loads(snap_nodes)
    if isinstance(snap_conns, str):
        snap_conns = json.loads(snap_conns)

    print(f" - Snapshot loaded ({len(snap_nodes)} nodes, snapshot size {len(json.dumps(snap_nodes))} bytes)")

    # Apply 035 + 036 to AI Agent systemMessage IN MEMORY
    for n in snap_nodes:
        if n.get("name") == "AI Agent":
            sm = n["parameters"].get("options", {}).get("systemMessage", "")
            sm = apply_035(sm)
            sm = apply_036(sm)
            n["parameters"].setdefault("options", {})["systemMessage"] = sm
            print(f" - AI Agent: re-applied 035 + 036 (final length {len(sm)} chars)")
            break

    # Write to DB
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    cur.execute("""
        UPDATE workflow_entity
           SET nodes = %s::jsonb,
               connections = %s::jsonb,
               "updatedAt" = now()
         WHERE name = 'Leos Workflow'
    """, (json.dumps(snap_nodes), json.dumps(snap_conns)))
    conn.commit()
    print(" - workflow_entity updated atomically")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
