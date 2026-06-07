#!/usr/bin/env python3
"""apply_deploy_362_vault_tools.py — wire vault tools into Leo + restore his
filing-assistant conversational role.

Six new toolHttpRequest nodes get added to "Leos Workflow" (vSDQv1vfn6627bnA):
    vault_register      POST  /api/vault/register
    vault_attach_scan   POST  /api/vault/attach_scan
    vault_find          GET   /api/vault/find
    vault_queue         GET   /api/vault/queue
    vault_missing       GET   /api/vault/missing
    vault_last          GET   /api/vault/last

Each is connected as a `ai_tool` input to the AI Agent node so Leo can call
them. Connection direction in n8n langchain: TOOL_NODE → AI_AGENT (the tool
is an input to the agent).

A "Rule M — Vault Coordination" addendum is appended to the AI Agent's
systemMessage. It:
  - tells Leo the six vault verbs Kristyle and Jonathan use,
  - pins him to deterministic execution (call the tool, return the result
    in plain language, no editorializing),
  - keeps Rule G (Kristyle scope) intact and layers vault verbs on top,
  - explicitly forbids Leo from inventing section codes, doc numbers, or
    matter codes — invalid input is a tool error, not a guess.

Idempotent: re-runs replace the six tool nodes by id rather than appending
duplicates, and replace the Rule M block by exact-match delimiter
('## Rule M' to '## END Rule M').

Includes a pre-write snapshot to leo_workflow_snapshots for rollback.
"""
from __future__ import annotations
import json
import os
import sys
from copy import deepcopy

import psycopg2

PG_DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"
BASE_URL = "http://172.18.0.1:8765/api/vault"

# Place new nodes in a horizontal row well clear of existing positions
ROW_Y = -1200
COL_X = 100

NEW_TOOLS = [
    {
        "id": "tool-vault_register",
        "name": "vault_register",
        "endpoint": "register",
        "method": "POST",
        "position": [COL_X, ROW_Y],
        "params": [
            ("section",        "string", "Section code from the master vault: TCT, DEED, SPA, AFF, TAX, PSA, ID, CRT, RES, CONT, CORR, MISC"),
            ("number",         "number", "Section-relative number Kristyle assigned to the folder (1-9999)"),
            ("description",    "string", "What the document is in plain language, e.g. 'affidavit of loss Patricia Zschoche 2026-05-30'"),
            ("matter_code",    "string", "Matter this belongs to. Must start with MWK- or PAR-. Examples: MWK-CV26360, MWK-TCT4497, MWK-ARTA-1210, PAR-CAPACUAN"),
            ("vault_location", "string", "Optional free-text geography: 'Cabinet A, Drawer 2'. Empty string if not specified."),
            ("drive_file_id",  "string", "Optional Drive file id of the initial scan. Empty string if no scan attached yet."),
        ],
        "description": (
            "Create a new physical-master document row in the master vault. "
            "USE WHEN Kristyle texts a 'vault SECTION-NNN ...' message or Jonathan "
            "directs that an original be vaulted. Returns ok=true with doc_id + locator "
            "on success, or ok=false with a specific error: unknown_section, "
            "unknown_matter, locator_taken, description_too_short. Do NOT invent "
            "section codes — only the 12 codes listed in the section parameter are "
            "valid. Do NOT invent matter codes — they must already exist in the "
            "matters table."
        ),
    },
    {
        "id": "tool-vault_attach_scan",
        "name": "vault_attach_scan",
        "endpoint": "attach_scan",
        "method": "POST",
        "position": [COL_X + 280, ROW_Y],
        "params": [
            ("section",       "string", "Section code of the existing vault entry."),
            ("number",        "number", "Vault number of the existing entry."),
            ("drive_file_id", "string", "Drive file id of the scan (preferred)."),
            ("drive_link",    "string", "Full Drive URL alternative if id not available."),
            ("scan_doc_id",   "number", "If the scan is already an existing doc row, use its id and skip drive_file_id/drive_link."),
        ],
        "description": (
            "Attach a digital scan to an existing physical-master vault entry. USE WHEN "
            "Kristyle texts a 'scan SECTION-NNN <drive_id_or_url>' command, or after the "
            "system OCR pipeline produces a scan for a vaulted master. Returns ok=true "
            "with master_doc_id + scan_doc_id on success. Returns no_master_at_SECTION-NNN "
            "if the locator is wrong — do not create the master here, send Kristyle back "
            "to vault_register first."
        ),
    },
    {
        "id": "tool-vault_find",
        "name": "vault_find",
        "endpoint": "find",
        "method": "GET",
        "position": [COL_X + 560, ROW_Y],
        "params": [
            ("section", "string", "Section code (TCT, AFF, etc.)"),
            ("number",  "number", "Vault number"),
        ],
        "description": (
            "Look up a vault entry by SECTION-NNN. USE WHEN someone asks 'what is AFF-014' "
            "or 'find SPA-007'. Returns ok=true with smart_filename, case_file, matter_codes, "
            "digital_scan_id (null if no scan), vault_location, created_at. Returns not_found "
            "if no entry exists at that locator."
        ),
    },
    {
        "id": "tool-vault_queue",
        "name": "vault_queue",
        "endpoint": "queue",
        "method": "GET",
        "position": [COL_X + 840, ROW_Y],
        "params": [],
        "description": (
            "Return Kristyle's pending vault actions: physical masters created without an "
            "attached digital scan. USE WHEN Kristyle texts 'queue' or 'what's pending' or "
            "asks what she should work on next. Returns pending_scans array and counts."
        ),
    },
    {
        "id": "tool-vault_missing",
        "name": "vault_missing",
        "endpoint": "missing",
        "method": "GET",
        "position": [COL_X + 1120, ROW_Y],
        "params": [
            ("matter_code", "string", "Matter code to check, e.g. MWK-TCT4497."),
        ],
        "description": (
            "For a matter, list documents that look like they should have physical masters "
            "but don't yet — notarized affidavits, deeds, court orders, titles, etc. USE WHEN "
            "Kristyle asks 'what's missing for X' or 'what needs vaulting for matter Y'. "
            "Returns suggestions with suggested_section codes she can use when she labels."
        ),
    },
    {
        "id": "tool-vault_last",
        "name": "vault_last",
        "endpoint": "last",
        "method": "GET",
        "position": [COL_X + 1400, ROW_Y],
        "params": [
            ("n", "number", "How many recent entries to return (1-100, default 10)."),
        ],
        "description": (
            "Recent vault entries — audit trail. USE WHEN Kristyle asks 'last N vaulted' or "
            "'what did I do today' or Jonathan asks 'what has she been vaulting'. Returns "
            "entries ordered most recent first."
        ),
    },
]


# ── Rule M block (replaced by exact delimiter match) ────────────────────────
RULE_M_START = "## Rule M — Vault Coordination (deploy_362)"
RULE_M_END = "## END Rule M"
RULE_M = f"""{RULE_M_START}

The master vault is the LandTek system of record for physical-original
documents (deploy_361). Kristyle (filing_assistant) builds and curates it
in the field; Jonathan oversees. Leo is the bridge.

### The six verbs and the tools that handle them

| Verb        | Who uses it       | Tool to call         |
|-------------|-------------------|----------------------|
| vault       | Kristyle, Jonathan| vault_register       |
| scan        | Kristyle          | vault_attach_scan    |
| find        | both              | vault_find           |
| queue       | Kristyle, Jonathan| vault_queue          |
| missing     | both              | vault_missing        |
| last        | both              | vault_last           |

### Conversation rules — strict

1. If a Telegram message starts with `vault`, `scan`, `find`, `queue`,
   `missing`, or `last`, treat it as a vault command. Parse it into the
   tool parameters and CALL THE TOOL. Do not paraphrase her message, do
   not editorialize, do not ask Kristyle to clarify what a section code
   means.

2. If parsing fails (missing section, no number, unknown matter), reply
   in plain language explaining what's missing — one sentence — and stop.
   Example: "Need a matter code. Reply with matter:MWK-TCT4497 (or whichever applies)."

3. ALL section codes are exactly one of: TCT, DEED, SPA, AFF, TAX, PSA,
   ID, CRT, RES, CONT, CORR, MISC. Reject any other code without calling
   the tool. Tell her the closest valid code if her input is a typo.

4. NEVER invent a matter code. If Kristyle does not give one and her
   message doesn't make it obvious, ask: "Which matter? Examples:
   MWK-TCT4497, MWK-ARTA-1210, MWK-CV26360." Do not guess.

5. After a successful vault_register or vault_attach_scan, send a
   ONE-LINE confirmation back: "Logged AFF-001 — affidavit of loss
   Patricia Zschoche, matter MWK-TCT4497." Plain text. Then stop.

6. When Kristyle vaults something, you may briefly notify Jonathan with
   one line via telegram_summary_for_jonathan. ONE line per vault event,
   not a paragraph. Pacing rule still applies — if he has an
   un-replied message, you skip the notify.

7. When Jonathan tells you something about the vault (e.g., "the
   manifestation went to OP last week, expect a returning copy"), record
   it as a chat_note and surface it next time Kristyle texts.

### What Leo MUST NOT do in vault context

- Do NOT explain the filing system to Kristyle unless she explicitly asks.
- Do NOT propose new section codes.
- Do NOT add legal opinions, case strategy, or motivational lines.
- Do NOT chain replies — one point per message, both directions.
- Do NOT call any non-vault tool to answer a vault command. If she asks
  "what's pending hardcopy for ARTA-1210" → that's `vault_missing` with
  matter_code=MWK-ARTA-1210, full stop.

### Cross-link with Rule G (filing-assistant interaction, deploy_286)

Rule G still defines who Kristyle is and what she's authorized for.
Rule M is the vault verb layer on top of Rule G. If a Kristyle message
is NOT a vault verb, fall back to Rule G behavior.

{RULE_M_END}
"""


def build_tool_node(spec):
    """Construct a toolHttpRequest n8n node from the spec."""
    node = {
        "id": spec["id"],
        "name": spec["name"],
        "type": "@n8n/n8n-nodes-langchain.toolHttpRequest",
        "typeVersion": 1.1,
        "position": spec["position"],
        "parameters": {
            "url": f"{BASE_URL}/{spec['endpoint']}",
            "method": spec["method"],
            "toolDescription": spec["description"],
        },
    }
    if spec["method"] == "GET":
        node["parameters"]["sendQuery"] = True
        node["parameters"]["parametersQuery"] = {
            "values": [
                {
                    "name": p[0],
                    "valueProvider": "modelOptional",
                    "description": p[2],
                }
                for p in spec["params"]
            ]
        }
    else:
        # POST with JSON body assembled by the agent
        node["parameters"]["sendBody"] = True
        node["parameters"]["specifyBody"] = "json"
        body_lines = ["{"]
        for i, (name, _typ, _desc) in enumerate(spec["params"]):
            comma = "," if i < len(spec["params"]) - 1 else ""
            body_lines.append(f'  "{name}": {{ $fromAI("{name}") }}{comma}')
        body_lines.append("}")
        node["parameters"]["jsonBody"] = "={" + "}".join(["", *body_lines, ""]) + "}"
        # Simpler form using direct param send
        node["parameters"].pop("jsonBody", None)
        node["parameters"]["specifyBody"] = "keypair"
        node["parameters"]["parametersBody"] = {
            "values": [
                {
                    "name": p[0],
                    "valueProvider": "modelOptional",
                    "description": p[2],
                }
                for p in spec["params"]
            ]
        }
    return node


def upsert_node(nodes_list, new_node):
    """Replace by id if exists, else append."""
    for i, n in enumerate(nodes_list):
        if n.get("id") == new_node["id"]:
            nodes_list[i] = new_node
            return "replaced"
    nodes_list.append(new_node)
    return "appended"


def patch_system_message(sm):
    """Append or replace the Rule M block. Returns new sm + change marker."""
    if RULE_M_START in sm and RULE_M_END in sm:
        # Replace existing block
        start = sm.index(RULE_M_START)
        end = sm.index(RULE_M_END) + len(RULE_M_END)
        return sm[:start] + RULE_M.strip() + sm[end:], "replaced"
    # Append at end
    return sm.rstrip() + "\n\n" + RULE_M.strip() + "\n", "appended"


def connect_tools(connections, tool_names, agent_name="AI Agent"):
    """Wire each tool as an `ai_tool` input to the AI Agent.

    n8n connection model: source_node -> connection_type -> target_node_array.
    Tool nodes connect with type 'ai_tool' to the AI Agent.
    """
    for tname in tool_names:
        node_conns = connections.setdefault(tname, {})
        ai_tool_conns = node_conns.setdefault("ai_tool", [])
        # Each entry is a list of edge dicts: [[{node, type, index}]]
        # Replace any existing ai_tool connection to AI Agent
        new_edge = [{"node": agent_name, "type": "ai_tool", "index": 0}]
        node_conns["ai_tool"] = [new_edge]


def main():
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    cur = conn.cursor()

    print(f"[deploy_362] loading workflow {WORKFLOW_ID} ...")
    cur.execute("SELECT nodes, connections FROM workflow_entity WHERE id = %s",
                (WORKFLOW_ID,))
    row = cur.fetchone()
    if not row:
        print("FATAL: workflow not found", file=sys.stderr)
        sys.exit(2)
    nodes_raw, conns_raw = row
    nodes = json.loads(nodes_raw) if isinstance(nodes_raw, str) else nodes_raw
    connections = json.loads(conns_raw) if isinstance(conns_raw, str) else conns_raw
    nodes = deepcopy(nodes)
    connections = deepcopy(connections)

    print(f"[deploy_362] snapshotting current state to leo_workflow_snapshots ...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leo_workflow_snapshots (
            id          serial PRIMARY KEY,
            workflow_id text NOT NULL,
            reason      text NOT NULL,
            nodes       jsonb NOT NULL,
            connections jsonb NOT NULL,
            taken_at    timestamptz NOT NULL DEFAULT now()
        )
    """)
    cur.execute("""
        INSERT INTO leo_workflow_snapshots (workflow_id, reason, nodes, connections)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """, (WORKFLOW_ID, "pre-deploy_362 vault tools",
          json.dumps(nodes), json.dumps(connections)))
    snap_id = cur.fetchone()[0]
    print(f"  snapshot id: {snap_id}")

    print("[deploy_362] adding/replacing six vault tool nodes ...")
    added_names = []
    for spec in NEW_TOOLS:
        node = build_tool_node(spec)
        action = upsert_node(nodes, node)
        added_names.append(spec["name"])
        print(f"  {action:>8}  {spec['name']:<22}  -> {spec['method']} {BASE_URL}/{spec['endpoint']}")

    print("[deploy_362] connecting tools as ai_tool inputs to AI Agent ...")
    # Find AI Agent name
    agent_node = next((n for n in nodes
                       if n.get("type") == "@n8n/n8n-nodes-langchain.agent"), None)
    if not agent_node:
        print("FATAL: AI Agent node not found", file=sys.stderr)
        sys.exit(3)
    agent_name = agent_node["name"]
    print(f"  agent node name: {agent_name!r}")
    connect_tools(connections, added_names, agent_name=agent_name)

    print("[deploy_362] patching AI Agent systemMessage with Rule M ...")
    sm = agent_node.get("parameters", {}).get("options", {}).get("systemMessage", "")
    new_sm, sm_action = patch_system_message(sm)
    sm_delta = len(new_sm) - len(sm)
    print(f"  rule_m {sm_action} ({sm_delta:+d} chars; total now {len(new_sm)})")
    agent_node.setdefault("parameters", {}).setdefault("options", {})["systemMessage"] = new_sm
    # Re-find agent in nodes and replace
    for i, n in enumerate(nodes):
        if n.get("name") == agent_name:
            nodes[i] = agent_node
            break

    print("[deploy_362] writing workflow back ...")
    cur.execute("""
        UPDATE workflow_entity
           SET nodes = %s, connections = %s, "updatedAt" = NOW()
         WHERE id = %s
    """, (json.dumps(nodes), json.dumps(connections), WORKFLOW_ID))

    cur.close()
    conn.close()
    print(f"[deploy_362] DONE — snapshot {snap_id} for rollback")


if __name__ == "__main__":
    main()
