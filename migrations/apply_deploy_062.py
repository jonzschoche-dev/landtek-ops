#!/usr/bin/env python3
"""Deploy 062 — Extract File Text uses multipart binary upload.

deploy_061 set up the HTTP Request node correctly except for one issue:
n8n's binary data mode is 'filesystem-v2', so $binary.data.data resolves
to the literal string 'filesystem-v2' (a storage marker), NOT the actual
base64. The HTTP node sent an empty base64_data field -> Flask 400.

Fix: configure the HTTP Request node to use multipart/form-data with
n8n's built-in 'send binary' parameter type. This automatically reads
the binary from filesystem-v2 storage and uploads it properly.

Flask endpoint /api/extract_file_text already updated in this deploy's
prep step to accept multipart uploads (in addition to JSON+base64 path).
"""
import json, sys
sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
WF_ID = "vSDQv1vfn6627bnA"


def snapshot():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = f"/root/landtek/snapshots/leos_workflow_pre_062_{ts}.json"
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
        if n.get("name") != "Extract File Text":
            continue
        n["parameters"] = {
            "url": "http://172.18.0.1:8765/api/extract_file_text",
            "method": "POST",
            "sendBody": True,
            "contentType": "multipart-form-data",
            "bodyParameters": {
                "parameters": [
                    {
                        "name": "file",
                        "parameterType": "formBinaryData",
                        "inputDataFieldName": "data",
                    },
                    {
                        "name": "original_filename",
                        "value": "={{ $binary.data.fileName || $('Telegram Trigger').first().json.message?.document?.file_name || 'uploaded_file' }}",
                    },
                    {
                        "name": "mime_type",
                        "value": "={{ $binary.data.mimeType || '' }}",
                    },
                ]
            },
            "options": {"timeout": 60000},
        }
        print(f" - Extract File Text: switched to multipart/form-data with formBinaryData")
        print(f"     - file: binary from $binary.data (n8n filesystem-v2)")
        print(f"     - original_filename + mime_type: from $binary.data metadata")

    cur.close(); conn.close()
    from deploy_helpers import patch_workflow_dual
    patch_workflow_dual(WF_ID, nodes=nodes)


if __name__ == "__main__":
    main()
    from deploy_helpers import commit_deploy
    msg = """Extract File Text: switch to multipart/form-data binary upload

deploy_061 used JSON body with $binary.data.data, but n8n's
filesystem-v2 binary mode stores actual content on disk and resolves
$binary.data.data to the literal marker string 'filesystem-v2'.
HTTP node sent empty base64_data -> Flask 400 'base64_data required'.

Fix: HTTP Request node now uses contentType='multipart-form-data'
with bodyParameters of type 'formBinaryData' (inputDataFieldName: 'data').
n8n auto-loads the binary from filesystem storage and uploads as
multipart.

Flask endpoint /api/extract_file_text was extended to also handle
multipart in addition to JSON+base64. Both paths smoke-tested with
test_petition.docx (HTTP 200, 116 chars extracted)."""
    commit_deploy("062", msg)
