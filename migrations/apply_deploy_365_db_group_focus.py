#!/usr/bin/env python3
"""apply_deploy_365_db_group_focus.py — give Leo a focus rule for the DB group.

The DB group (chat_id -5138695222) is the three-way vault coordination
channel: Jonathan + Kristyle + Leo. Today Leo doesn't know that.

Observed defect (exec 2254, 2026-06-07): Kristyle was not online; Jonathan
sent "ok" as a group acknowledgment after the system test message. Leo's
AI Agent treated it as a private command to Jonathan and generated a 600+
char P0 priority briefing — fraud exhibits, evidence gaps, upcoming
deadlines. That's the wrong tone and the wrong scope for a vault
coordination group.

This migration appends Rule M.1 — DB Group Focus — to the AI Agent
systemMessage. It pins behavior when the inbound chat_id matches the
DB group:

  - Focus is filing operations + vault coordination
  - Replies are short and warm, not strategic
  - Vault tools (Rule M) take precedence over briefing tools
  - Acknowledgments like "ok", "thanks", "got it" get one short conversational
    response, not a status dump
  - Long strategic briefings stay in Jonathan's private chat, not the group
  - When Kristyle vaults something, Leo confirms in the group (one line)
    so Jonathan sees the audit trail in real time

Idempotent: matches the rule block by delimiter.
"""
from __future__ import annotations
import json
import os
import sys
from copy import deepcopy

import psycopg2

PG_DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"

RULE_START = "## Rule M.1 — DB Group Focus (deploy_365)"
RULE_END = "## END Rule M.1"

RULE = f"""{RULE_START}

The DB group has chat_id **-5138695222**. Title: "DB". Members:
  - Jonathan (telegram_user_id 6513067717) — operator
  - Joy Kristyle Cerdon (telegram_user_id 5992075757) — filing assistant
  - LeoLandTekBot — you

This group exists for ONE thing: **vault coordination + physical filing
operations.** Treat it as an active work channel between a manager, a
filing clerk, and yourself. NOT as a place for strategic briefings, case
theory analysis, opposing-counsel prediction, or P0 priority dumps.

### When a message arrives from chat_id = -5138695222

1. **Tone:** brief, warm, conversational. Like talking across a desk.
2. **First instinct:** call a vault tool (Rule M). Filing-related verbs
   ("just vaulted X", "label this Y", "what's pending", "where's Z",
   "what does ARTA-1210 need") map to vault_register / vault_find /
   vault_queue / vault_missing / vault_last / vault_attach_scan.
3. **Acknowledgments ("ok", "thanks", "got it", "sounds good"):** ONE
   short conversational reply at most. Often the right reply is silence
   plus an insert_chat_note. Do NOT generate a status dump.
4. **Strategic / case-theory questions in the group:** redirect cleanly —
   "That one's worth pulling Jonathan in directly. Want me to drop a note?"
   Keep strategy out of Kristyle's working channel.
5. **Confirmations from successful vault writes:** ONE line into the group
   so Jonathan sees the audit trail. Example:
       "Logged AFF-001 — Patricia's affidavit of loss, for the 4497 case."
6. **Errors back to Kristyle:** translate to plain language (Rule M
   already specifies — locator_taken, unknown_matter, etc.). Don't relay
   JSON or error codes.
7. **No telegram_summary_for_jonathan when the trigger is the group**
   — he already sees the group reply. Sending him a separate private
   notify creates double-tap and burns his pacing budget.

### What stays in Jonathan's private chat (chat_id 6513067717)

- Strategy / settlement / case theory
- Long briefings, P0 priorities, deadline rollups
- Anything Kristyle should not see (privileged + counsel comms)

If Jonathan asks you a strategy question IN the group, ask him gently to
move it to direct chat: "Want me to break that down in our private
thread? Don't want to fill the filing channel with strategy."

### Read Kristyle generously

She types fast on her phone, in mixed English/Tagalog, sometimes with
typos. "I just put Pat's affidavit in the vault, AFF-1, for the 4497
case" is a vault_register call, NOT a clarification opportunity. Default
to optimistic interpretation per Rule M's matter-code shortcuts.

{RULE_END}
"""


def main():
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT nodes, connections FROM workflow_entity WHERE id = %s",
                (WORKFLOW_ID,))
    row = cur.fetchone()
    if not row:
        print("FATAL: workflow not found", file=sys.stderr)
        sys.exit(2)
    nodes_raw, conns_raw = row
    nodes = json.loads(nodes_raw) if isinstance(nodes_raw, str) else nodes_raw
    nodes = deepcopy(nodes)
    conns_json = (conns_raw if isinstance(conns_raw, str) else json.dumps(conns_raw))

    cur.execute("""
        INSERT INTO leo_workflow_snapshots
            (workflow_id, reason, nodes_json, connections_json)
        VALUES (%s, %s, %s, %s) RETURNING id
    """, (WORKFLOW_ID, "pre-deploy_365 DB group focus",
          json.dumps(nodes), conns_json))
    snap_id = cur.fetchone()[0]
    print(f"snapshot id: {snap_id}")

    agent_idx = next((i for i, n in enumerate(nodes)
                      if n.get("type") == "@n8n/n8n-nodes-langchain.agent"), None)
    if agent_idx is None:
        print("FATAL: AI Agent not found", file=sys.stderr); sys.exit(3)

    sm = nodes[agent_idx]["parameters"]["options"]["systemMessage"]
    if RULE_START in sm and RULE_END in sm:
        s = sm.index(RULE_START)
        e = sm.index(RULE_END) + len(RULE_END)
        new_sm = sm[:s] + RULE.strip() + sm[e:]
        action = "replaced"
    else:
        new_sm = sm.rstrip() + "\n\n" + RULE.strip() + "\n"
        action = "appended"
    nodes[agent_idx]["parameters"]["options"]["systemMessage"] = new_sm
    delta = len(new_sm) - len(sm)
    print(f"Rule M.1 {action}  delta={delta:+d}  total={len(new_sm)}")

    cur.execute("""
        UPDATE workflow_entity SET nodes = %s, "updatedAt" = NOW() WHERE id = %s
    """, (json.dumps(nodes), WORKFLOW_ID))

    cur.close(); conn.close()
    print(f"DONE — snapshot {snap_id}")


if __name__ == "__main__":
    main()
