#!/usr/bin/env python3
"""Deploy 059 — File content extraction so Leo can inquire about file contents.

Five changes wired in one transaction (workflow_entity + workflow_history):

1. NEW node 'Extract File Text' (n8n-nodes-base.code) — inserted between
   Get a File and Resolve Folder ID. Reads $binary.data.data, writes
   binary to /root/landtek/uploads/, calls extract_uploaded_file.py,
   returns {extracted_text, char_count, status, local_path, mime_type}.

2. Reroute: Get a File -> Extract File Text -> Resolve Folder ID
   (was: Get a File -> Resolve Folder ID).

3. Log File Receipt1 column.value extended with:
   - extracted_text: from Extract File Text node
   - mime_type:      from Extract File Text node (overrides Parse Agent1's guess)
   - file_path:      local_path from Extract File Text node

4. Execute a SQL query: extends the subquery to also fetch recent_documents
   (last 4 docs for current client's case_file) with extracted_text + filename.

5. Context Builder: agentInput gets a 'RECENT DOCUMENTS' section showing
   recent file uploads + extracted text excerpt so Leo can reference content
   on the NEXT turn after a file lands.

All via patch_workflow_dual() so workflow_entity and workflow_history stay synced.
"""
import json, sys, uuid
sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
WF_ID = "vSDQv1vfn6627bnA"


EXTRACT_NODE_JS = """// Extract File Text — deploy_059
// Reads the binary from Get a File, decodes, calls Python extractor,
// returns {extracted_text, char_count, status, local_path, mime_type}.

const { execSync } = require('child_process');

const itemIn = items[0];
const binData = itemIn.binary?.data || {};
const base64Data = binData.data || '';
const originalFilename = binData.fileName || $('Telegram Trigger').first().json.message?.document?.file_name || 'uploaded_file';
const mimeType = binData.mimeType || '';

if (!base64Data) {
    return [{ json: {
        ...itemIn.json,
        extract_status: 'no_binary',
        extracted_text: '',
        char_count: 0,
        local_path: '',
        mime_type: mimeType,
        original_filename: originalFilename,
    } }];
}

const payload = JSON.stringify({
    base64_data: base64Data,
    original_filename: originalFilename,
    mime_type: mimeType,
});

let result;
try {
    const out = execSync('python3 /root/landtek/extract_uploaded_file.py', {
        input: payload,
        encoding: 'utf-8',
        maxBuffer: 50 * 1024 * 1024,
        timeout: 60000,
    });
    result = JSON.parse(out);
} catch (e) {
    result = {
        extracted_text: '',
        char_count: 0,
        status: 'exec_error: ' + e.message.slice(0, 200),
        local_path: '',
        mime_type: mimeType,
    };
}

return [{ json: {
    ...itemIn.json,
    extracted_text: result.extracted_text || '',
    char_count: result.char_count || 0,
    extract_status: result.status || 'unknown',
    local_path: result.local_path || '',
    mime_type: result.mime_type || mimeType,
    original_filename: originalFilename,
}, binary: itemIn.binary }];
"""


NEW_SQL_QUERY = """SELECT
  c.*,
  (
    SELECT json_agg(conv)
    FROM (
      SELECT timestamp, client_name, message_caption, leo_response, category
      FROM conversations
      WHERE case_file = c.case_file
      ORDER BY timestamp DESC
      LIMIT 4
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
      WHERE case_file = c.case_file
        AND coalesce(extracted_text,'') <> ''
      ORDER BY id DESC
      LIMIT 4
    ) docs
  ) as recent_documents
FROM clients c
LEFT JOIN cases ca ON ca.case_file = c.case_file
WHERE c.telegram_id = '{{ $json.message.from.id }}'
LIMIT 1"""


def snapshot():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = f"/root/landtek/snapshots/leos_workflow_pre_059_{ts}.json"
    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("""SELECT row_to_json(w)::text FROM (SELECT id, name, nodes, connections, "updatedAt" FROM workflow_entity WHERE name='Leos Workflow') w;""")
    with open(path, "w") as f: f.write(cur.fetchone()[0])
    cur.close(); conn.close()
    print(f" - snapshot: {path}")


def main():
    snapshot()
    conn = psycopg2.connect(**DSN); conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SELECT nodes::jsonb, connections::jsonb FROM workflow_entity WHERE id=%s", (WF_ID,))
    nodes, conns = cur.fetchone()

    # ── 1. Add 'Extract File Text' node ───────────────────────────────────
    if any(n.get("name") == "Extract File Text" for n in nodes):
        print(" - Extract File Text node already exists")
    else:
        get_a_file_pos = next((n.get("position", [600, 200]) for n in nodes if n.get("name") == "Get a file"), [600, 200])
        new_node = {
            "id": str(uuid.uuid4()),
            "name": "Extract File Text",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [get_a_file_pos[0] + 200, get_a_file_pos[1]],
            "parameters": {"jsCode": EXTRACT_NODE_JS},
        }
        nodes.append(new_node)
        print(" - Added node: Extract File Text")

    # ── 2. Reroute: Get a file -> Extract File Text -> Resolve Folder ID ──
    if "Get a file" in conns:
        for branch in conns["Get a file"].get("main", []):
            for edge in branch:
                if edge.get("node") == "Resolve Folder ID":
                    edge["node"] = "Extract File Text"
                    print(" - Rerouted: Get a file -> Extract File Text (was: -> Resolve Folder ID)")
    # Wire Extract File Text -> Resolve Folder ID
    if "Extract File Text" not in conns or not any(
        e.get("node") == "Resolve Folder ID"
        for branch in conns.get("Extract File Text", {}).get("main", [])
        for e in branch
    ):
        conns["Extract File Text"] = {"main": [[{"node": "Resolve Folder ID", "type": "main", "index": 0}]]}
        print(" - Wired: Extract File Text -> Resolve Folder ID")

    # ── 3. Log File Receipt1: add extracted_text + mime_type + file_path ──
    for n in nodes:
        if n.get("name") != "Log File Receipt1":
            continue
        cols = n["parameters"].setdefault("columns", {}).setdefault("value", {})
        cols["extracted_text"] = "={{ $('Extract File Text').first().json.extracted_text }}"
        cols["mime_type"] = "={{ $('Extract File Text').first().json.mime_type }}"
        cols["file_path"] = "={{ $('Extract File Text').first().json.local_path }}"
        # Ensure schema array has these (so n8n doesn't strip them)
        schema = n["parameters"]["columns"].get("schema", [])
        existing_ids = {s.get("id") for s in schema}
        for fld_id in ["extracted_text", "file_path"]:
            if fld_id not in existing_ids:
                schema.append({
                    "id": fld_id, "type": "string", "display": True,
                    "removed": False, "required": False, "displayName": fld_id,
                    "defaultMatch": False, "canBeUsedToMatch": True,
                })
        n["parameters"]["columns"]["schema"] = schema
        print(" - Log File Receipt1: added extracted_text, mime_type, file_path columns")

    # ── 4. Execute a SQL query: extend query to fetch recent_documents ────
    for n in nodes:
        if n.get("name") != "Execute a SQL query":
            continue
        old_q = n["parameters"].get("query", "")
        if "recent_documents" in old_q:
            print(" - Execute a SQL query: already extended with recent_documents")
        else:
            n["parameters"]["query"] = NEW_SQL_QUERY
            print(f" - Execute a SQL query: extended ({len(old_q)} -> {len(NEW_SQL_QUERY)} chars)")

    # ── 5. Context Builder: include RECENT DOCUMENTS section in agentInput ──
    for n in nodes:
        if n.get("name") != "Context Builder":
            continue
        js = n["parameters"].get("jsCode", "")
        if "RECENT DOCUMENTS" in js:
            print(" - Context Builder: already has RECENT DOCUMENTS section")
        else:
            # Insert recent_documents block after recent conversations
            anchor = "// Build client profile"
            if anchor not in js:
                print(" - WARN: Context Builder anchor not found, skipping")
                continue
            insertion = """// Build recent documents (deploy_059)
const recentDocs = clientRow?.recent_documents || [];
const documentsBlock = recentDocs.length
  ? recentDocs.map(d =>
      `--- DOC ${d.id}: ${d.original_filename || 'unnamed'} (${d.char_count || 0} chars)\\n` +
      `Excerpt:\\n${d.extracted_excerpt || '(no text extracted)'}\\n`
    ).join('\\n')
  : 'No previous file uploads with extracted content.';

"""
            new_js = js.replace(anchor, insertion + anchor, 1)

            # Now extend the agentInput template
            agentInput_anchor = "RECENT CONVERSATION HISTORY (last 4):"
            if agentInput_anchor in new_js:
                new_js = new_js.replace(
                    "${conversationHistory || \"No previous conversations\"}",
                    "${conversationHistory || \"No previous conversations\"}\n\nRECENT DOCUMENTS UPLOADED BY THIS CLIENT (last 4 with extracted content):\n${documentsBlock}",
                    1
                )
            n["parameters"]["jsCode"] = new_js
            print(f" - Context Builder: RECENT DOCUMENTS section added ({len(js)} -> {len(new_js)} chars)")

    # ── 6. Persist via patch_workflow_dual ───────────────────────────────
    cur.close(); conn.close()
    from deploy_helpers import patch_workflow_dual
    patch_workflow_dual(WF_ID, nodes=nodes, connections=conns)


if __name__ == "__main__":
    main()
    from deploy_helpers import commit_deploy
    msg = """File content extraction — Leo sees uploaded file contents on next turn

NEW: Extract File Text Code node + extract_uploaded_file.py worker
  PDF -> fitz, DOCX -> python-docx, images -> Gemini Vision.
  Fitz fallback to Gemini if <200 chars (scanned PDFs).

Wiring: Get a File -> Extract File Text -> Resolve Folder ID -> ...
  (extraction happens BEFORE Drive upload; result is captured in
  Log File Receipt1's INSERT into documents.extracted_text)

Data:
  documents.extracted_text now populated for every file upload
  documents.file_path = local copy at /root/landtek/uploads/<pid>_<name>
  documents.mime_type = correct value (was empty before)

Memory plumbing:
  Execute a SQL query extended with recent_documents subquery (last 4
  docs per case_file with non-empty extracted_text + 1500-char excerpt)
  Context Builder agentInput gets RECENT DOCUMENTS section showing
  recent file content excerpts. Leo references this on NEXT turn after
  a file lands.

Test post-deploy: upload a DOCX/PDF to Leo. Reply now should still be
filename-based (extraction runs in parallel with AI Agent). NEXT turn:
asking about the file's content should produce informed answers."""
    commit_deploy("059", msg)
