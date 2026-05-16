#!/usr/bin/env python3
"""Deploy 061 — Replace Extract File Text Code node with HTTP Request node.

n8n's task-runner sandbox blocks:
  - require('child_process')  (deploy_059 hit this)
  - global fetch              (deploy_060 hit this)

The only reliable way to do HTTP from inside the workflow is n8n's built-in
HTTP Request node (`n8n-nodes-base.httpRequest`). 'Log Leo Interaction' uses
this same pattern successfully.

This deploy:
- Replaces the Extract File Text Code node with HTTP Request node
- POSTs $binary.data as JSON to http://172.18.0.1:8765/api/extract_file_text
- Endpoint returns {extracted_text, char_count, status, local_path, mime_type}
- Log File Receipt1 reads $('Extract File Text').first().json.extracted_text (still works — node name preserved)
"""
import json, sys
sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
WF_ID = "vSDQv1vfn6627bnA"


# n8n expression for the JSON body
JSON_BODY_EXPR = '''={{ {
  base64_data: $binary.data.data,
  original_filename: $binary.data.fileName || $('Telegram Trigger').first().json.message?.document?.file_name || 'uploaded_file',
  mime_type: $binary.data.mimeType || ''
} }}'''


def snapshot():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = f"/root/landtek/snapshots/leos_workflow_pre_061_{ts}.json"
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

    # Find and replace Extract File Text
    found = False
    for n in nodes:
        if n.get("name") != "Extract File Text":
            continue
        # Preserve id, name, position; replace type and parameters
        n["type"] = "n8n-nodes-base.httpRequest"
        n["typeVersion"] = 4.2
        n["parameters"] = {
            "url": "http://172.18.0.1:8765/api/extract_file_text",
            "method": "POST",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": JSON_BODY_EXPR,
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "options": {"timeout": 60000},
        }
        found = True
        print(f" - Extract File Text: replaced Code node -> httpRequest node")
        print(f"     URL: http://172.18.0.1:8765/api/extract_file_text")
        print(f"     Body: base64_data + original_filename + mime_type from $binary.data")

    if not found:
        print(" - Extract File Text node not found")
        return

    cur.close(); conn.close()
    from deploy_helpers import patch_workflow_dual
    patch_workflow_dual(WF_ID, nodes=nodes, connections=conns)


if __name__ == "__main__":
    main()
    from deploy_helpers import commit_deploy
    msg = """Extract File Text: Code node -> HTTP Request node

deploy_059 hit: require('child_process') is disallowed.
deploy_060 hit: ReferenceError: fetch is not defined.

n8n's task-runner sandbox blocks both. The ONLY reliable HTTP path
from inside the workflow is n8n's built-in n8n-nodes-base.httpRequest
node. 'Log Leo Interaction' uses this same pattern (already proven).

This deploy replaces the Extract File Text Code node with an HTTP
Request node:
  URL:    http://172.18.0.1:8765/api/extract_file_text
  Method: POST
  Body:   JSON {base64_data, original_filename, mime_type} from $binary.data
  Output: $json contains {extracted_text, char_count, status, local_path, mime_type}

Node name 'Extract File Text' is preserved, so Log File Receipt1's
expression ={{ $('Extract File Text').first().json.extracted_text }}
keeps working without changes.

Test post-deploy: re-upload a file. documents.extracted_text should
finally populate with real content."""
    commit_deploy("061", msg)
