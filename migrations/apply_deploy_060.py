#!/usr/bin/env python3
"""Deploy 060 — Fix Extract File Text node: use HTTP instead of child_process.

deploy_059's Extract File Text Code node used `require('child_process').execSync`
to call extract_uploaded_file.py. n8n's task-runner blocks this for security:
  Error: Module 'child_process' is disallowed

Fix: leo_tools/server.py now has /api/extract_file_text endpoint (added in
this deploy's prep step). The Code node POSTs base64 binary there and receives
the extracted text back. No subprocess required.

Also adds: /root/landtek/leo_tools/server.py endpoint /api/extract_file_text
(this part is shell-installed before running the python script).
"""
import json, sys
sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
WF_ID = "vSDQv1vfn6627bnA"


NEW_EXTRACT_NODE_JS = """// Extract File Text — deploy_060 (uses HTTP, not child_process)
// Reads binary from Get a File, POSTs base64 to leo_tools Flask, returns extracted text.

const item = items[0];
const binData = item.binary?.data || {};
const base64Data = binData.data || '';
const originalFilename = binData.fileName ||
    $('Telegram Trigger').first().json.message?.document?.file_name ||
    'uploaded_file';
const mimeType = binData.mimeType || '';

if (!base64Data) {
    return [{ json: {
        ...item.json,
        extract_status: 'no_binary',
        extracted_text: '',
        char_count: 0,
        local_path: '',
        mime_type: mimeType,
        original_filename: originalFilename,
    } }];
}

let result;
try {
    const response = await fetch('http://172.18.0.1:8765/api/extract_file_text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            base64_data: base64Data,
            original_filename: originalFilename,
            mime_type: mimeType,
        }),
    });
    if (!response.ok) {
        result = {
            extracted_text: '',
            char_count: 0,
            status: 'http_status_' + response.status,
            local_path: '',
            mime_type: mimeType,
        };
    } else {
        result = await response.json();
    }
} catch (e) {
    result = {
        extracted_text: '',
        char_count: 0,
        status: 'http_exception: ' + String(e).slice(0, 200),
        local_path: '',
        mime_type: mimeType,
    };
}

return [{ json: {
    ...item.json,
    extracted_text: result.extracted_text || '',
    char_count: result.char_count || 0,
    extract_status: result.status || 'unknown',
    local_path: result.local_path || '',
    mime_type: result.mime_type || mimeType,
    original_filename: originalFilename,
}, binary: item.binary }];
"""


def snapshot():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = f"/root/landtek/snapshots/leos_workflow_pre_060_{ts}.json"
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

    patched = False
    for n in nodes:
        if n.get("name") != "Extract File Text":
            continue
        old_len = len(n["parameters"].get("jsCode", ""))
        n["parameters"]["jsCode"] = NEW_EXTRACT_NODE_JS
        new_len = len(NEW_EXTRACT_NODE_JS)
        print(f" - Extract File Text node: jsCode rewritten to use HTTP ({old_len} -> {new_len} chars)")
        patched = True

    if not patched:
        print(" - Extract File Text node not found — abort")
        return

    cur.close(); conn.close()
    from deploy_helpers import patch_workflow_dual
    patch_workflow_dual(WF_ID, nodes=nodes, connections=conns)


if __name__ == "__main__":
    main()
    from deploy_helpers import commit_deploy
    msg = """Fix Extract File Text: use HTTP instead of blocked child_process

deploy_059's Extract File Text Code node used require('child_process')
.execSync to shell out to extract_uploaded_file.py. n8n's task-runner
security blocks child_process:
  Error: Module 'child_process' is disallowed

Fix part A: leo_tools/server.py now has /api/extract_file_text endpoint
that wraps extract_uploaded_file.py's logic. Smoke-tested with a
116-char DOCX (HTTP 200, returned correct text).

Fix part B (this deploy): Extract File Text node JS rewritten to use
await fetch('http://172.18.0.1:8765/api/extract_file_text', ...) instead
of execSync. No subprocess required. Async function pattern matches
n8n Code node expectations.

Test post-deploy: upload a file. documents.extracted_text should be
populated with real content. Next turn's Context Builder includes
RECENT DOCUMENTS section so Leo can reference file contents."""
    commit_deploy("060", msg)
