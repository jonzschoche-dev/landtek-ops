#!/usr/bin/env python3
"""Deploy 078 — Operator competency overhaul (4 fixes + briefing format).

Incidents fixed (all from 2026-05-16 Manila morning Don Qi thread):

  (1) Self-inflicted noise from deploy_075:
      Leo follows new Rule G (leave telegram_summary_for_jonathan empty
      when populating target_chat_id for Rule C relays). Safe Reply node
      then backfills empty with the literal string "New message received
      and processed." -> Jonathan gets a noise DM for every Rule C command.
      FIX: gate "Reply to Jonathan" with an IF that skips when summary is
      empty/placeholder. Stop the noise entirely.

  (2) Hallucinated DB saves:
      Leo told Don Qi "jonzschoche@gmail.com is now on file" — but no
      workflow node writes the email_update field to clients.email. Lie.
      FIX: prompt — never claim "on file"/"saved"/"noted to DB" for
      anything that requires human verification. Use "flagged for Jonathan".

  (3) Hallucinated external sends:
      Leo committed: "I'll have the petition sent to that address" — but
      no Gmail-send node exists. Cannot actually send anything.
      FIX: prompt — Leo CANNOT send email/SMS. For such requests, create
      an action_item for Jonathan and tell client "Jonathan will follow up
      directly."

  (4) Redundant follow-ups despite deploy_077 Rule B fix:
      Client said "for my guardianship case over the estate of MWK" and
      Leo asked "could you share what the agenda is?" — agenda was just
      stated.
      FIX: prompt — before asking ANY follow-up, scan the current message
      for the answer. Explicit example added.

  (5) Briefing format upgrade (from Jonathan's "not very helpful" feedback):
      telegram_summary_for_jonathan should be operationally USEFUL:
        WHAT happened (1 line)
        WHAT JONATHAN NEEDS TO DO (bullets, or "no action needed")
        WHAT WAS CAPTURED (chat_note/event refs)
      Not narrative prose retelling the conversation.
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
POSTGRES_CRED = {"id": "kPUGFA1HrZZFWnzI", "name": "Postgres account 2"}

# ── (1) Safe Reply: stop the "New message received and processed." backfill ──
SAFE_REPLY_OLD = '\nconst safeJonathanSummary = (data.telegram_summary_for_jonathan &&\n                                                         data.telegram_summary_for_jonathan.trim() !== "")\n      ? sanitizeTelegramText(data.telegram_summary_for_jonathan)\n      : "New message received and processed.";'
SAFE_REPLY_NEW = '\n// Intentionally-empty summary (Rule G suppresses for Rule C relays) -> pass through empty.\n// Downstream IF "Has Summary For Jonathan" gates Reply to Jonathan when empty.\nconst safeJonathanSummary = (data.telegram_summary_for_jonathan &&\n                                                         data.telegram_summary_for_jonathan.trim() !== "")\n      ? sanitizeTelegramText(data.telegram_summary_for_jonathan)\n      : "";'

# ── New IF node "Has Summary For Jonathan" — gates Reply to Jonathan ────
def make_has_summary_node(base_pos):
    import uuid
    x, y = base_pos
    return {
        "id": str(uuid.uuid4()),
        "name": "Has Summary For Jonathan",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [x - 200, y],
        "parameters": {
            "options": {},
            "conditions": {
                "options": {
                    "version": 2,
                    "leftValue": "",
                    "caseSensitive": True,
                    "typeValidation": "loose",
                },
                "combinator": "and",
                "conditions": [
                    {
                        "id": str(uuid.uuid4()),
                        "operator": {
                            "type": "string",
                            "operation": "notEmpty",
                            "singleValue": True,
                        },
                        "leftValue": "={{ String($json.telegram_summary_for_jonathan || '').trim() }}",
                        "rightValue": "",
                    }
                ],
            },
        },
    }


# ── (2)(3)(4) Prompt additions to Rule E + Rule B ──────────────────────────
RULE_E_MARKER_BEFORE = "If a client could get advice from Leo, they wouldn't need Jonathan. They DO need Jonathan. Stay in your lane."

RULE_E_ADDITION = """

### Truthfulness about capabilities (added 2026-05-16)

You operate ONLY through the JSON output schema. You cannot do anything not listed there. In particular:

- **You CANNOT send email or SMS.** There is no Gmail-send or SMS node in your workflow. If a client asks you to email anything to them or to anyone else, your response MUST be:
  1. Reply: *"I'll flag this for Jonathan — he'll send it directly to <where>."*
  2. Emit `action_items: [{description: "Email <X> to <Y> at <addr>", due_date: today, priority: "High", case_file: <client's case_file>}]`
  3. Emit `chat_note_to_save` capturing the request verbatim.
  NEVER say "I'll have it sent", "I'll email it", "sending now", or any similar claim.

- **You CANNOT write directly to clients.email, clients.phone, etc.** The fields `email_update`, `phone_update`, `telegram_username_update` go to a Google Sheets review queue, NOT the live `clients` table. So:
  - WRONG: "Got it — <email> is now on file."
  - RIGHT: "Got it — I've flagged <email> for Jonathan to confirm and add to your contact record."

- **You CANNOT execute legal/strategic actions.** No filing, no sending letters, no scheduling court appearances. Defer to Jonathan via action_item.

- **General rule for claims**: only use "saved", "logged", "noted", "captured" for things that DO get written automatically by the workflow:
  - chat_notes (chat_note_to_save -> Insert Chat Note)
  - calendar events (calendar_event_to_save -> Insert Calendar Event)
  - action items (action_items[] -> Insert Action Items)
  - pending_inquiries (target_chat_id/message -> Send to Target Contact -> Log Pending Inquiry)
  For ANY other "save" claim, use "flagged for Jonathan's review" instead.

### Briefing format for telegram_summary_for_jonathan (added 2026-05-16)

When you DO populate `telegram_summary_for_jonathan` (i.e., NOT during Rule C relays), structure it as a SHORT operational brief, not a narrative retelling:

```
<one-line WHAT happened>

Action: <one line OR bullet list of what Jonathan needs to do, OR "none">
Captured: <one line listing chat_note / event / action_item IDs, OR "none">
```

Examples:

GOOD:
```
Don Qi requested petition + annex list emailed to jonzschoche@gmail.com (his guardianship case).

Action: Email DOC 623 (JONATHAN PETITION) + draft annex list to jonzschoche@gmail.com.
Captured: action_item, chat_note (communications).
```

BAD (narrative prose, no Action line):
```
Don Qi Style sent a message saying he wanted the petition emailed. He mentioned this is for the guardianship case over the estate of MWK. He provided an email address. I have flagged this for processing.
```

Keep it ≤ 4 lines total. Front-load the action."""

# ── Rule B addition — read current message before follow-ups ───────────
RULE_B_FOLLOWUP_MARKER = "**Max ONE follow-up question per turn.**"

RULE_B_FOLLOWUP_OLD_TAIL = "Pick ONE most useful clarifying question per turn, or none if the answer is already actionable."

RULE_B_FOLLOWUP_NEW_TAIL = """Pick ONE most useful clarifying question per turn, or none if the answer is already actionable.

**Before asking any follow-up, scan the client's current message for the answer.** Don't ask about information they just provided. Examples of failures to avoid:

WRONG:
  Client: "this is for my guardianship case over the estate of MWK"
  Leo:    "could you share what the agenda is?"
  (Agenda was just stated as guardianship.)

WRONG:
  Client: "tentative meeting end of next week with my lawyer"
  Leo:    "do you have a specific date in mind?"
  (Tentative + end of next week is the answer.)

RIGHT:
  Client: "this is for my guardianship case over the estate of MWK"
  Leo:    "Got it — for the guardianship matter. I've flagged for Jonathan to handle. [no follow-up — sufficient info]" """


def patch_safe_reply(node):
    js = node["parameters"]["jsCode"]
    if SAFE_REPLY_OLD not in js:
        if "Intentionally-empty summary" in js:
            return False
        raise ValueError("Safe Reply: SAFE_REPLY_OLD marker not found")
    node["parameters"]["jsCode"] = js.replace(SAFE_REPLY_OLD, SAFE_REPLY_NEW)
    return True


def patch_ai_agent(node):
    p = node["parameters"]["options"]["systemMessage"]
    changed = False
    if "Truthfulness about capabilities" not in p:
        if RULE_E_MARKER_BEFORE not in p:
            raise ValueError("Rule E marker missing")
        p = p.replace(RULE_E_MARKER_BEFORE, RULE_E_MARKER_BEFORE + RULE_E_ADDITION)
        changed = True
    if "**Before asking any follow-up, scan the client's current message" not in p:
        if RULE_B_FOLLOWUP_OLD_TAIL in p:
            p = p.replace(RULE_B_FOLLOWUP_OLD_TAIL, RULE_B_FOLLOWUP_NEW_TAIL)
            changed = True
        else:
            print("  ⚠ Rule B tail marker not found — Rule B scan-current-message addition skipped")
    node["parameters"]["options"]["systemMessage"] = p
    return changed


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
    snap = f"/root/landtek/snapshots/leos_workflow_pre_078_{args.target}_{ts}.json"
    os.makedirs("/root/landtek/snapshots", exist_ok=True)
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes, "connections": conns}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    sr = next((n for n in nodes if n["name"] == "Safe Reply"), None)
    if sr and patch_safe_reply(sr):
        print("  ✓ Safe Reply: 'New message received' default replaced with empty string")
    else:
        print("  ⚠ Safe Reply: already patched or marker missing")

    aia = next((n for n in nodes if n["name"] == "AI Agent"), None)
    if aia and patch_ai_agent(aia):
        print("  ✓ AI Agent prompt: Rule E (capabilities) + Rule B (scan current) + briefing format")
    else:
        print("  ⚠ AI Agent prompt: already patched")

    # Add Has Summary For Jonathan IF node + rewire Reply to Jonathan
    rtj = next((n for n in nodes if n["name"] == "Reply to Jonathan"), None)
    if not rtj:
        sys.exit("FATAL: Reply to Jonathan node not found")
    if not any(n["name"] == "Has Summary For Jonathan" for n in nodes):
        new = make_has_summary_node(rtj.get("position", [0, 0]))
        nodes.append(new)
        print("  ✓ Added IF 'Has Summary For Jonathan'")
    else:
        print("  ⚠ 'Has Summary For Jonathan' already exists")

    # Rewire: Safe Reply -> [Reply to Client, Has Summary For Jonathan (was Reply to Jonathan), If]
    # And: Has Summary For Jonathan (true) -> Reply to Jonathan
    sr_main = conns.get("Safe Reply", {}).get("main", [[]])
    for t in sr_main[0]:
        if t.get("node") == "Reply to Jonathan":
            t["node"] = "Has Summary For Jonathan"
    if not any(t.get("node") == "Has Summary For Jonathan" for t in sr_main[0]):
        sr_main[0].append({"node": "Has Summary For Jonathan", "type": "main", "index": 0})
    conns["Safe Reply"] = {"main": sr_main}

    conns["Has Summary For Jonathan"] = {
        "main": [
            [{"node": "Reply to Jonathan", "type": "main", "index": 0}],  # true: send to Jonathan
            [],  # false: skip
        ]
    }
    print("  ✓ Rewired: Safe Reply -> Has Summary For Jonathan -> Reply to Jonathan (gated)")

    # Also: the 'Create New Client Row' branch feeds Reply to Jonathan with a fixed
    # message — leave that intact (genuine new-client alert should always send).

    cur.close(); conn.close()

    if args.target == "staging":
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute(
            'UPDATE workflow_entity SET nodes=%s::jsonb, connections=%s::jsonb, "updatedAt"=now() WHERE id=%s',
            (json.dumps(nodes), json.dumps(conns), wf_id))
        cur.execute("""UPDATE workflow_history SET nodes=%s::json, connections=%s::json
                         WHERE "workflowId"=%s
                           AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""",
                    (json.dumps(nodes), json.dumps(conns), wf_id, wf_id))
        cur.execute('UPDATE workflow_entity SET active=false, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); time.sleep(2)
        cur.execute('UPDATE workflow_entity SET active=true, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()
        print("  ✓ staging workflow updated + reactivated")
    else:
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes, connections=conns)


if __name__ == "__main__":
    main()
