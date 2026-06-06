#!/usr/bin/env python3
"""
Leo 1.0 Output Parser (Corrected + topic-coerced)
Uses correct keys for leo_handle_output(), proper priority casing,
and clamps chat_notes.topic to the allowed enum.
"""

import json
import psycopg2
import sys
import os
from datetime import datetime

DB_HOST = os.environ.get("POSTGRES_HOST", "172.18.0.3")
DB_PORT = os.environ.get("POSTGRES_PORT", "5432")
DB_NAME = os.environ.get("POSTGRES_DB", "n8n")
DB_USER = os.environ.get("POSTGRES_USER", "n8n")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "n8npassword")

ALLOWED_NOTE_TOPICS = {
    "legal_strategy", "evidence", "people", "deadlines",
    "communications", "task", "misc",
}

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD
    )

def save_action_item(case_file, description, due_date=None, priority="Medium"):
    if not description:
        return
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO action_items (case_file, description, due_date, priority, status, created_at)
        VALUES (%s, %s, %s, %s, 'open', NOW())
    """, (case_file, description, due_date, priority))
    conn.commit()
    cur.close()
    conn.close()

def coerce_note_topic(note):
    """Clamp note.topic to the allowed CHECK enum.

    If Leo emits an unrecognized topic, remap to 'misc' but preserve
    the original token by prepending [topic:<orig>] to the summary.
    """
    if not isinstance(note, dict):
        return note
    raw = (note.get("topic") or "").strip().lower()
    if raw and raw not in ALLOWED_NOTE_TOPICS:
        existing_summary = (note.get("summary") or "").strip()
        note["summary"] = f"[topic:{raw}] {existing_summary}".strip()
        note["topic"] = "misc"
    return note

def save_via_leo_handle_output(case_file, calendar_event_to_save=None, chat_note_to_save=None):
    conn = get_db_connection()
    cur = conn.cursor()
    payload = {"case_file": case_file}
    if calendar_event_to_save:
        payload["calendar_event_to_save"] = calendar_event_to_save
    if chat_note_to_save:
        payload["chat_note_to_save"] = coerce_note_topic(chat_note_to_save)

    cur.execute("SELECT leo_handle_output(%s::jsonb)", (json.dumps(payload),))
    result = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return result

def parse_leo_output(data):
    case_file = data.get("client") or data.get("case_file")
    leo_output = data.get("leo_output", {})
    results = []

    # Action Items
    for item in leo_output.get("action_items", []):
        if isinstance(item, str):
            save_action_item(case_file, item)
            results.append("action_item")
        elif isinstance(item, dict):
            save_action_item(
                case_file,
                item.get("description"),
                item.get("due_date"),
                item.get("priority", "Medium")
            )
            results.append("action_item")

    # Calendar Events
    for event in leo_output.get("calendar_events", []):
        save_via_leo_handle_output(case_file, calendar_event_to_save=event)
        results.append("calendar_event")

    # Notes
    for note in leo_output.get("notes", []):
        save_via_leo_handle_output(case_file, chat_note_to_save=note)
        results.append("note")

    return {
        "status": "success",
        "case_file": case_file,
        "processed": results
    }

if __name__ == "__main__":
    raw = sys.stdin.read().strip()
    if raw:
        try:
            data = json.loads(raw)
            result = parse_leo_output(data)
            print(json.dumps(result))
        except Exception as e:
            print(json.dumps({"status": "error", "message": str(e)}))
    else:
        print("parse_leo_output() ready")
