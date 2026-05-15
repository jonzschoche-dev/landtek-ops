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

def get_recent_context(client: str, limit: int = 8):
    conn = get_db_connection()
    cur = conn.cursor()

    # Fixed column names
    cur.execute("""
        SELECT client_name, message_caption, created_at
        FROM conversations
        WHERE case_file = %s
        ORDER BY created_at DESC
        LIMIT %s
    """, (client, limit))

    messages = []
    for row in cur.fetchall():
        messages.append({
            "sender": row[0],
            "text": row[1],
            "time": row[2].isoformat() if row[2] else None
        })

    cur.execute("""
        SELECT description, due_date, priority
        FROM action_items
        WHERE case_file = %s AND status = 'open'
        ORDER BY due_date ASC NULLS LAST
        LIMIT 8
    """, (client,))

    action_items = []
    for row in cur.fetchall():
        action_items.append({
            "description": row[0],
            "due_date": row[1].isoformat() if row[1] else None,
            "priority": row[2]
        })

    cur.close()
    conn.close()

    return {
        "client": client,
        "recent_messages": messages,
        "open_action_items": action_items,
        "retrieved_at": datetime.now().isoformat()
    }

if __name__ == "__main__":
    raw = sys.stdin.read().strip()
    if raw:
        data = json.loads(raw)
        client = data.get("client")
        if client:
            print(json.dumps(get_recent_context(client), default=str))
        else:
            print(json.dumps({"error": "No client provided"}))
    else:
        print("get_recent_context() ready")
