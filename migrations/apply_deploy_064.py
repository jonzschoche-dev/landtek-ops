#!/usr/bin/env python3
"""Deploy 064 — Re-attach binary after Extract File Text (HTTP) so Drive upload works.

deploy_062 made Extract File Text an HTTP Request node. HTTP Request nodes
return ONLY the JSON response — they don't propagate the input binary.
So Resolve Folder ID -> Upload file ran without binary input, errored with:
  'This operation expects the node's input data to contain a binary file
   "data", but none was found'

Result: extraction works (text captured in documents.extracted_text), but
Drive upload fails (drive_file_id stays empty).

Fix: insert a small Code node 'Re-attach Binary' between Extract File Text
and Resolve Folder ID. The Code node reads $('Get a file').first().binary
and merges it onto the current item, restoring the binary stream for
Upload file. Code nodes can do this — only require('child_process') is
blocked; basic n8n expression access is allowed.
"""
import json, sys, uuid
sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
WF_ID = "vSDQv1vfn6627bnA"


REATTACH_JS = """// Re-attach Binary — deploy_064
// HTTP Request nodes don't propagate input binary. Re-merge the binary
// from Get a file so downstream nodes (Resolve Folder ID, Upload file)
// have it available.

const original = items[0];
const getAFileBinary = $('Get a file').first().binary || {};

return [{
    json: original.json,
    binary: getAFileBinary,
}];
"""


def snapshot():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = f"/root/landtek/snapshots/leos_workflow_pre_064_{ts}.json"
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

    # 1. Add Re-attach Binary node (idempotent)
    if any(n.get("name") == "Re-attach Binary" for n in nodes):
        print(" - Re-attach Binary node already exists")
    else:
        # Place it between Extract File Text and Resolve Folder ID
        eft_pos = next((n.get("position", [800, 200]) for n in nodes if n.get("name") == "Extract File Text"), [800, 200])
        new_node = {
            "id": str(uuid.uuid4()),
            "name": "Re-attach Binary",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [eft_pos[0] + 200, eft_pos[1]],
            "parameters": {"jsCode": REATTACH_JS},
        }
        nodes.append(new_node)
        print(" - Added node: Re-attach Binary")

    # 2. Rewire: Extract File Text -> Re-attach Binary -> Resolve Folder ID
    #    (was: Extract File Text -> Resolve Folder ID)
    if "Extract File Text" in conns:
        for branch in conns["Extract File Text"].get("main", []):
            for edge in branch:
                if edge.get("node") == "Resolve Folder ID":
                    edge["node"] = "Re-attach Binary"
                    print(" - Rerouted: Extract File Text -> Re-attach Binary (was: -> Resolve Folder ID)")

    # 3. Add Re-attach Binary -> Resolve Folder ID
    if "Re-attach Binary" not in conns or not any(
        e.get("node") == "Resolve Folder ID"
        for branch in conns.get("Re-attach Binary", {}).get("main", [])
        for e in branch
    ):
        conns["Re-attach Binary"] = {"main": [[{"node": "Resolve Folder ID", "type": "main", "index": 0}]]}
        print(" - Wired: Re-attach Binary -> Resolve Folder ID")

    cur.close(); conn.close()
    from deploy_helpers import patch_workflow_dual
    patch_workflow_dual(WF_ID, nodes=nodes, connections=conns)


if __name__ == "__main__":
    main()
    from deploy_helpers import commit_deploy
    msg = """Re-attach binary after Extract File Text (fixes Drive upload)

deploy_062 made Extract File Text an n8n HTTP Request node. HTTP
Request nodes return ONLY the JSON response, dropping the input
binary. So Resolve Folder ID -> Upload file lost the binary and
errored: 'expects binary file data, but none was found'.

Result so far: extraction worked (documents.extracted_text was
populated) but Drive upload failed (drive_file_id stayed empty).

Fix: small Code node 'Re-attach Binary' between Extract File Text
and Resolve Folder ID. Reads $('Get a file').first().binary and
merges it onto the item, restoring the binary stream.

New flow: Get a file -> Extract File Text -> Re-attach Binary
         -> Resolve Folder ID -> Upload file -> Log File Receipt1

After this deploy, JONATHAN PETITION.docx (and future uploads)
should land in:
  - Local: /root/landtek/uploads/ (already working)
  - DB:    documents.extracted_text (already working post-062)
  - Drive: MWK-001 Legal folder (1y3w8gIS8SG66J2npfKhKQibOUpqwUTUi)
           with drive_file_id populated"""
    commit_deploy("064", msg)
