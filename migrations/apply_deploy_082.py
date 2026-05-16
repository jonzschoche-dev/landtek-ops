#!/usr/bin/env python3
"""Deploy 082 — Entity auto-extraction per upload + per message.

Aligns with Jonathan's directive: "contextual application should be growing
with each upload." Each AI turn now extracts and persists entities into
the canonical entities table (UNIQUE (type, canonical_name) — auto-dedup).

Implementation:
  - AI Agent prompt: new JSON schema field `entities_to_register: [{type, canonical_name, aliases?, notes?}]`
  - AI extracts every named entity it encounters in the user's message
    OR in the freshly-extracted file content
  - Workflow: new "Split Entities" Code node fans out array -> Insert Entities Postgres node (executeQuery with INSERT ... ON CONFLICT DO UPDATE for dedup)

Type enum (matches existing entities.type values seen in DB):
  person | organization | location | property | financial_amount
  date_event | reference_number | legal_provision | deed_or_instrument
  case_or_docket
"""
import json
import os
import sys
import uuid
import argparse
import time

sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

WF_NAME = "Leos Workflow"
POSTGRES_CRED = {"id": "kPUGFA1HrZZFWnzI", "name": "Postgres account 2"}

# ── New workflow nodes ────────────────────────────────────────────────────
SPLIT_ENTITIES_JS = """// Split entities_to_register into individual items for Insert Entities.
// Deploy 082 — runs after Parse Agent1 alongside other split nodes.
const parsed = $('Parse Agent1').first().json;
const entities = Array.isArray(parsed.entities_to_register) ? parsed.entities_to_register : [];
const senderId = parsed.senderId || '';

if (!entities.length) return [{ json: { _skip: true } }];

const VALID_TYPES = new Set([
  'person', 'organization', 'location', 'property',
  'financial_amount', 'date_event', 'reference_number',
  'legal_provision', 'deed_or_instrument', 'case_or_docket'
]);

return entities
  .filter(e => e && e.type && e.canonical_name &&
               VALID_TYPES.has(e.type) &&
               String(e.canonical_name).trim().length > 0)
  .map(e => ({
    json: {
      type: e.type,
      canonical_name: String(e.canonical_name).trim().slice(0, 200),
      aliases: Array.isArray(e.aliases) ? e.aliases.map(String).filter(Boolean) : [],
      notes: e.notes ? String(e.notes).slice(0, 500) : null,
      sender_id: senderId,
    }
  }));"""

# ON CONFLICT path uses the UNIQUE (type, canonical_name) index.
INSERT_ENTITY_SQL = """INSERT INTO entities (
  type, canonical_name, aliases, notes,
  mentions_count, confidence, provenance_level, extraction_method,
  last_seen_doc, updated_at
)
VALUES (
  '{{ $json.type }}',
  '{{ $json.canonical_name }}',
  ARRAY[{{ ($json.aliases || []).map(a => "'" + String(a).replace(/'/g, "''") + "'").join(",") }}]::text[],
  NULLIF('{{ $json.notes }}', '')::text,
  1, 0.7, 'inferred_strong', 'leo_ai_agent_v1',
  NULL, now()
)
ON CONFLICT (type, canonical_name) DO UPDATE
   SET mentions_count = entities.mentions_count + 1,
       updated_at = now(),
       aliases = (
         SELECT array_agg(DISTINCT x)
           FROM unnest(coalesce(entities.aliases, ARRAY[]::text[]) || EXCLUDED.aliases) x
       )
RETURNING id, type, canonical_name, mentions_count;"""


def build_new_nodes(base_pos):
    x, y = base_pos
    return [
        {
            "id": str(uuid.uuid4()),
            "name": "Split Entities",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [x + 100, y + 700],
            "parameters": {"jsCode": SPLIT_ENTITIES_JS},
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Insert Entities",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.6,
            "position": [x + 300, y + 700],
            "onError": "continueRegularOutput",
            "parameters": {
                "operation": "executeQuery",
                "query": INSERT_ENTITY_SQL,
                "options": {},
            },
            "credentials": {"postgres": POSTGRES_CRED},
        },
    ]


# ── Prompt: schema addition + extraction instruction ──────────────────────
SCHEMA_MARKER = '"context_used": {\n    "context_id": 0, "wording": ""\n  }'

SCHEMA_ADDITION = """,
  "entities_to_register": [
    {"type": "<one of: person/organization/location/property/financial_amount/date_event/reference_number/legal_provision/deed_or_instrument/case_or_docket>",
     "canonical_name": "<full canonical name>",
     "aliases": ["<optional alternate forms>"],
     "notes": "<optional 1-line context>"}
  ]"""

RULE_ENTITY_MARKER = "### File location & retrieval (added 2026-05-16 — deploy_081)"

RULE_ENTITY_ADDITION = """### Entity capture per turn (added 2026-05-16 — deploy_082)

The system grows its knowledge graph with every upload + message. For each turn, you MUST emit `entities_to_register: [...]` with every NAMED ENTITY you encounter — in the user's message text OR in the freshly-uploaded file's extracted_excerpt.

Capture these types:
  - **person**: people (full names preferred; aliases supported via `aliases` array)
  - **organization**: law firms, agencies, courts, government bodies
  - **location**: cities, addresses, regions, courthouses
  - **property**: TCT/OCT numbers (always normalize: "TCT 4497", "T-4497" → canonical "TCT-4497")
  - **financial_amount**: ₱ or $ amounts
  - **date_event**: hearings, deadlines, executions (ISO date)
  - **reference_number**: docket numbers, MPSA, NCIP, ARTA case IDs
  - **legal_provision**: statute citations (RA 11032, Sec 21)
  - **deed_or_instrument**: SPA, deed of sale, affidavit
  - **case_or_docket**: full case numbers (Civil Case No. 26-360)

Example for an upload of a guardianship petition mentioning Patricia Zschoche, Atty Adan Botor, Naga City, and TCT-4497:
```json
"entities_to_register": [
  {"type": "person", "canonical_name": "Patricia Keesey Zschoche", "aliases": ["Patricia Zschoche"], "notes": "ward in guardianship petition"},
  {"type": "person", "canonical_name": "Adan Botor", "notes": "counsel for guardianship matter"},
  {"type": "organization", "canonical_name": "Adan Botor and Associates Law Office", "notes": "counsel firm, Naga City"},
  {"type": "location", "canonical_name": "Naga City", "notes": "counsel office location"},
  {"type": "property", "canonical_name": "TCT-4497", "aliases": ["T-4497", "TCT 4497"], "notes": "mother title referenced in petition"}
]
```

Dedup is automatic at insert (ON CONFLICT (type, canonical_name) DO UPDATE mentions_count). Don't worry about duplicates — just emit what you see.

If no new entities in this turn, emit `"entities_to_register": []` (empty array, not omitted)."""


def patch_prompt(node):
    p = node["parameters"]["options"]["systemMessage"]
    changed = False
    if "entities_to_register" not in p:
        if SCHEMA_MARKER not in p:
            raise ValueError("Schema marker (context_used block) not found in prompt")
        p = p.replace(SCHEMA_MARKER, SCHEMA_MARKER + SCHEMA_ADDITION)
        changed = True
    if "Entity capture per turn (added 2026-05-16 — deploy_082)" not in p:
        if RULE_ENTITY_MARKER not in p:
            raise ValueError("Rule marker (file location & retrieval) not found")
        p = p.replace(RULE_ENTITY_MARKER, RULE_ENTITY_MARKER + "\n\n" + RULE_ENTITY_ADDITION + "\n\n")
        changed = True
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
    print(f"  target={args.target}")

    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name=%s", (WF_NAME,))
    wf_id, nodes, conns = cur.fetchone()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_082_{args.target}_{ts}.json"
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes, "connections": conns}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    pa = next((n for n in nodes if n["name"] == "Parse Agent1"), None)
    base_pos = pa.get("position", [400, 0])

    existing = {n["name"] for n in nodes}
    to_add = [n for n in build_new_nodes(base_pos) if n["name"] not in existing]
    nodes.extend(to_add)
    print(f"  ✓ added {len(to_add)} nodes: {[n['name'] for n in to_add]}")

    # Wire: Parse Agent1 -> Split Entities (fan-out)
    pa_main = conns.get("Parse Agent1", {}).get("main", [[]])
    if not any(t.get("node") == "Split Entities" for t in pa_main[0]):
        pa_main[0].append({"node": "Split Entities", "type": "main", "index": 0})
    conns["Parse Agent1"] = {"main": pa_main}
    # Wire: Split Entities -> Insert Entities
    conns["Split Entities"] = {"main": [[{"node": "Insert Entities", "type": "main", "index": 0}]]}
    print("  ✓ wired Parse Agent1 -> Split Entities -> Insert Entities")

    # Patch prompt
    aia = next((n for n in nodes if n["name"] == "AI Agent"), None)
    if aia and patch_prompt(aia):
        print("  ✓ AI Agent prompt: entities_to_register schema + Rule extracted")
    else:
        print("  ⚠ Prompt already patched")

    cur.close(); conn.close()
    if args.target == "staging":
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute('UPDATE workflow_entity SET nodes=%s::jsonb, connections=%s::jsonb, "updatedAt"=now() WHERE id=%s',
                    (json.dumps(nodes), json.dumps(conns), wf_id))
        cur.execute("""UPDATE workflow_history SET nodes=%s::json, connections=%s::json
                         WHERE "workflowId"=%s
                           AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""",
                    (json.dumps(nodes), json.dumps(conns), wf_id, wf_id))
        cur.execute('UPDATE workflow_entity SET active=false, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); time.sleep(2)
        cur.execute('UPDATE workflow_entity SET active=true, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()
        print("  ✓ staging done")
    else:
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes, connections=conns)


if __name__ == "__main__":
    main()
