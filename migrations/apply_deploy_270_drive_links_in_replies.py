#!/usr/bin/env python3
"""Deploy 270 - Drive links surface in Leo replies.

User request (May 25): "can the system provide me a link to the document
so I can download it?"

Three pieces:
  1. (data) Backfilled documents.drive_link from drive_file_id for 209 rows
     before this migration. After backfill: MWK 551/662, PAR 53/64, Owner 3/6
     have drive_link set.
  2. (api) leo_tools/server.py: query_documents, cross_reference, party
     endpoints now return drive_link + matter_code in each row.
  3. (prompt) AI Agent system prompt: when surfacing any document in a reply,
     ALWAYS include the drive_link in this exact format:
       doc#<id>  <smart_filename or title>
       <drive_link>
     so Jonathan can tap it from Telegram.

n8n restart + leo-tools restart to load the new code.

Idempotent. Audited via app.actor='jonathan_deploy_270'.
"""
import json
import subprocess
import sys

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
WORKFLOW_ID = "vSDQv1vfn6627bnA"

NEW_RULE = """

# DRIVE LINKS RULE (deploy_270 - 2026-05-25)

When you surface any document in a reply (whether from query_documents,
cross_reference, get_party_history, or get_thread), you MUST format each doc
as:

    doc#<id>  <filename or title>
    <drive_link>

If a doc has no drive_link (some legacy docs only have file_path), say
"no Drive link available" so Jonathan knows the doc exists but can't be
downloaded directly. Never silently omit the link.

Example reply format:

  Found 5 docs on Inocalla sustainable development:
  doc#490 Maharlika Institute ECO-Wellness Tourism / Inocalla sustainable community
  https://drive.google.com/file/d/1ikzSl6-PqYscUil_JPdsEpkIcsiD08Bd/view

  doc#485 Green World Consultancy MOU (Burnaby BC)
  https://drive.google.com/file/d/1HROGYVeU7t6LJqDRXC89pqYNNX8gt9uJ/view

  ...

Every list of documents that goes to Jonathan MUST follow this format.

"""


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'jonathan_deploy_270'")

    print("Deploy 270 - Drive links in replies")
    print("=" * 60)

    cur.execute("SELECT nodes FROM workflow_entity WHERE id = %s", (WORKFLOW_ID,))
    nodes_raw = cur.fetchone()["nodes"]
    nodes = nodes_raw if isinstance(nodes_raw, list) else json.loads(nodes_raw)

    patched = False
    for n in nodes:
        if n.get("name") == "AI Agent" and n.get("type") == "@n8n/n8n-nodes-langchain.agent":
            opts = n.setdefault("parameters", {}).setdefault("options", {})
            old = opts.get("systemMessage", "")
            if "DRIVE LINKS RULE (deploy_270" in old:
                print("  already present (no-op)")
                patched = True
                break
            # Insert just before NO EMPTY PROMISES RULE
            anchor = "# NO EMPTY PROMISES RULE"
            if anchor in old:
                new = old.replace(anchor, NEW_RULE.strip() + "\n\n" + anchor, 1)
            else:
                new = old.rstrip() + "\n" + NEW_RULE
            opts["systemMessage"] = new
            print(f"  AI Agent prompt: {len(old)} -> {len(new)} chars")
            patched = True

    if not patched:
        print("  AI Agent not found")
        sys.exit(1)

    cur.execute(
        "UPDATE workflow_entity SET nodes = %s::json, \"updatedAt\" = now() WHERE id = %s",
        (json.dumps(nodes), WORKFLOW_ID),
    )
    conn.commit()
    cur.close()
    conn.close()

    print("  syncing workflow_history...")
    r = subprocess.run(["python3", "/root/landtek/scripts/sync_workflow_history.py", WORKFLOW_ID],
                       capture_output=True, text=True)
    print("  " + r.stdout.strip())

    print("\n  restarting leo-tools to load new query_documents shape...")
    r = subprocess.run(["systemctl", "restart", "leo-tools"], capture_output=True, text=True)
    print(f"  systemctl restart leo-tools rc={r.returncode}")
    if r.stderr.strip():
        print(f"    stderr: {r.stderr.strip()[:200]}")

    print("\n  re-registering Telegram webhook (defensive)...")
    r = subprocess.run(["python3", "/root/landtek/scripts/sync_telegram_webhook.py"],
                       capture_output=True, text=True)
    print("  " + (r.stdout.split('\n')[-2] if r.stdout else ''))

    print("\n  smoke test...")
    r = subprocess.run(["python3", "/root/landtek/scripts/post_deploy_smoke.py"],
                       capture_output=True, text=True)
    print("  " + r.stdout.strip().replace("\n", "\n  "))


if __name__ == "__main__":
    main()
