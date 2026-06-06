#!/usr/bin/env python3
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

def get_db_connection():
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)

def save_action_item(case_file, description, due_date=None, priority="medium"):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO action_items (case_file, description, due_date, priority, status, created_at)
        VALUES (%s, %s, %s, %s, 'open', NOW())
    """, (case_file, description, due_date, priority))
    conn.commit()
    cur.close()
    conn.close()

def call_leo_handle_output(event=None, note=None):
    conn = get_db_connection()
    cur = conn.cursor()
    payload = {}
    if event:
        payload["event"] = event
    if note:
        payload["note"] = note
    cur.execute("SELECT leo_handle_output(%s::jsonb)", (json.dumps(payload),))
    result = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return result

def parse_and_save(data):
    case_file = data.get("client") or data.get("case_file")
    leo_output = data.get("leo_output", {})
    saved = []

    # Save action items
    for item in leo_output.get("action_items", []):
        if isinstance(item, str):
            save_action_item(case_file, item)
            saved.append(f"action_item")
        elif isinstance(item, dict):
            save_action_item(case_file, item.get("description", ""), item.get("due_date"), item.get("priority", "medium"))
            saved.append(f"action_item")

    # Handle calendar and notes (singular)
    for event in leo_output.get("calendar_events", []):
        call_leo_handle_output(event=event)
        saved.append("calendar_event")

    for note in leo_output.get("notes", []):
        call_leo_handle_output(note=note)
        saved.append("note")

    return {"status": "processed", "case_file": case_file, "saved": saved}

if __name__ == "__main__":
    raw = sys.stdin.read().strip()
    if raw:
        print(json.dumps(parse_and_save(json.loads(raw))))
    else:
        print("parse_and_save() ready")
