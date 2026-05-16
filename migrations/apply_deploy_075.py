#!/usr/bin/env python3
"""Deploy 075 — Suppress duplicate Jonathan-reply on Rule C inquiries.

Today's incident transcript:
  Jonathan: "send message to Don QI ask him when he will be in Naga"
  Leo to Jonathan (telegram_summary_for_jonathan):
    "Jonathan asked me to find out from Don Qi Style (MWK-001, telegram_id
     8575986732) when he will be in Naga. Inquiry dispatched via back-channel..."
  Leo to Jonathan (telegram_reply_to_client):
    "Sending inquiry to Don Qi Style: 'Hi! Just checking in — when are you
     planning to be in Naga?...' I'll relay his response when he replies."
  Leo to Don Qi (target_message): the actual inquiry (correct — only once)

Jonathan got 2 confirmations; Don Qi got 1 inquiry. Bug: redundant
summary AND reply to Jonathan for the same operator command.

Fix: prompt-only change inside Rule C — when populating target_chat_id /
target_message, leave telegram_summary_for_jonathan as an empty string.
"""
import json
import os
import sys
import argparse
import time

sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

WF_NAME = "Leos Workflow"

# Inserted as a new bullet in Rule C's "Inviolable rules" section.
RULE_C_ADDITION = """
- **No duplicate summary on relay**: When `target_chat_id` and `target_message` are populated (you're relaying an inquiry to a client per Rule C), you MUST leave `telegram_summary_for_jonathan` as an empty string. The `telegram_reply_to_client` already conveys the action to Jonathan in first-person form ("Sending inquiry to <client>: ..."). A second third-person summary is redundant and creates duplicate messages in Jonathan's chat."""


def patch_prompt(node):
    prompt = node["parameters"]["options"]["systemMessage"]
    if "No duplicate summary on relay" in prompt:
        return False  # already patched
    # Insert into Rule C's "Inviolable rules" section, right after the
    # last existing bullet ("Truthfulness").
    marker = '- **Truthfulness**: If you cannot frame a relayed inquiry without inventing context, REFUSE and ask Jonathan to clarify.'
    if marker not in prompt:
        raise ValueError("Rule C 'Truthfulness' marker not found in prompt — manual review needed")
    new_prompt = prompt.replace(marker, marker + RULE_C_ADDITION)
    node["parameters"]["options"]["systemMessage"] = new_prompt
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
    snap = f"/root/landtek/snapshots/leos_workflow_pre_075_{args.target}_{ts}.json"
    os.makedirs("/root/landtek/snapshots", exist_ok=True)
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes, "connections": conns}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    aia = next((n for n in nodes if n["name"] == "AI Agent"), None)
    if not aia:
        sys.exit("FATAL: AI Agent node not found")
    changed = patch_prompt(aia)
    print(f"  ✓ AI Agent prompt {'patched (Rule C addition)' if changed else 'already up to date'}")

    cur.close(); conn.close()

    if args.target == "staging":
        # Staging: direct DB update + n8n REST API reload mirroring patch_workflow_dual
        import urllib.request
        api_key_env = next((line.split("=",1)[1].strip() for line in open("/root/landtek/.env") if line.startswith("N8N_API_KEY=")), None)
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute(
            'UPDATE workflow_entity SET nodes=%s::jsonb, "updatedAt"=now() WHERE id=%s',
            (json.dumps(nodes), wf_id))
        cur.execute("""UPDATE workflow_history SET nodes=%s::json
                         WHERE "workflowId"=%s
                           AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""",
                    (json.dumps(nodes), wf_id, wf_id))
        conn.commit(); cur.close(); conn.close()
        # Staging doesn't have an n8n REST API on port 5678 — it's on 5679.
        # And the API key is for prod's n8n. So we use the DB toggle here.
        # (Staging isn't user-facing; the brief outage doesn't matter.)
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute('UPDATE workflow_entity SET active=false, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); time.sleep(2)
        cur.execute('UPDATE workflow_entity SET active=true, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()
        print(f"  ✓ staging workflow updated + reactivated")
    else:
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes)


if __name__ == "__main__":
    main()
