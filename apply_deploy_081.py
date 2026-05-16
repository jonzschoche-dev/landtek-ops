#!/usr/bin/env python3
"""Deploy 081 — File location + Jonathan cross-client visibility.

Incidents (2026-05-16 Don Qi thread):
  1. Don Qi uploads file at 9:36. Leo replies generically — never references
     content. Root cause: file path runs AFTER Parse Agent1 (parallel),
     extraction not done by AI's turn.
  2. Jonathan asks at 9:40 "Where can I find this file?" Leo replies "Which
     file?" Root cause: Execute a SQL query filters recent_documents by
     case_file = c.case_file. Jonathan's case_file is 'Owner', so Don Qi's
     MWK-001 uploads are invisible to him.
  3. File location isn't surfaced anywhere — file_path + drive_link exist
     in DB but never shown to user.

Fixes:
  A. SQL change: when sender is Jonathan (6513067717), recent_documents
     returns ALL recent docs across all case_files (full operator view).
  B. New "Notify File Location" Telegram node after Log File Receipt1.
     Sends Jonathan a structured DM: filename / id / case_file / local
     path / Drive link / dashboard URL.
  C. Prompt: when user asks "where is X file" / "find Y" / "locate Z",
     look at recent_documents for matching filename and return file_path,
     drive_link (if any), and dashboard URL https://leo.hayuma.org/files/<id>.
  D. Prompt: when client uploads file, acknowledge briefly + flag for
     review; if recent_documents[0] doesn't yet show content for the
     current upload, say "logging now, will follow up once I've read it"
     instead of asking generic questions.
"""
import json
import os
import sys
import uuid
import argparse
import time

sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

WF_NAME = "Leos Workflow"
TELEGRAM_CRED = {"id": "dSI1mdlTrzwdd1B8", "name": "Telegram account"}
JONATHAN_CHAT_ID = "6513067717"

# ── (A) SQL change: Jonathan sees all clients' recent_documents ───────────
SQL_OLD_DOCS_FILTER = """      FROM documents
      WHERE case_file = c.case_file
        AND coalesce(extracted_text,'') <> ''"""
SQL_NEW_DOCS_FILTER = """      FROM documents
      WHERE (c.telegram_id = '6513067717' OR case_file = c.case_file)
        AND coalesce(extracted_text,'') <> ''"""

# ── (B) New Telegram node config ──────────────────────────────────────────
FILE_LOC_TEXT = """📁 File logged: <b>{{ $('Log File Receipt1').first().json.original_filename || 'unnamed' }}</b>

DOC ID: {{ $('Log File Receipt1').first().json.id }}
Case: {{ $('Log File Receipt1').first().json.case_file || 'unclassified' }}
Sender: {{ $('Telegram Trigger').first().json.message.from.first_name }}

Local: <code>{{ $('Log File Receipt1').first().json.file_path || '(not yet captured)' }}</code>
Drive: {{ $('Log File Receipt1').first().json.drive_link || '(not in Drive yet)' }}
Dashboard: https://leo.hayuma.org/files/{{ $('Log File Receipt1').first().json.id }}"""


def make_file_loc_node(base_pos):
    x, y = base_pos
    return {
        "id": str(uuid.uuid4()),
        "name": "Notify File Location",
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [x + 200, y + 80],
        "onError": "continueRegularOutput",
        "parameters": {
            "text": FILE_LOC_TEXT,
            "chatId": JONATHAN_CHAT_ID,
            "parseMode": "HTML",
            "additionalFields": {"parse_mode": "HTML", "appendAttribution": False},
        },
        "credentials": {"telegramApi": TELEGRAM_CRED},
    }


# ── (C)(D) Prompt additions ────────────────────────────────────────────────
RULE_LOC_MARKER = "### Truthfulness about capabilities (added 2026-05-16)"

RULE_LOC_ADDITION = """

### File location & retrieval (added 2026-05-16 — deploy_081)

When ANY sender (Jonathan or client) asks about WHERE a file is, HOW to find/access X document, or to retrieve Y by name/case/TCT/keyword:

1. Scan `RECENT DOCUMENTS UPLOADED BY THIS CLIENT` for a matching filename / case_file / topic.
2. Reply with these THREE locators (use whichever fields are populated):
   - **DOC id**: e.g. `DOC 686`
   - **Local path** on VPS: e.g. `/root/landtek/uploads/385170_file_42.docx`
   - **Drive link** (if drive_file_id exists): `https://drive.google.com/file/d/<id>/view`
   - **Files Dashboard URL**: `https://leo.hayuma.org/files/<doc_id>` (always works)
3. If multiple files match, list all candidates with id + filename.
4. If no match, refuse honestly: "I don't see that file in the documents index. If it was just uploaded, extraction may still be in progress — try again in a moment."

NEVER reply "which file?" when the conversation history makes the referent obvious — scan RECENT CONVERSATION HISTORY for the most recently mentioned file.

### File uploads — defer follow-up until extracted (added 2026-05-16)

When `hasFile === true` for the current turn AND the file does NOT yet appear in `RECENT DOCUMENTS UPLOADED BY THIS CLIENT[0]` (extraction is still running in parallel):

1. Acknowledge naturally: "Got <filename> — logging now. I'll follow up with what I see in it shortly."
2. Emit `chat_note_to_save` capturing the receipt + filename + sender.
3. Do NOT ask follow-up questions. Wait for the next user turn to discuss content; by then recent_documents will include the freshly-extracted excerpt.

When the file DOES appear in recent_documents[0] with non-empty extracted_excerpt, you can engage substantively: reference specific parties, dates, TCT numbers, etc. from the excerpt."""


def patch_sql(node):
    q = node["parameters"]["query"]
    if SQL_OLD_DOCS_FILTER not in q:
        if "c.telegram_id = '6513067717' OR case_file" in q:
            return False
        raise ValueError("Execute a SQL query: documents filter marker not found")
    node["parameters"]["query"] = q.replace(SQL_OLD_DOCS_FILTER, SQL_NEW_DOCS_FILTER)
    return True


def patch_prompt(node):
    p = node["parameters"]["options"]["systemMessage"]
    if "File location & retrieval (added 2026-05-16 — deploy_081)" in p:
        return False
    if RULE_LOC_MARKER not in p:
        raise ValueError("Rule E truthfulness marker not found")
    node["parameters"]["options"]["systemMessage"] = p.replace(
        RULE_LOC_MARKER, RULE_LOC_MARKER + RULE_LOC_ADDITION
    )
    return True


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
    snap = f"/root/landtek/snapshots/leos_workflow_pre_081_{args.target}_{ts}.json"
    os.makedirs("/root/landtek/snapshots", exist_ok=True)
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes, "connections": conns}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    # A. SQL change
    sql = next((n for n in nodes if n["name"] == "Execute a SQL query"), None)
    if sql and patch_sql(sql):
        print("  ✓ SQL: Jonathan now sees all clients' recent_documents")
    else:
        print("  ⚠ SQL already patched")

    # B. Add Notify File Location node + wire
    log_recv = next((n for n in nodes if n["name"] == "Log File Receipt1"), None)
    if not log_recv:
        sys.exit("FATAL: Log File Receipt1 not found")
    if not any(n["name"] == "Notify File Location" for n in nodes):
        new_node = make_file_loc_node(log_recv.get("position", [0, 0]))
        nodes.append(new_node)
        print("  ✓ Added node: Notify File Location")
    # Wire: Log File Receipt1 -> Notify File Location
    if "Log File Receipt1" not in conns or not conns["Log File Receipt1"].get("main"):
        conns["Log File Receipt1"] = {"main": [[]]}
    existing_targets = conns["Log File Receipt1"]["main"][0]
    if not any(t.get("node") == "Notify File Location" for t in existing_targets):
        existing_targets.append({"node": "Notify File Location", "type": "main", "index": 0})
        print("  ✓ Wired Log File Receipt1 -> Notify File Location")

    # C. Prompt additions
    aia = next((n for n in nodes if n["name"] == "AI Agent"), None)
    if aia and patch_prompt(aia):
        print("  ✓ AI Agent prompt: file location & deferred follow-up rules added")
    else:
        print("  ⚠ AI Agent prompt already patched")

    cur.close(); conn.close()

    if args.target == "staging":
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute('UPDATE workflow_entity SET nodes=%s::jsonb, connections=%s::jsonb, "updatedAt"=now() WHERE id=%s',
                    (json.dumps(nodes), json.dumps(conns), wf_id))
        cur.execute("""UPDATE workflow_history SET nodes=%s::json, connections=%s::json
                         WHERE "workflowId"=%s
                           AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""",
                    (json.dumps(nodes), json.dumps(conns), wf_id, wf_id))
        cur.execute('UPDATE workflow_entity SET active=false, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); time.sleep(2)
        cur.execute('UPDATE workflow_entity SET active=true, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()
        print("  ✓ staging updated + reactivated")
    else:
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes, connections=conns)


if __name__ == "__main__":
    main()
