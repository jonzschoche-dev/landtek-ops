#!/usr/bin/env python3
"""Deploy 037 — Back-Channel Operator Mode.

1. Append Rule C to AI Agent systemMessage:
   - When isJonathan===true, Jonathan's messages are operator commands
   - Three command types: question / instruction / inquiry-to-relay
   - Inquiry-to-relay populates target_chat_id + target_message
   - target_message never mentions Jonathan; scoped to target client's matters
   - When isJonathan===false, target_* fields must be empty (security rule)
   - Embed live client directory for resolution

2. Patch Has Target Contact IF — add AND isJonathan===true condition.
   Blocks any non-Jonathan sender from triggering relay, even if their
   captured Parse Agent1 output somehow contains target_message.

Snapshot saved at /root/landtek/snapshots/leos_workflow_pre_037_*.json
"""
import json
import psycopg2

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")

# Anchor at the end of the live prompt (after the Jonathan-leakage clause from deploy 036)
ANCHOR_TAIL = "communications, deadlines, or activities on unrelated matters."

RULE_C = """

---

## BACK-CHANNEL OPERATOR MODE (Rule C — Jonathan only)

This rule applies ONLY when the current sender is Jonathan (`isJonathan === true`, telegram_id `6513067717`). When ANY other sender is talking to you, this entire rule is INERT and you MUST leave `target_chat_id` and `target_message` empty/null in your JSON output. Generating these fields as a non-Jonathan sender is a security violation that will be blocked downstream but must also never be attempted in the first place.

### When Jonathan messages you

Treat his messages as operator commands. Identify the intent:

1. **Question to Leo** — Jonathan asks you something (e.g. "Who are the registered owners of T-4497?"). Answer privately in `telegram_reply_to_client` (which Telegram routes to Jonathan since he is the active client). Do not populate `target_*`.

2. **Instruction to Leo** — Jonathan tells you to do something (update intelligence, schedule, journal, generate a report, etc.). Perform the action, then confirm in `telegram_reply_to_client`. Do not populate `target_*` unless the instruction is an inquiry-to-relay (next).

3. **Inquiry-to-relay** — Jonathan asks you to find out something from a specific client. Examples:
   > "Ask Datu Shishir when the mining contract was signed."
   > "Find out from Don Qi Style which lots are included in the SPA."
   > "Get confirmation from Allan V. Inocalla on the June 30 hearing attendance."

   When you detect this intent, you MUST:
   - Identify the target client (by name, nickname, company, case_file, or telegram username).
   - Resolve the target's `telegram_id` from the directory below.
   - Compose a NATURAL inquiry message addressed directly to that client.
   - **Never mention Jonathan or that he requested the inquiry.** The message must come across as your own natural follow-up, framed within that client's known matters only.
   - Populate `target_chat_id` (numeric telegram_id of the target) and `target_message` (your inquiry text).
   - Set `telegram_reply_to_client` to a private confirmation to Jonathan, of the form:
     > "Sending inquiry to <client name>: <quoted message text>. I'll relay his response when he replies."
   - Apply Rule B's investigative discipline to your inquiry — clarity-focused, scoped, polite.

### Client directory (authoritative for back-channel resolution)

| Identifier | Telegram ID | Notes |
|---|---|---|
| Jonathan Zschoche / Owner | `6513067717` | OPERATOR — never a relay target |
| Heirs of MWK / Don Qi Style / MWK-001 | `8575986732` | Reachable via back-channel |
| Allan V. Inocalla / Datu Shishir / Paracale-001 | (not yet recorded) | Cannot be reached via back-channel until his telegram_id is recorded in the clients table |

If a target client's telegram_id is not in the directory, REFUSE the inquiry in `telegram_reply_to_client` and ask Jonathan to provide the ID. Do not guess.

### Inviolable rules

- **Authorization**: `target_chat_id` and `target_message` may ONLY be populated when `isJonathan === true`. Never when a client is the sender. There is also a downstream IF gate that blocks non-Jonathan relay attempts, but you must not try them.
- **Isolation**: `target_message` must be scoped to the target client's known matters only. Never reference Jonathan, his strategy, another client's affairs, or cross-client information.
- **Source attribution**: `target_message` must NEVER contain phrases like "Jonathan asked me to find out", "the operator wants to know", or any attribution that exposes the back-channel. Frame the question as your own.
- **Truthfulness**: If you cannot frame a relayed inquiry without inventing context, REFUSE and ask Jonathan to clarify.
"""


def main():
    conn = psycopg2.connect(**DSN)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("SELECT id, nodes::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes = cur.fetchone()

    rule_c_added = False
    if_patched = False

    for n in nodes:
        # 1. Append Rule C to AI Agent systemMessage
        if n.get("name") == "AI Agent":
            sm = n["parameters"].get("options", {}).get("systemMessage", "")
            if "BACK-CHANNEL OPERATOR MODE" in sm:
                print(" - AI Agent: Rule C already present, skipping append")
            elif ANCHOR_TAIL not in sm:
                print(f"WARN: Rule C anchor not found — appending to end instead")
                n["parameters"].setdefault("options", {})["systemMessage"] = sm + RULE_C
                rule_c_added = True
            else:
                cut = sm.rindex(ANCHOR_TAIL) + len(ANCHOR_TAIL)
                new_sm = sm[:cut] + RULE_C + sm[cut:]
                n["parameters"].setdefault("options", {})["systemMessage"] = new_sm
                rule_c_added = True
                print(f" - AI Agent: Rule C appended ({len(sm)} -> {len(new_sm)} chars, delta {len(new_sm) - len(sm):+d})")

        # 2. Patch Has Target Contact IF — add isJonathan check
        if n.get("name") == "Has Target Contact":
            conds = n["parameters"].get("conditions", {}).get("conditions", [])
            has_jonathan_check = any(
                isinstance(c.get("leftValue"), str)
                and "isJonathan" in c.get("leftValue", "")
                for c in conds
            )
            if has_jonathan_check:
                print(" - Has Target Contact: isJonathan condition already present, skipping")
            else:
                conds.append({
                    "id": "auth-gate-isjonathan-only",
                    "operator": {
                        "type": "boolean",
                        "operation": "true",
                        "singleValue": True,
                    },
                    "leftValue": "={{ $('Context Builder').first().json.isJonathan }}",
                    "rightValue": "",
                })
                n["parameters"]["conditions"]["conditions"] = conds
                # Make sure combinator is AND (it already is per inspection)
                n["parameters"]["conditions"]["combinator"] = "and"
                if_patched = True
                print(" - Has Target Contact: AND isJonathan===true condition added")

    if not (rule_c_added or if_patched):
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
