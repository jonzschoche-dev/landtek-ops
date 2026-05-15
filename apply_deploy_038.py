#!/usr/bin/env python3
"""Deploy 038 — pending_inquiries + Response Correlation.

Stages:
 1. Create pending_inquiries table + indexes.
 2. Workflow patches in one transaction:
    - Append Rule D to AI Agent systemMessage.
    - Modify Context Builder to read pendingInquiries from Fetch Pending Inquiries.
    - Switch router gets a new 'inquiry_resolution' branch (highest priority).
    - 4 new nodes:
        Fetch Pending Inquiries (postgres)        — between Execute a SQL query and Context Builder
        Log Pending Inquiry (postgres)            — after Send to Target Contact
        Close Pending Inquiry (postgres)          — new switch branch
        Notify Jonathan of Resolution (telegram)  — after Close Pending Inquiry
    - Reroute connections to insert the new nodes in the right places.

Snapshot saved at /root/landtek/snapshots/leos_workflow_pre_038_*.json
"""
import json
import uuid
import psycopg2

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")

PG_CRED = {"postgres": {"id": "kPUGFA1HrZZFWnzI", "name": "Postgres account 2"}}
TG_CRED = {"telegramApi": {"id": "dSI1mdlTrzwdd1B8", "name": "Telegram account"}}

# ── Rule D — Response Correlation prompt addition ───────────────────────────
RULE_D = """

---

## RESPONSE CORRELATION (Rule D — relayed inquiry follow-up)

When the current sender is NOT Jonathan (a client is talking to you) AND `context.pendingInquiries[]` is non-empty, you are looking at a potential answer to a question Jonathan previously asked you to relay via Rule C. Process this as follows:

1. **Read the oldest open inquiry** in `context.pendingInquiries[]` (sorted by `asked_at` ascending). Each entry has: `id`, `question_text` (Jonathan's verbatim ask), `relayed_message` (the inquiry you sent the client), `asked_at`, `target_client_name`.

2. **Judge whether the current client message is the answer** — semantically, not just by keyword. Score your confidence 0..1.

3. **If confidence ≥ 0.7** (it's the answer):
   - Set `pending_inquiry_resolution = { id: <inquiry_id>, response_text: <verbatim or short summary of the client's answer>, confidence: <float> }` in your JSON output.
   - Set `target_chat_id = "6513067717"` and `target_message = "<Client> answered your inquiry '<short>': <verbatim or summary>"`. This is the ONE place where you reach Jonathan from a non-Jonathan turn — the Rule C auth gate is satisfied by `pending_inquiry_resolution.id` being non-empty (the workflow handles this).
   - Reply naturally to the client in `telegram_reply_to_client` — Rule B still applies: thank them, investigate any remaining gap, journal as note.

4. **If confidence < 0.7** (not the answer, or ambiguous):
   - Leave `pending_inquiry_resolution` empty/null.
   - Process the client message normally per Rule B (proactive investigation, scoped).
   - The inquiry stays open until a future message resolves it or it expires.

5. **Never reveal Jonathan or the back-channel to the client.** Do not say "thanks, I'll pass this on", "Jonathan was asking", or anything that exposes the relay. Frame your reply as your own follow-up.

6. **Multiple open inquiries**: process only the oldest one per turn. If the message could resolve multiple, attribute it to the oldest and leave the others open — confirm with Jonathan in the resolution message.

7. **Expired inquiries**: never appear in `context.pendingInquiries[]` (filtered at fetch time). Do not act on stale state.
"""

CONTEXT_BUILDER_INJECTION = """

// ── pendingInquiries (deploy 038 — Response Correlation) ─────────────────
// Read all rows produced by 'Fetch Pending Inquiries' (a separate Postgres node
// that ran just before Context Builder). Each row is an n8n item.
let pendingInquiries = [];
try {
  const items = $('Fetch Pending Inquiries').all();
  pendingInquiries = items
    .map(i => i.json)
    .filter(r => r && r.id);  // skip empty results
} catch (e) {
  pendingInquiries = [];
}
"""


def main():
    conn = psycopg2.connect(**DSN)
    conn.autocommit = False
    cur = conn.cursor()

    # ── Stage 1: Schema ────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_inquiries (
            id                  SERIAL PRIMARY KEY,
            asked_by_chat_id    TEXT NOT NULL,
            question_text       TEXT NOT NULL,
            target_client_code  VARCHAR(50) NOT NULL,
            target_chat_id      TEXT NOT NULL,
            target_client_name  TEXT,
            relayed_message     TEXT NOT NULL,
            status              TEXT NOT NULL DEFAULT 'open'
                                CHECK (status IN ('open','answered','closed','expired')),
            asked_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at          TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
            response_text       TEXT,
            response_conv_id    INT,
            responded_at        TIMESTAMPTZ,
            closed_reason       TEXT,
            ai_match_confidence REAL,
            FOREIGN KEY (response_conv_id) REFERENCES conversations(id)
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS pending_inq_open_by_target ON pending_inquiries(target_chat_id) WHERE status='open';")
    cur.execute("CREATE INDEX IF NOT EXISTS pending_inq_status_asked ON pending_inquiries(status, asked_at DESC);")
    print(" - pending_inquiries table + indexes ensured")

    # ── Stage 2: Workflow patch ─────────────────────────────────────────────
    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes, conns = cur.fetchone()

    existing_names = {n.get("name") for n in nodes}

    # 2a. Rule D into AI Agent prompt
    rule_d_added = False
    for n in nodes:
        if n.get("name") != "AI Agent":
            continue
        sm = n["parameters"].get("options", {}).get("systemMessage", "")
        if "RESPONSE CORRELATION (Rule D" in sm:
            print(" - AI Agent: Rule D already present, skipping")
        else:
            new_sm = sm + RULE_D
            n["parameters"].setdefault("options", {})["systemMessage"] = new_sm
            rule_d_added = True
            print(f" - AI Agent: Rule D appended ({len(sm)} -> {len(new_sm)} chars, delta {len(new_sm) - len(sm):+d})")

    # 2b. Context Builder injection — add pendingInquiries reading
    cb_patched = False
    for n in nodes:
        if n.get("name") != "Context Builder":
            continue
        js = n["parameters"].get("jsCode", "")
        if "pendingInquiries" in js:
            print(" - Context Builder: pendingInquiries already present, skipping")
        else:
            # Insert the pendingInquiries logic right after the first line that
            # defines `const msg = $('Telegram Trigger')...`.
            anchor = "const msg = $('Telegram Trigger').first().json.message || {};"
            if anchor not in js:
                raise RuntimeError("Context Builder: expected anchor not found, refusing to patch blind")
            new_js = js.replace(anchor, anchor + CONTEXT_BUILDER_INJECTION, 1)
            # And ensure pendingInquiries lands in the returned object
            # Look for the `return [{ json: { ...` line and inject the field.
            # The existing Context Builder ends with `return [{ json: {...} }]`. Easiest:
            # patch the last `return [{ json:` to include pendingInquiries.
            # Use a marker approach: find `clientRow` since that's used.
            marker = "clientRow,"
            if marker in new_js:
                new_js = new_js.replace(marker, marker + "\n    pendingInquiries,", 1)
            else:
                # Fallback: append before final `}}];` of return statement
                if "}]" in new_js:
                    pass  # leave alone; we'll log warning
                print("WARN: Context Builder return marker not patched, pendingInquiries may be unreachable")
            n["parameters"]["jsCode"] = new_js
            cb_patched = True
            print(f" - Context Builder: pendingInquiries injection added ({len(js)} -> {len(new_js)} chars)")

    # 2c. New node: Fetch Pending Inquiries (Postgres)
    if "Fetch Pending Inquiries" not in existing_names:
        fetch_node = {
            "id": str(uuid.uuid4()),
            "name": "Fetch Pending Inquiries",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.6,
            "position": [32, -200],
            "parameters": {
                "operation": "executeQuery",
                "query": "SELECT id, question_text, relayed_message, asked_at::text AS asked_at, target_client_name FROM pending_inquiries WHERE target_chat_id = '{{ $('Telegram Trigger').first().json.message.from.id }}' AND status='open' AND expires_at > now() ORDER BY asked_at ASC LIMIT 3;",
                "options": {},
            },
            "credentials": PG_CRED,
        }
        nodes.append(fetch_node)
        print(" - Added node: Fetch Pending Inquiries")

    # 2d. New node: Log Pending Inquiry (Postgres) — after Send to Target Contact
    if "Log Pending Inquiry" not in existing_names:
        log_node = {
            "id": str(uuid.uuid4()),
            "name": "Log Pending Inquiry",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.6,
            "position": [2848, 96],
            "parameters": {
                "operation": "executeQuery",
                "query": (
                    "INSERT INTO pending_inquiries "
                    "(asked_by_chat_id, question_text, target_client_code, target_chat_id, target_client_name, relayed_message) "
                    "VALUES ("
                    "'{{ $('Telegram Trigger').first().json.message.from.id }}', "
                    "'{{ ($('Telegram Trigger').first().json.message.text || $('Telegram Trigger').first().json.message.caption || '').replace(/'/g, \"''\") }}', "
                    "COALESCE((SELECT client_code FROM clients WHERE telegram_id = '{{ $('Parse Agent1').first().json.target_chat_id }}' LIMIT 1), 'Unknown'), "
                    "'{{ $('Parse Agent1').first().json.target_chat_id }}', "
                    "COALESCE((SELECT name FROM clients WHERE telegram_id = '{{ $('Parse Agent1').first().json.target_chat_id }}' LIMIT 1), 'Unknown'), "
                    "'{{ ($('Parse Agent1').first().json.target_message || '').replace(/'/g, \"''\") }}'"
                    ") RETURNING id;"
                ),
                "options": {},
            },
            "credentials": PG_CRED,
        }
        nodes.append(log_node)
        print(" - Added node: Log Pending Inquiry")

    # 2e. New node: Close Pending Inquiry (Postgres)
    if "Close Pending Inquiry" not in existing_names:
        close_node = {
            "id": str(uuid.uuid4()),
            "name": "Close Pending Inquiry",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.6,
            "position": [928, 480],
            "parameters": {
                "operation": "executeQuery",
                "query": (
                    "UPDATE pending_inquiries "
                    "SET status='answered', "
                    "    response_text='{{ ($json.pending_inquiry_resolution.response_text || '').replace(/'/g, \"''\") }}', "
                    "    responded_at=now(), "
                    "    ai_match_confidence={{ $json.pending_inquiry_resolution.confidence || 0 }}, "
                    "    closed_reason='auto_matched' "
                    "WHERE id = {{ $json.pending_inquiry_resolution.id }} "
                    "RETURNING id, target_client_name, response_text;"
                ),
                "options": {},
            },
            "credentials": PG_CRED,
        }
        nodes.append(close_node)
        print(" - Added node: Close Pending Inquiry")

    # 2f. New node: Notify Jonathan of Resolution (Telegram)
    if "Notify Jonathan of Resolution" not in existing_names:
        notify_node = {
            "id": str(uuid.uuid4()),
            "name": "Notify Jonathan of Resolution",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [1184, 480],
            "parameters": {
                "chatId": "6513067717",
                "text": "={{ $('Parse Agent1').first().json.target_message }}",
                "additionalFields": {"parse_mode": "HTML", "appendAttribution": False},
            },
            "credentials": TG_CRED,
        }
        nodes.append(notify_node)
        print(" - Added node: Notify Jonathan of Resolution")

    # 2g. Switch router — add 'inquiry_resolution' branch (insert at top of rules)
    sw_patched = False
    for n in nodes:
        if n.get("name") != "Switch router":
            continue
        rules = n["parameters"].get("rules", {}).get("values", [])
        if any(r.get("outputKey") == "inquiry_resolution" for r in rules):
            print(" - Switch router: inquiry_resolution branch already present")
        else:
            new_rule = {
                "outputKey": "inquiry_resolution",
                "renameOutput": True,
                "conditions": {
                    "options": {
                        "version": 3,
                        "leftValue": "",
                        "caseSensitive": True,
                        "typeValidation": "strict",
                    },
                    "combinator": "and",
                    "conditions": [
                        {
                            "id": "inquiry-res-id-notempty",
                            "operator": {
                                "type": "string",
                                "operation": "notEmpty",
                                "singleValue": True,
                            },
                            "leftValue": "={{ ($json.pending_inquiry_resolution || {}).id }}",
                            "rightValue": "",
                        }
                    ],
                },
            }
            # Put the new branch at the FRONT so it takes priority
            n["parameters"]["rules"]["values"] = [new_rule] + rules
            sw_patched = True
            print(" - Switch router: inquiry_resolution branch added (at top)")

    # ── 2h. Connections rewiring ────────────────────────────────────────────
    # Track edges added
    edges_added = []

    # Edge 1: Execute a SQL query → Fetch Pending Inquiries → Context Builder
    # First remove the existing Execute → Context Builder direct edge
    if "Execute a SQL query" in conns:
        existing = conns["Execute a SQL query"].get("main", [[]])
        # Replace destination with Fetch Pending Inquiries (only when needed)
        replaced = False
        for branch in existing:
            for edge in branch:
                if edge.get("node") == "Context Builder":
                    edge["node"] = "Fetch Pending Inquiries"
                    replaced = True
                    edges_added.append("Execute a SQL query → Fetch Pending Inquiries (was: → Context Builder)")
        if replaced:
            conns.setdefault("Fetch Pending Inquiries", {"main": [[{"node": "Context Builder", "type": "main", "index": 0}]]})
            edges_added.append("Fetch Pending Inquiries → Context Builder")

    # Edge 2: Send to Target Contact → Log Pending Inquiry
    if "Send to Target Contact" not in conns:
        conns["Send to Target Contact"] = {"main": [[]]}
    has_log = any(
        e.get("node") == "Log Pending Inquiry"
        for branch in conns["Send to Target Contact"].get("main", [])
        for e in branch
    )
    if not has_log:
        if not conns["Send to Target Contact"]["main"]:
            conns["Send to Target Contact"]["main"] = [[]]
        conns["Send to Target Contact"]["main"][0].append(
            {"node": "Log Pending Inquiry", "type": "main", "index": 0}
        )
        edges_added.append("Send to Target Contact → Log Pending Inquiry")

    # Edge 3: Switch router 'inquiry_resolution' (index 0, since prepended) → Close Pending Inquiry
    if "Switch router" not in conns:
        conns["Switch router"] = {"main": []}
    sw_main = conns["Switch router"]["main"]
    # Ensure the new front-most output has its own slot at index 0
    new_branch_slot = [{"node": "Close Pending Inquiry", "type": "main", "index": 0}]
    if not sw_main or sw_main[0] != new_branch_slot:
        sw_main.insert(0, new_branch_slot)
        edges_added.append("Switch router[inquiry_resolution] → Close Pending Inquiry")

    # Edge 4: Close Pending Inquiry → Notify Jonathan of Resolution
    if "Close Pending Inquiry" not in conns:
        conns["Close Pending Inquiry"] = {"main": [[{"node": "Notify Jonathan of Resolution", "type": "main", "index": 0}]]}
        edges_added.append("Close Pending Inquiry → Notify Jonathan of Resolution")

    for e in edges_added:
        print(f"   edge: {e}")

    # Write back
    cur.execute("""
        UPDATE workflow_entity SET nodes=%s::jsonb, connections=%s::jsonb, "updatedAt"=now() WHERE id=%s
    """, (json.dumps(nodes), json.dumps(conns), wf_id))
    conn.commit()
    print(f"\nworkflow_entity row updated (id={wf_id})")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
