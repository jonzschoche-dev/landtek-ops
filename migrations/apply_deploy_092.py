#!/usr/bin/env python3
"""Deploy 092 — Telegram cadence overhaul: icons, dedupe, throttle.

Goals:
  1. Suppress duplicate DMs on file upload. Combine telegram_summary_for_jonathan
     + Notify File Location into ONE message (the file notification, augmented
     with the AI's summary text).
  2. Add intent icons to every Leo->Jonathan summary: 👤 client activity,
     📋 system log, ❓ needs answer, 🚨 alert, 📊 stats.
  3. Throttle educate_leo from 25+ DMs to 4-5 (separate file edit).

Changes:
  - Notify File Location text template: extends to include the AI's summary
  - Has Summary For Jonathan IF: also skips when hasFile=true (since file
    notification now carries the summary)
  - AI Agent prompt: icon prefix rule added to briefing format
"""
import json, os, sys, argparse, time
sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

WF_NAME = "Leos Workflow"

# Combined file notification: includes the AI's summary text, structured
# as a single Telegram DM. Uses n8n template literal expression.
_FOLDER = "\U0001F4C1"  # 📁
NEW_FILE_LOC_TEXT = (
    "={{ `" + _FOLDER + " <b>${$('Log File Receipt1').first().json.original_filename || 'unnamed'}</b> from ${$('Telegram Trigger').first().json.message.from.first_name}\n\n"
    "DOC ${$('Log File Receipt1').first().json.id} · ${$('Log File Receipt1').first().json.case_file || 'unclassified'}\n"
    "Local: <code>${$('Log File Receipt1').first().json.file_path || '(not yet captured)'}</code>\n"
    "Drive: ${$('Log File Receipt1').first().json.drive_link || '(not in Drive yet)'}\n"
    "Dashboard: https://leo.hayuma.org/files/${$('Log File Receipt1').first().json.id}\n\n"
    "${$('Parse Agent1').first().json.telegram_summary_for_jonathan || '(no summary)'}` }}"
)

# IF condition update: skip Reply to Jonathan when hasFile (file path will send the combined notif)
IF_CONDITIONS_OLD_LEFT = "={{ String($json.telegram_summary_for_jonathan || '').trim() }}"
# We'll add a second condition to the same IF that requires hasFile != true

# Prompt: icon prefix rule for telegram_summary_for_jonathan
PROMPT_ANCHOR = "### Briefing format for telegram_summary_for_jonathan (added 2026-05-16)"

ICON_RULE = """### Icon prefix for telegram_summary_for_jonathan (added 2026-05-16 — deploy_092)

EVERY telegram_summary_for_jonathan MUST begin with ONE of these single-character icons + space:

  👤  Client activity — a client messaged/uploaded; informational, low-priority
  📋  System log — action_item created, doc auto-classified, routine state change
  ❓  Needs answer — you have a specific question Jonathan must answer
  🚨  Alert / issue — something is broken, suspicious, or needs intervention
  📊  Stats / report — daily digest, case briefing, multi-doc synthesis

This lets Jonathan scan his Telegram with eye-flick priority. Examples:

WRONG (no icon): "Don Qi uploaded a petition. Action: review and respond..."
RIGHT: "👤 Don Qi uploaded petition (DOC 689). No action urgently needed.

WRONG: "Workflow patched, classification corrected."
RIGHT: "📋 Workflow patched: DOC 687 reclassified MWK-001 via keyword vote.

For Rule C inquiry-to-relay: leave telegram_summary_for_jonathan empty (Rule G); the file notification or reply already covers the action confirmation.

"""


def patch_prompt(node):
    p = node["parameters"]["options"]["systemMessage"]
    if "Icon prefix for telegram_summary_for_jonathan (added 2026-05-16 — deploy_092)" in p:
        return False
    if PROMPT_ANCHOR not in p:
        raise ValueError("briefing format anchor not found")
    p = p.replace(PROMPT_ANCHOR, ICON_RULE + "\n" + PROMPT_ANCHOR)
    node["parameters"]["options"]["systemMessage"] = p
    return True


def patch_file_notification(nodes):
    n = next((x for x in nodes if x["name"] == "Notify File Location"), None)
    if not n:
        return False
    if "telegram_summary_for_jonathan" in n["parameters"].get("text", ""):
        return False  # already combined
    n["parameters"]["text"] = NEW_FILE_LOC_TEXT
    return True


def patch_summary_if(nodes):
    """Add a second AND condition to Has Summary For Jonathan: hasFile must be false."""
    n = next((x for x in nodes if x["name"] == "Has Summary For Jonathan"), None)
    if not n:
        return False
    conds = n["parameters"]["conditions"]["conditions"]
    if any("hasFile" in c.get("leftValue", "") for c in conds):
        return False  # already added
    import uuid
    conds.append({
        "id": str(uuid.uuid4()),
        "operator": {"type": "boolean", "operation": "false", "singleValue": True},
        "leftValue": "={{ Boolean($json.hasFile) }}",
        "rightValue": "",
    })
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["staging", "prod"], required=True)
    args = ap.parse_args()
    DSN = (dict(host="172.18.0.3", port=5432, dbname="n8n", user="n8n", password="n8npassword")
           if args.target == "prod"
           else dict(host="127.0.0.1", port=5433, dbname="n8n", user="n8n", password="n8npassword"))

    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb FROM workflow_entity WHERE name=%s", (WF_NAME,))
    wf_id, nodes = cur.fetchone()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_092_{args.target}_{ts}.json"
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    aia = next((n for n in nodes if n["name"] == "AI Agent"), None)
    if aia and patch_prompt(aia):
        print("  ✓ AI Agent prompt: icon prefix rule added")
    else:
        print("  ⚠ prompt already patched or anchor missing")

    if patch_file_notification(nodes):
        print("  ✓ Notify File Location: combined with summary text")
    else:
        print("  ⚠ Notify File Location already combined or missing")

    if patch_summary_if(nodes):
        print("  ✓ Has Summary For Jonathan: now skips when hasFile=true (no dupe)")
    else:
        print("  ⚠ Has Summary For Jonathan already patched or missing")

    cur.close(); conn.close()

    if args.target == "prod":
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes)
    else:
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute('UPDATE workflow_entity SET nodes=%s::jsonb, "updatedAt"=now() WHERE id=%s', (json.dumps(nodes), wf_id))
        cur.execute("""UPDATE workflow_history SET nodes=%s::json WHERE "workflowId"=%s AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""", (json.dumps(nodes), wf_id, wf_id))
        cur.execute('UPDATE workflow_entity SET active=false WHERE id=%s', (wf_id,))
        conn.commit(); time.sleep(2)
        cur.execute('UPDATE workflow_entity SET active=true WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()
        print("  ✓ staging done")


if __name__ == "__main__":
    main()
