#!/usr/bin/env python3
"""Deploy 034 — close three data-loss surfaces.

1. Insert Chat Note: wire full column mapping (currently only `archived: false`),
   coerce topic to allowed enum at the n8n expression level.
2. Insert Calendar Event: wire full column mapping (currently only start_at with
   `==` typo), fix the typo.
3. Raw LLM output persistence: add `conversations.raw_llm_output text` column
   (single nullable text) and extend Log Conversation node to populate it from
   $('AI Agent').first().json.output.

Snapshot saved at /root/landtek/snapshots/leos_workflow_pre_034_*.json
"""
import json
import psycopg2

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")

ALLOWED_TOPIC_ENUM = "['legal_strategy','evidence','people','deadlines','communications','task','misc']"

CHAT_NOTE_COLS = {
    "content":          "={{ $json.content }}",
    "summary":          "={{ $json.summary }}",
    "topic":            "={{ " + ALLOWED_TOPIC_ENUM + ".includes($json.topic) ? $json.topic : 'misc' }}",
    "importance":       "={{ $json.importance }}",
    "related_case":     "={{ $json.related_case }}",
    "related_tct":      "={{ $json.related_tct }}",
    "sender_id":        "={{ $json.created_by_telegram_id }}",
    "sender_name":      "={{ $('Context Builder').first().json.senderName }}",
    "telegram_msg_id":  "={{ $('Telegram Trigger').first().json.message.message_id }}",
    "archived":         False,
}

CHAT_NOTE_SCHEMA_IDS = [
    "id", "telegram_msg_id", "sender_id", "sender_name", "content",
    "summary", "topic", "related_entity_id", "related_tct", "related_case",
    "related_event_id", "importance", "archived", "created_at", "client_id",
]

CALENDAR_EVENT_COLS = {
    "title":         "={{ $json.title }}",
    "description":   "={{ $json.description }}",
    "start_at":      "={{ $json.start_at }}",
    "end_at":        "={{ $json.end_at }}",
    "location":      "={{ $json.location }}",
    "related_tct":   "={{ $json.related_tct }}",
    "related_case":  "={{ $json.related_case }}",
    "sender_id":     "={{ $json.created_by_telegram_id }}",
    "source":        "telegram",
    "source_msg_id": "={{ $('Telegram Trigger').first().json.message.message_id }}",
    "status":        "scheduled",
}

CALENDAR_EVENT_SCHEMA_IDS = [
    "id", "title", "description", "start_at", "end_at", "location",
    "attendees", "related_tct", "related_case", "source", "source_msg_id",
    "sender_id", "status", "remind_before", "created_at", "updated_at", "client_id",
]


def _build_schema(ids, removed_ids=None, required_ids=None):
    removed_ids = set(removed_ids or [])
    required_ids = set(required_ids or [])
    out = []
    for i in ids:
        out.append({
            "id": i,
            "type": "string",
            "display": True,
            "removed": i in removed_ids,
            "required": i in required_ids,
            "displayName": i,
            "defaultMatch": (i == "id"),
            "canBeUsedToMatch": True,
        })
    return out


def main():
    conn = psycopg2.connect(**DSN)
    conn.autocommit = False
    cur = conn.cursor()

    # ── Part 3: schema change FIRST (so Log Conversation patch can reference it) ─
    cur.execute("""
        ALTER TABLE conversations
        ADD COLUMN IF NOT EXISTS raw_llm_output text;
    """)
    print(" - conversations: raw_llm_output column ensured")

    # ── Patch workflow JSON ──────────────────────────────────────────────────────
    cur.execute("SELECT id, nodes::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes = cur.fetchone()

    changes = []
    for n in nodes:
        name = n.get("name")

        if name == "Insert Chat Note":
            n["parameters"]["columns"]["value"] = CHAT_NOTE_COLS
            n["parameters"]["columns"]["schema"] = _build_schema(
                CHAT_NOTE_SCHEMA_IDS,
                removed_ids=["id", "related_entity_id", "related_event_id", "created_at", "client_id"],
                required_ids=["content"],
            )
            changes.append("Insert Chat Note: 10 columns wired (was 1), topic coerced to enum")

        if name == "Insert Calendar Event":
            n["parameters"]["columns"]["value"] = CALENDAR_EVENT_COLS
            n["parameters"]["columns"]["schema"] = _build_schema(
                CALENDAR_EVENT_SCHEMA_IDS,
                removed_ids=["id", "attendees", "remind_before", "created_at", "updated_at", "client_id"],
                required_ids=["title", "start_at"],
            )
            changes.append("Insert Calendar Event: 11 columns wired (was 1), == typo fixed")

        if name == "Log Conversation":
            cols = n["parameters"]["columns"]["value"]
            cols["raw_llm_output"] = "={{ $('AI Agent').first().json.output }}"
            schema = n["parameters"]["columns"]["schema"]
            if not any(s.get("id") == "raw_llm_output" for s in schema):
                schema.append({
                    "id": "raw_llm_output", "type": "string", "display": True,
                    "removed": False, "required": False, "displayName": "raw_llm_output",
                    "defaultMatch": False, "canBeUsedToMatch": True,
                })
            changes.append("Log Conversation: raw_llm_output mapped (raw AI Agent output)")

    cur.execute("""
        UPDATE workflow_entity SET nodes = %s::jsonb, "updatedAt" = now() WHERE id = %s
    """, (json.dumps(nodes), wf_id))
    conn.commit()

    for c in changes:
        print(" -", c)
    print(f"\nworkflow_entity row updated (id={wf_id})")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
