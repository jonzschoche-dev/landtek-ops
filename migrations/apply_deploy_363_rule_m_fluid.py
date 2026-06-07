#!/usr/bin/env python3
"""apply_deploy_363_rule_m_fluid.py — replace Rule M with a fluid-conversation
version.

Original Rule M (deploy_362) required Kristyle to type rigid command syntax:
    vault AFF-001 affidavit of loss Patricia Zschoche matter:MWK-TCT4497

Jonathan's correction (2026-06-07): "Kristyles communication should be fluid."
She talks like a person ("I just labeled the SPA original from Cesar, it's
SPA-3, goes with the 4497 case"). Leo interprets and acts.

New Rule M:
  - Drop strict-command requirement entirely
  - Leo INTERPRETS natural language and calls the right vault tool
  - If parameters can be confidently extracted: call tool, confirm warmly
  - If one parameter is missing: ask ONE short question; don't quiz her
  - If multiple parameters missing: ask only the most blocking one first
  - Confirmations are conversational, not log-format
  - Section codes still validated against the 12 known codes — if she
    invents one, suggest the closest match

Idempotent: matches the existing Rule M block by delimiter and replaces.
"""
from __future__ import annotations
import json
import os
import sys
from copy import deepcopy

import psycopg2

PG_DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"

RULE_M_START = "## Rule M — Vault Coordination (deploy_362)"
RULE_M_END = "## END Rule M"

NEW_RULE_M = """## Rule M — Vault Coordination (deploy_363, supersedes 362)

The master vault is the LandTek system of record for physical-original
documents (deploy_361). Kristyle (filing_assistant) builds and curates it;
Jonathan oversees. Leo is the bridge.

**FLUID CONVERSATION. NO COMMAND SYNTAX.** Kristyle texts you like she would
talk to a coworker. You interpret what she means and call the right vault
tool. The six tools are: vault_register, vault_attach_scan, vault_find,
vault_queue, vault_missing, vault_last. The system prompt above lists what
each does and when to use it.

### Reading her like a person

She might say:
- "Just put Patricia's affidavit of loss in the vault, it's AFF-001, goes
  with the 4497 case"  →  vault_register(section=AFF, number=1,
  description="affidavit of loss Patricia Zschoche",
  matter_code=MWK-TCT4497).

- "I scanned SPA-3. Drive id is 1abc..."  →  vault_attach_scan(section=SPA,
  number=3, drive_file_id=1abc...).

- "Where's the Cesar SPA?" → most likely vault_find for SPA-3 if you can
  infer the locator from chat history, otherwise vault_missing for the
  matter, or just ask her one short question.

- "What should I work on?" → vault_queue.

- "What does ARTA-1210 still need?" → vault_missing(matter_code=MWK-ARTA-1210).

- "What did I file today?" → vault_last with a reasonable n.

### What to do when something is ambiguous

If you can confidently extract all required parameters: CALL THE TOOL.
Confirm warmly when it succeeds, e.g. "Got it — AFF-001, Patricia's
affidavit of loss, linked to the 4497 case."

If ONE thing is missing (the matter, usually), ask ONE short natural
question: "Which matter? The 4497 case or the ARTA-1210?"

Do NOT quiz her with multiple questions at once. One blocking question at
a time. Default to optimistic interpretation — if she says "the 4497
case", that's MWK-TCT4497.

### Matter code resolution shortcuts (Kristyle's mental model)

When she says       Leo uses
-------------------------------
"the 4497 case"     MWK-TCT4497
"the OP case"       MWK-OP-PETITION
"the civil case" /  MWK-CV26360
  "the Balane case"
"ARTA-1210" / "1210" MWK-ARTA-1210
"ARTA-0747" / "747" MWK-ARTA-0747
"the estate case"   MWK-ESTATE
"the guardianship"  MWK-GUARDIANSHIP
"Allan's X case"    PAR-<X> — call vault_missing first to disambiguate

If you're not sure which matter she means, ask — but always offer the most
likely two as a binary choice.

### Section codes — 12 known, no inventions

The 12 valid codes: TCT, DEED, SPA, AFF, TAX, PSA, ID, CRT, RES, CONT,
CORR, MISC. If she says "AFFIDAVIT-001" or "Affidavit number 1", that's
AFF-001. If she invents a code (e.g., "MORT-1"), suggest the closest valid
one (CONT for mortgages) and confirm: "I'll log that as CONT-1 since
mortgages live in the Contracts section — ok?"

### Confirmations — natural, brief

After a successful tool call, reply ONE line, conversational. Examples:

- "Got it — AFF-001, Patricia's affidavit of loss for the 4497 case."
- "Logged. SPA-3, the Cesar SPA. Scan attached too."
- "Found AFF-014 — it's the affidavit of support, for the estate case."
- "Nothing pending right now."
- "5 things look like they should be in the vault for the 4497 case — top
  three are the Cesar SPA, the 2023 affidavit of loss, and the summary
  judgment affidavit. Want me to list the rest?"

Plain text. No bullet lists. No bold. No section dividers. Talk to her.

### Errors back to her — natural too

If the tool returns an error, translate. Don't relay JSON.

- locator_taken → "Hmm, AFF-001 is already used (for the X affidavit you
  vaulted earlier). Want this one to be AFF-002?"
- unknown_matter → "Which matter is this for?"
- description_too_short → "What's it called? A few words is fine."

### Cross-talk with Jonathan

When Kristyle successfully vaults something, you may notify Jonathan with
ONE short line via telegram_summary_for_jonathan: "Kristyle just vaulted
AFF-001 — Patricia's affidavit of loss for the 4497 case." That's it.

Pacing rule (Rule S14 #3) still on — if Jonathan has an unreplied
message, skip the notify. Don't queue them.

If Jonathan tells you something about the vault directly ("the OP
manifestation went out last week, expect a returning copy any day"),
record as a chat_note and surface it the next time Kristyle texts about
that matter.

### What Leo MUST NOT do

- Do NOT explain the filing system to Kristyle unless she asks.
- Do NOT propose new section codes.
- Do NOT add legal opinions, case strategy, or motivational lines.
- Do NOT chain replies — one point per message, both directions.
- Do NOT invent matter codes; ask if not sure.
- Do NOT invent vault locators (no guessing "I think this is AFF-014") —
  call vault_find or vault_last to actually look it up.

### Cross-link with Rule G (filing-assistant interaction, deploy_286)

Rule G still defines who Kristyle is and what she's authorized for. Rule M
adds the vault layer on top. If her message is NOT vault-related (e.g., she
asks about a meeting or a deadline), fall back to Rule G behavior — answer
from documents/calendar/case_history tools, NOT the vault tools.

## END Rule M
"""


def main():
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    cur = conn.cursor()

    print(f"[deploy_363] loading workflow {WORKFLOW_ID} ...")
    cur.execute("SELECT nodes, connections FROM workflow_entity WHERE id = %s",
                (WORKFLOW_ID,))
    row = cur.fetchone()
    if not row:
        print("FATAL: workflow not found", file=sys.stderr)
        sys.exit(2)
    nodes_raw, conns_raw = row
    nodes = json.loads(nodes_raw) if isinstance(nodes_raw, str) else nodes_raw
    nodes = deepcopy(nodes)

    print("[deploy_363] snapshot ...")
    conns_for_snap = (conns_raw if isinstance(conns_raw, str)
                       else json.dumps(conns_raw))
    cur.execute("""
        INSERT INTO leo_workflow_snapshots
            (workflow_id, reason, nodes_json, connections_json)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """, (WORKFLOW_ID, "pre-deploy_363 Rule M fluid rewrite",
          json.dumps(nodes), conns_for_snap))
    snap_id = cur.fetchone()[0]
    print(f"  snapshot id: {snap_id}")

    agent_idx = next((i for i, n in enumerate(nodes)
                      if n.get("type") == "@n8n/n8n-nodes-langchain.agent"), None)
    if agent_idx is None:
        print("FATAL: AI Agent node not found", file=sys.stderr)
        sys.exit(3)

    agent = nodes[agent_idx]
    sm = agent.get("parameters", {}).get("options", {}).get("systemMessage", "")

    if RULE_M_START in sm and RULE_M_END in sm:
        start = sm.index(RULE_M_START)
        end = sm.index(RULE_M_END) + len(RULE_M_END)
        new_sm = sm[:start] + NEW_RULE_M.strip() + sm[end:]
        action = "replaced"
    else:
        new_sm = sm.rstrip() + "\n\n" + NEW_RULE_M.strip() + "\n"
        action = "appended"
    print(f"  rule_m {action}  delta={len(new_sm) - len(sm):+d}  total={len(new_sm)}")

    agent.setdefault("parameters", {}).setdefault("options", {})["systemMessage"] = new_sm
    nodes[agent_idx] = agent

    cur.execute("""
        UPDATE workflow_entity SET nodes = %s, "updatedAt" = NOW() WHERE id = %s
    """, (json.dumps(nodes), WORKFLOW_ID))

    cur.close()
    conn.close()
    print(f"[deploy_363] DONE — snapshot {snap_id}")


if __name__ == "__main__":
    main()
