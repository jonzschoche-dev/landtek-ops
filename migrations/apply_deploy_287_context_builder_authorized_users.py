#!/usr/bin/env python3
"""Deploy 287 — add authorized_users_directory to Leo's Context Builder so
the AI Agent ALWAYS knows who is registered + their Telegram IDs.

Symptom (transcript 9:09–9:23 May 28): Leo repeatedly asked Jonathan for
Kristyle's Telegram ID, full name, phone, and email — when all of that
already lives in authorized_users (id=2, name='Joy Kristyle',
telegram_user_id='5992075757', role='filing_assistant', active=true).

Root cause: the 'Execute a SQL query' node (Context Builder source) loads
11 JSON aggregates but does NOT query authorized_users. Leo therefore has
no schema awareness of who is registered.

Fix: append an authorized_users_directory aggregate to the SQL. The
Context Builder node downstream of it already passes c.* to agentInput,
so a new column on the same SELECT gets surfaced automatically.

Also adds an unauth_attempts_24h aggregate so Leo can see fresh unauth
traffic (the joykristyle 6-attempt thread tonight) without needing to be
asked.
"""
import json
import psycopg2
import psycopg2.extras

WORKFLOW_ID = "vSDQv1vfn6627bnA"

DIRECTORY_SQL = """,
  -- AUTHORIZED USERS DIRECTORY (deploy_287) — Leo must always know who is registered
  (
    SELECT json_agg(au ORDER BY id)
    FROM (
      SELECT id, telegram_user_id, name, role,
             can_transcribe, can_verify, can_admin,
             active, created_at::date AS created_date
        FROM authorized_users
       WHERE active = true
       ORDER BY id
    ) au
  ) as authorized_users_directory,
  -- RECENT UNAUTH TRAFFIC (deploy_287) — surface non-Jonathan inbound so Leo knows context
  (
    SELECT json_agg(ua ORDER BY attempted_at DESC)
    FROM (
      SELECT id, telegram_id, first_name, username, message_text,
             attempted_at::timestamp(0)
        FROM unauth_attempts
       WHERE attempted_at > now() - INTERVAL '7 days'
       ORDER BY attempted_at DESC
       LIMIT 15
    ) ua
  ) as recent_unauth_attempts_7d"""

conn = psycopg2.connect("postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
conn.autocommit = False
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
cur.execute("SELECT nodes FROM workflow_entity WHERE id=%s FOR UPDATE", (WORKFLOW_ID,))
nodes = cur.fetchone()["nodes"]

patched = False
for n in nodes:
    if n.get("name") != "Execute a SQL query":
        continue
    params = n.setdefault("parameters", {})
    sql = params.get("query") or params.get("sqlExpression") or ""

    if "authorized_users_directory" in sql:
        print("Already patched — authorized_users_directory already present.")
        raise SystemExit(0)

    # Insert before "FROM clients c" (the source table). We do this by anchoring
    # on the closing of the last selected aggregate before FROM.
    anchor = "FROM clients c"
    if anchor not in sql:
        print(f"FAIL: could not find anchor {anchor!r} in SQL")
        raise SystemExit(1)
    idx = sql.find(anchor)
    new_sql = sql[:idx] + DIRECTORY_SQL.lstrip(",").strip() + "\n  " + sql[idx:]
    # Actually need leading comma if there's a preceding SELECT clause
    new_sql = sql[:idx].rstrip().rstrip(",") + DIRECTORY_SQL + "\n  " + sql[idx:]

    # Save back
    if "query" in params:
        params["query"] = new_sql
    else:
        params["sqlExpression"] = new_sql
    patched = True
    print(f"Patched. Old SQL length: {len(sql)}  New: {len(new_sql)}")
    break

if not patched:
    print("Execute a SQL query node not found")
    raise SystemExit(1)

cur.execute(
    'UPDATE workflow_entity SET nodes=%s, "updatedAt"=now() WHERE id=%s',
    (json.dumps(nodes), WORKFLOW_ID),
)
conn.commit()
print("DB UPDATED")
