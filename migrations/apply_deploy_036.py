#!/usr/bin/env python3
"""Deploy 036 — add explicit Jonathan-leakage prohibition to the live Client
Isolation clause.

The live clause says: "Never expose one client's information to another."
This implicitly covers Jonathan (clients.client_code='Owner') but doesn't name
him. The LLM is more likely to misread implicit protection than a named one.

Patch: append a sentence right after the existing line so the prohibition is
unmissable.

Snapshot saved at /root/landtek/snapshots/leos_workflow_pre_036_*.json
"""
import json
import psycopg2

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")

ANCHOR = "Never expose one client's information to another."
APPENDED = (
    " Never assume or leak information from Jonathan's matters or any other "
    "client to the talking client — including his strategy, instructions, "
    "communications, deadlines, or activities on unrelated matters."
)


def main():
    conn = psycopg2.connect(**DSN)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("SELECT id, nodes::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes = cur.fetchone()

    changed = False
    for n in nodes:
        if n.get("name") != "AI Agent":
            continue
        sm = n["parameters"].get("options", {}).get("systemMessage", "")

        if ANCHOR not in sm:
            print("ERROR: anchor sentence not found in live systemMessage")
            return

        # Idempotency: skip if already appended
        if "Never assume or leak information from Jonathan's matters" in sm:
            print(" - AI Agent: explicit Jonathan-leakage clause already present, skipping")
            return

        new_sm = sm.replace(ANCHOR, ANCHOR + APPENDED, 1)
        n["parameters"].setdefault("options", {})["systemMessage"] = new_sm
        print(f" - AI Agent: Jonathan-leakage clause appended ({len(sm)} -> {len(new_sm)} chars, delta {len(new_sm) - len(sm):+d})")
        changed = True

    if not changed:
        print("No changes applied.")
        return

    cur.execute("""
        UPDATE workflow_entity SET nodes=%s::jsonb, "updatedAt"=now() WHERE id=%s
    """, (json.dumps(nodes), wf_id))
    conn.commit()
    print(f"\nworkflow_entity row updated (id={wf_id})")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
