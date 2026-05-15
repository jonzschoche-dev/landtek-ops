#!/usr/bin/env python3
"""Deploy 032 — single transaction patch on Leos Workflow.

Three changes in one shot:
  1. Log File Receipt1: strip trailing ` }} }}` from all 7 column expressions,
     strip 2 leading spaces from original_filename, add drive_file_id mapping.
  2. Upload file (Drive): name expression gets fallback chain.
  3. AI Agent: append Rule A (action_items[].description must be non-empty)
     and Rule B (proactive investigation on file uploads).

Snapshot already saved at /root/landtek/snapshots/leos_workflow_pre_032_*.json
"""
import json
import psycopg2

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")

PROMPT_ADDITION = """

---

## DESCRIPTION DISCIPLINE (Rule A — non-negotiable)

Every entry in `action_items[]` MUST have a non-empty `description` field. If you cannot articulate the concrete action in one sentence, OMIT the entry entirely. Never emit `{description: "", ...}` — that creates blank rows in the action_items table and is treated as a system bug.

## PROACTIVE INVESTIGATION ON FILE UPLOADS (Rule B — required behavior)

When a client uploads ANY file (document, photo, voice, video), you are required to:

1. **Acknowledge** the file and its apparent purpose in your reply (recognize the filename, file type, and any obvious context from the upload moment).

2. **Investigate by asking follow-up questions** that surface clarity in at least three of these dimensions:
   - **What is this?** — confirm document type, parties, date, jurisdiction, version
   - **Why was it sent?** — is it for filing, evidence, review, signature, information, or another purpose?
   - **How does it relate to current matters?** — link to the active matter (e.g. MWK-CV26360), specific titles (T-4497 and derivatives), known transferees, or ongoing court actions
   - **What action does the client expect?** — review, file with court, send to counsel, hold for hearing, draft response, etc.
   - **What organizational needs does it trigger?** — filing path, indexing, OCR queue, conflict check, deadline calendar entry, escalation to Atty. Barandon

3. **Log the upload as a structured note** via `leo_handle_output()` with topic in the allowed enum (legal_strategy / evidence / people / deadlines / communications / task / misc). Include the filename, apparent classification, and the client's stated purpose if known.

4. **Treat every file upload as an investigative opportunity** — Leo is not a passive intake clerk. Each upload is a chance to bring clarity to the client relationship and surface organizational needs. A bare acknowledgment without follow-up questions is a failure mode.

Example of correct behavior (SPA upload):
> "I've received the 2025 Special Power of Attorney with Jonathan Zschoche as attorney-in-fact. Before I file this in the MWK Legal folder and flag it for Atty. Barandon's review, three questions: (1) Is this the SPA Don Qi Style mentioned earlier for the guardianship meeting with Atty. Botor, or a separate instrument? (2) Should I treat this as evidence in Civil Case 26-360 (Zschoche v. Balane), or is it limited to estate administration? (3) Do you want me to draft a one-page memo summarizing the powers granted, for use in the upcoming pre-trial?"
"""


def main():
    conn = psycopg2.connect(**DSN)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes, conns = cur.fetchone()

    changes = []

    for n in nodes:
        # 1. Log File Receipt1 — fix expressions
        if n.get("name") == "Log File Receipt1":
            cols = n["parameters"]["columns"]["value"]

            replacements = {
                "case_file": "={{ $('Parse Agent1').first().json.case_file }}",
                "mime_type": "={{ $('Parse Agent1').first().json.mime_type }}",
                "drive_link": "={{ $json.webViewLink }}",
                "classification": "={{ $('Parse Agent1').first().json.classification }}",
                "smart_filename": "={{ $('Parse Agent1').first().json.smart_filename }}",
                "original_filename": "={{ $('Parse Agent1').first().json.fileName }}",
                "strategic_relevance": "={{ $('Parse Agent1').first().json.context_md_content }}",
            }
            for k, v in replacements.items():
                if k in cols:
                    cols[k] = v
            # Add drive_file_id mapping (pulls from Upload file node output)
            cols["drive_file_id"] = "={{ $('Upload file').first().json.id }}"
            # Ensure drive_file_id is in the schema list as well so n8n doesn't strip it
            schema = n["parameters"]["columns"].get("schema", [])
            if not any(s.get("id") == "drive_file_id" for s in schema):
                schema.append({
                    "id": "drive_file_id",
                    "type": "string",
                    "display": True,
                    "removed": False,
                    "required": False,
                    "displayName": "drive_file_id",
                    "defaultMatch": False,
                    "canBeUsedToMatch": True,
                })
                n["parameters"]["columns"]["schema"] = schema
            changes.append("Log File Receipt1: 7 expressions cleaned + drive_file_id added")

        # 2. Upload file — name fallback
        if n.get("name") == "Upload file":
            n["parameters"]["name"] = "={{ $json.smart_filename || $json.fileName || 'untitled' }}"
            changes.append("Upload file: name fallback set (smart_filename || fileName || 'untitled')")

        # 3. AI Agent — append rules to systemMessage (idempotent: skip if already appended)
        if n.get("name") == "AI Agent":
            sm = n["parameters"].get("options", {}).get("systemMessage", "")
            if "Rule A — non-negotiable" not in sm:
                n["parameters"].setdefault("options", {})["systemMessage"] = sm + PROMPT_ADDITION
                changes.append(f"AI Agent: systemMessage extended (+{len(PROMPT_ADDITION)} chars)")
            else:
                changes.append("AI Agent: systemMessage already contains Rule A — skipped")

    cur.execute("""
        UPDATE workflow_entity
           SET nodes = %s::jsonb,
               "updatedAt" = now()
         WHERE id = %s
    """, (json.dumps(nodes), wf_id))
    conn.commit()

    for c in changes:
        print(" -", c)
    print(f"\nworkflow_entity row updated (id={wf_id})")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
