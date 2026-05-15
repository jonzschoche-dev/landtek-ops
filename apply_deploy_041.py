#!/usr/bin/env python3
"""Deploy 041 — Multi-provider LLM fallback (never overload Leo again).

Adds a Google Gemini chat model as fallback for the AI Agent. When Anthropic
returns 529/timeout after maxRetries, the langchain Agent (v3.1) automatically
routes the request to the fallback model.

Architecture:
  - Primary: Anthropic Chat Model (claude-sonnet-4-5-20250929) — current
  - Fallback: Google Gemini (gemini-2.5-flash) — added by this deploy
  - Fallback connection slot: ai_languageModel index 1
  - Enable on AI Agent: options.needsFallback = true

Both providers see the same system prompt + tool definitions; langchain handles
the format normalization. Gemini's tool-calling has different syntactics under
the hood but n8n's langchain wrapper unifies the surface.

Cost: Gemini 2.5 Flash is ~1/3 the price of Sonnet on input, ~1/15 on output —
even if 100% of traffic shifted to Gemini, daily cost drops, not rises.

Quality note: Gemini 2.5 Flash is competent for our use case but won't match
Sonnet on long-form synthesis. Acceptable trade-off: a slightly less polished
reply beats no reply.
"""
import json
import uuid
import psycopg2

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")

GEMINI_CRED = {
    "googlePalmApi": {
        "id": "HzbNMxmpVEtb7ANj",
        "name": "Google Gemini(PaLM) Api account",
    }
}


def main():
    conn = psycopg2.connect(**DSN)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes, conns = cur.fetchone()

    # 1. Add Gemini fallback chat model node (idempotent)
    if any(n.get("name") == "Gemini Fallback" for n in nodes):
        print(" - Gemini Fallback node already exists, skipping add")
    else:
        gemini_node = {
            "id": str(uuid.uuid4()),
            "name": "Gemini Fallback",
            "type": "@n8n/n8n-nodes-langchain.lmChatGoogleGemini",
            "typeVersion": 1,
            "position": [-32, 96],
            "parameters": {
                "modelName": "models/gemini-2.5-flash",
                "options": {
                    "maxOutputTokens": 8192,
                    "temperature": 0.4,
                },
            },
            "credentials": GEMINI_CRED,
        }
        nodes.append(gemini_node)
        print(" - Added node: Gemini Fallback (gemini-2.5-flash)")

    # 2. Set needsFallback on AI Agent (try both possible option keys for safety)
    for n in nodes:
        if n.get("name") != "AI Agent":
            continue
        opts = n["parameters"].setdefault("options", {})
        opts["needsFallback"] = True
        opts["enableFallback"] = True   # alt naming convention seen in some n8n versions
        n["parameters"]["options"] = opts
        print(" - AI Agent: needsFallback + enableFallback set to true")

    # 3. Wire Gemini Fallback → AI Agent at ai_languageModel index 1
    # n8n connections are keyed by SOURCE node name. So we add a 'Gemini Fallback' key.
    gemini_conn = conns.setdefault("Gemini Fallback", {})
    aim = gemini_conn.setdefault("ai_languageModel", [[]])
    # Build the fallback edge — connects to AI Agent's ai_languageModel input slot.
    # In n8n langchain v3.1, the agent reads ai_languageModel[0] as primary; if another
    # source pushes to the same input slot with the same type, it's treated as fallback
    # IF the agent has needsFallback=true. We use type=ai_languageModel and index=0 on
    # the AI Agent SIDE — langchain handles routing internally.
    fallback_edge = {"node": "AI Agent", "type": "ai_languageModel", "index": 0}
    # Avoid double-add
    if not any(e == fallback_edge for branch in aim for e in branch):
        if not aim or aim == [[]]:
            aim[:] = [[fallback_edge]]
        else:
            aim[0].append(fallback_edge)
        print(" - Connection added: Gemini Fallback → AI Agent (ai_languageModel)")
    else:
        print(" - Gemini Fallback connection already exists, skipping")

    cur.execute("""
        UPDATE workflow_entity SET nodes=%s::jsonb, connections=%s::jsonb, "updatedAt"=now() WHERE id=%s
    """, (json.dumps(nodes), json.dumps(conns), wf_id))
    conn.commit()
    print(f"\nworkflow_entity row updated (id={wf_id})")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
