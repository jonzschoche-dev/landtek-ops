#!/usr/bin/env python3
"""Deploy 089 — Fix new_contact_detected false-positive.

Incident from same 2026-05-16 10:15 thread:
  Don Qi (id 9, telegram_id 8575986732, case_file MWK-001) uploads a file.
  Leo's brief to Jonathan: "New contact detected; no existing client profile."
  -> WRONG. Don Qi IS in clients table and clientRow is populated.

Root cause: AUTHORITY rule says "If a never-seen sender messages, set
new_contact_detected:true". The phrase "never-seen" is too loose — AI
sometimes interprets generic file-uploads with no caption as "no profile".

Fix: prompt — explicit predicate.
  new_contact_detected = true   ONLY IF clientRow.id is empty/null
                                AND clientProfile starts with "No matching client profile found"
                                AND the sender's telegram_id doesn't match any known authorized_users row.
"""
import json, os, sys, argparse, time
sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

WF_NAME = "Leos Workflow"

AUTH_MARKER = "# AUTHORITY\n\nYou answer to Jonathan Zschoche (the principal). Other senders are CLIENTS — you serve them in a journaling role (capture every event/note from them) but only Jonathan can authorize structural changes. If a never-seen sender messages, set new_contact_detected:true AND still emit a chat_note_to_save capturing their message verbatim with topic='communications' and importance=3."

AUTH_NEW = """# AUTHORITY

You answer to Jonathan Zschoche (the principal). Other senders are CLIENTS — you serve them in a journaling role (capture every event/note from them) but only Jonathan can authorize structural changes.

**new_contact_detected — strict predicate (added 2026-05-16 — deploy_089)**:

Set `new_contact_detected: true` ONLY when ALL of these conditions hold:
  - `$json.clientRow` is null OR `$json.clientRow.id` is empty/missing, AND
  - `CLIENT PROFILE` block in your input starts with "No matching client profile found.", AND
  - The sender is not Jonathan (`$json.isJonathan === false`)

In ALL other cases — including when `clientRow.id` is present (e.g., Don Qi at telegram_id 8575986732 IS a known MWK-001 client) — set `new_contact_detected: false`.

Examples:
  ✗ WRONG: Don Qi uploads a file with no caption. Leo says "New contact detected; no existing client profile." Don Qi has been a client since 2026-05-09 with case_file MWK-001 — clientRow.id = 9 — so this is FALSE.
  ✓ RIGHT: A telegram_id with no matching clients row sends "hello". clientRow is null. Now `new_contact_detected: true`.

Still emit `chat_note_to_save` for every substantive client message regardless of whether they're new — that part of the original rule stands."""


def patch_prompt(node):
    p = node["parameters"]["options"]["systemMessage"]
    if "new_contact_detected — strict predicate" in p:
        return False
    if AUTH_MARKER not in p:
        raise ValueError("AUTHORITY marker not found")
    p = p.replace(AUTH_MARKER, AUTH_NEW)
    node["parameters"]["options"]["systemMessage"] = p
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["staging", "prod"], required=True)
    args = parser.parse_args()
    DSN = (dict(host="127.0.0.1", port=5433, dbname="n8n", user="n8n", password="n8npassword")
           if args.target == "staging"
           else dict(host="172.18.0.3", port=5432, dbname="n8n", user="n8n", password="n8npassword"))

    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb FROM workflow_entity WHERE name=%s", (WF_NAME,))
    wf_id, nodes = cur.fetchone()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_089_{args.target}_{ts}.json"
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    aia = next((n for n in nodes if n["name"] == "AI Agent"), None)
    if aia and patch_prompt(aia):
        print("  ✓ AI Agent prompt: AUTHORITY rule clarified")
    else:
        print("  ⚠ Already patched or marker missing")

    cur.close(); conn.close()
    if args.target == "staging":
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute('UPDATE workflow_entity SET nodes=%s::jsonb, "updatedAt"=now() WHERE id=%s', (json.dumps(nodes), wf_id))
        cur.execute("""UPDATE workflow_history SET nodes=%s::json
                         WHERE "workflowId"=%s AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""",
                    (json.dumps(nodes), wf_id, wf_id))
        cur.execute('UPDATE workflow_entity SET active=false, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); time.sleep(2)
        cur.execute('UPDATE workflow_entity SET active=true, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()
        print("  ✓ staging done")
    else:
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes)


if __name__ == "__main__":
    main()
