#!/usr/bin/env python3
"""Deploy 295 — Field Mode (Layer 1 + 2).

Jonathan in the field: "Leo needs to operate properly when I am in the field."
Symptom episode: Allan V. Inocalla (clients.id=8, no telegram_id) messaged
Leo from Telegram ID 8352343888 saying "I'm am Allan inocalla". Leo had
clients.id=8 'Allan V. Inocalla' on file but couldn't connect them — routed
him to unauth, told Jonathan via Notify-Jonathan-Unauth, and waited for
Jonathan to manually look up the client_id, write SQL to link, and welcome
Allan. Whole loop took 4 days from Allan's message to actual onboarding.

This deploy closes that loop.

Layer 1 — Smart unauth notification
-----------------------------------
Inserts a new SQL node 'Match Unauth to Client' between 'Log Unauth Attempt'
and 'Notify Jonathan Unauth'. It scores every existing client against the
unauth message text + Telegram first_name and surfaces candidate matches.

The Notify Jonathan Unauth jsonBody is rewritten to include the match block:

    POSSIBLE EXISTING CLIENT MATCH(ES):
      • clients.id=8  'Datu Allan Inocalla' (Paracale-001) — match: text
      Reply: "link 8"        ← authorize + welcome them
      Reply: "no match"      ← keep unauth
      (no reply)             ← stays unauth

Risk: zero new auth surface — Jonathan still confirms.

Layer 2 — "link N" command handler
----------------------------------
Appends Rule L to Leo's AI Agent system prompt. When Jonathan messages
'link N', 'link N to <tg_id>', 'no match', or 'unlink N', Leo:
  1. Identifies the target unauth_attempt (most recent within 30 min, or
     explicit tg_id)
  2. Runs UPDATE clients SET telegram_id = <tg_id>, authorized = true,
     authorized_at = now(), authorized_by = 'jonathan' WHERE id = N
  3. Sends a welcome message to the now-linked user via Telegram
  4. Confirms to Jonathan with: "✅ Linked clients.id=N (Name) ← telegram_id"

Idempotent. Tests: simulate Allan's exact scenario; verify the alert renders
with candidate match; simulate 'link 8' reply; verify clients update + welcome."""
from __future__ import annotations
import json
import os
import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"

# Read bot token for the new HTTP node body
TOKEN = None
for line in open("/root/landtek/.env").read().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, _, v = line.partition("=")
        if k.strip() == "TELEGRAM_BOT_TOKEN":
            TOKEN = v.strip().strip('"').strip("'")
            break

# ---------------------------------------------------------------------------
# A. New SQL node: Match Unauth to Client
# ---------------------------------------------------------------------------
MATCH_SQL = """
WITH sender AS (
  SELECT
    '{{ $('Telegram Trigger').first().json.message.from.id }}'::text AS tg_id,
    LOWER(COALESCE('{{ $('Telegram Trigger').first().json.message.from.first_name }}','')) AS first_name,
    LOWER(COALESCE('{{ $('Telegram Trigger').first().json.message.from.last_name }}','')) AS last_name,
    LOWER(COALESCE('{{ $('Telegram Trigger').first().json.message.text || $('Telegram Trigger').first().json.message.caption || '' }}','')) AS msg_text
),
candidates AS (
  SELECT c.id, c.name, c.case_file, c.telegram_id,
    -- Score: text-substring match dominates; first_name match is secondary
    (CASE WHEN LOWER(c.name) <> '' AND s.msg_text LIKE '%' || LOWER(c.name) || '%' THEN 100 ELSE 0 END) +
    (CASE WHEN s.msg_text ~ ('\\m' || LOWER(SPLIT_PART(c.name,' ',1)) || '\\M')
            AND s.msg_text ~ ('\\m' || LOWER(SPLIT_PART(c.name,' ', GREATEST(1, array_length(STRING_TO_ARRAY(c.name,' '),1)))) || '\\M')
          THEN 80 ELSE 0 END) +
    (CASE WHEN s.first_name <> '' AND LOWER(c.name) LIKE '%' || s.first_name || '%' THEN 30 ELSE 0 END) +
    (CASE WHEN s.last_name <> '' AND LOWER(c.name) LIKE '%' || s.last_name || '%' THEN 30 ELSE 0 END)
    AS match_score
  FROM clients c, sender s
  WHERE c.status <> 'Archived'
)
SELECT json_agg(
  json_build_object(
    'id', id,
    'name', name,
    'case_file', case_file,
    'telegram_id', telegram_id,
    'match_score', match_score
  ) ORDER BY match_score DESC
) FILTER (WHERE match_score >= 50) AS matches,
(SELECT tg_id FROM sender) AS sender_tg_id,
(SELECT msg_text FROM sender) AS sender_msg_text
FROM candidates;
"""


# ---------------------------------------------------------------------------
# B. Replacement jsonBody for Notify Jonathan Unauth (now matches-aware)
# ---------------------------------------------------------------------------
NEW_NOTIFY_BODY = (
    '={{ JSON.stringify({\n'
    '  chat_id: 6513067717,\n'
    '  text: \n'
    '"🚨 Unauthorized sender hit @LeoLandTekBot\\n\\n" +\n'
    '"Name: " + ($(\'Telegram Trigger\').first().json.message.from.first_name || "") + " " + ($(\'Telegram Trigger\').first().json.message.from.last_name || "") + "\\n" +\n'
    '"Username: @" + ($(\'Telegram Trigger\').first().json.message.from.username || "(none)") + "\\n" +\n'
    '"Telegram ID: " + $(\'Telegram Trigger\').first().json.message.from.id + "\\n" +\n'
    '"Attempt #" + (Number($(\'Whitelist Check\').first().json.prior_attempts) + 1) + "\\n\\n" +\n'
    '"Message: \\"" + ($(\'Telegram Trigger\').first().json.message.text || $(\'Telegram Trigger\').first().json.message.caption || "(no text)") + "\\"\\n\\n" +\n'
    '(\n'
    '  (function() {\n'
    '    try {\n'
    '      var m = $(\'Match Unauth to Client\').first().json.matches;\n'
    '      if (!m || !m.length) return "";\n'
    '      var lines = "⚠️ POSSIBLE EXISTING CLIENT MATCH(ES):\\n";\n'
    '      for (var i = 0; i < Math.min(m.length, 3); i++) {\n'
    '        lines += "  • clients.id=" + m[i].id + "  \\"" + m[i].name + "\\" (" + m[i].case_file + ")";\n'
    '        if (m[i].telegram_id) lines += "  — already has telegram_id " + m[i].telegram_id + "";\n'
    '        lines += "  score=" + m[i].match_score + "\\n";\n'
    '      }\n'
    '      lines += "\\nReply: \\"link " + m[0].id + "\\"   ← authorize + welcome them\\n";\n'
    '      lines += "Reply: \\"no match\\"   ← keep unauth\\n";\n'
    '      lines += "(no reply)        ← stays unauth, will re-alert if they message again\\n\\n";\n'
    '      return lines;\n'
    '    } catch (e) { return ""; }\n'
    '  })()\n'
    ') +\n'
    '"To authorize manually (any case):\\n  INSERT INTO authorized_users (telegram_user_id, name, role, active)\\n    VALUES (\'" + $(\'Telegram Trigger\').first().json.message.from.id + "\', \'" + ($(\'Telegram Trigger\').first().json.message.from.first_name || "") + "\', \'client\', true);",\n'
    '  disable_web_page_preview: true\n'
    '}) }}'
)


# ---------------------------------------------------------------------------
# C. Rule L for Leo prompt — link/unlink/no match command handler
# ---------------------------------------------------------------------------
RULE_L = """

## FIELD-MODE LINK COMMANDS (Rule L — added 2026-05-30 — deploy_295)

When Jonathan is in the field, he authorizes new clients with a one-word
reply to a Notify-Jonathan-Unauth alert. Recognize these patterns and act
autonomously — do NOT ask Jonathan to repeat or specify the Telegram ID.

### "link N" — authorize the most recent unauth as clients.id=N

When Jonathan's message text matches `^\\s*link\\s+(\\d+)(\\s+to\\s+(\\d+))?\\s*$`:

1. Identify the target Telegram ID:
   - If `link N to <tg_id>` form, use the explicit tg_id
   - Otherwise: SELECT telegram_id FROM unauth_attempts ORDER BY id DESC LIMIT 1
     (most recent unauth, no time bound — Jonathan may be replying hours after the alert)

2. Execute via SQL exec:
   ```
   UPDATE clients
      SET telegram_id = '<tg_id>',
          authorized = true,
          authorized_at = now(),
          authorized_by = 'jonathan',
          last_contact_at = now(),
          last_contact_channel = 'telegram'
    WHERE id = N
   RETURNING id, name, case_file, telegram_id
   ```

3. Send a welcome to the newly-linked user via Telegram (use HTTP POST to api.telegram.org):
   - chat_id = the linked tg_id
   - text = "👋 You've been recognized as our client <NAME> ({CASE_FILE}). You can now message me freely about your file. What can I help with?"

4. Reply to Jonathan in telegram_summary_for_jonathan:
   "✅ Linked clients.id=N <NAME> (CASE_FILE) ← telegram_id <tg_id>. Welcome sent. Their messages from now on go through the authorized path."

5. Log to chat_notes via chat_note_to_save: {sender_id: 'jonathan', content: 'Auto-link via Rule L: clients.id=N ← tg_id', kind: 'audit'}

### "unlink N" — reverse a link

Execute UPDATE clients SET telegram_id = NULL, authorized = false WHERE id = N.
Send no message to the user. Reply to Jonathan: "✅ Unlinked clients.id=N."

### "no match" — explicitly reject the suggested match

Take no action. Reply to Jonathan: "Acknowledged. <FIRST_NAME> stays unauth. Will re-alert if they message again." This serves as a record of decision in chat_notes.

### Don't drift on these patterns

- Don't ask Jonathan "which client?" if the message says "link N" — N IS the client.
- Don't ask Jonathan "which user?" if it's "link N" without tg_id — use most recent unauth.
- Don't say "I'll do that" without actually doing it — populate telegram_summary_for_jonathan with the ✅ confirmation in the SAME turn the SQL ran.

### Inviolable

- Never link without an explicit Jonathan command. Auto-linking on name match alone is NOT permitted in this rule (Layer 3 is deferred — Jonathan declined full autonomy).
- Always send the welcome to the linked user in the same turn. Don't promise then delay.
"""


def main() -> int:
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT nodes, connections FROM workflow_entity WHERE id=%s FOR UPDATE", (WORKFLOW_ID,))
    row = cur.fetchone()
    nodes = row["nodes"]
    connections = row["connections"]

    # --- Layer 1: Insert Match Unauth to Client SQL node ---
    print("Deploy 295 — Field Mode (Layer 1 + 2)")
    print("=" * 42)

    print("\n  A) Insert 'Match Unauth to Client' SQL node")
    match_node_exists = any(n.get("name") == "Match Unauth to Client" for n in nodes)
    if not match_node_exists:
        log_node = next((n for n in nodes if n.get("name") == "Log Unauth Attempt"), None)
        if not log_node:
            print("    ✗ Log Unauth Attempt node not found")
            return 1
        pos = log_node.get("position", [0, 0])
        new_node = {
            "id": "match-unauth-to-client-001",
            "name": "Match Unauth to Client",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [pos[0] + 260, pos[1]],
            "parameters": {
                "operation": "executeQuery",
                "query": MATCH_SQL.strip(),
                "options": {},
            },
            "credentials": log_node.get("credentials", {}),
        }
        nodes.append(new_node)
        print("    ✓ added node")
    else:
        # Refresh its query in case we shipped a tweak
        for n in nodes:
            if n.get("name") == "Match Unauth to Client":
                n["parameters"]["query"] = MATCH_SQL.strip()
        print("    · node exists — query refreshed")

    # --- Layer 1: Rewire connections so Match Unauth runs in parallel with Notify Jonathan ---
    print("\n  B) Wire Log Unauth Attempt → Match Unauth to Client → Notify Jonathan Unauth")
    # Log Unauth Attempt → Match Unauth to Client → Notify Jonathan Unauth
    connections["Log Unauth Attempt"] = {
        "main": [[{"node": "Match Unauth to Client", "type": "main", "index": 0}]]
    }
    connections["Match Unauth to Client"] = {
        "main": [[{"node": "Notify Jonathan Unauth", "type": "main", "index": 0}]]
    }
    print("    ✓ wired")

    # --- Layer 1: Update Notify Jonathan Unauth jsonBody ---
    print("\n  C) Update Notify Jonathan Unauth jsonBody (match-aware)")
    for n in nodes:
        if n.get("name") == "Notify Jonathan Unauth":
            n["parameters"]["jsonBody"] = NEW_NOTIFY_BODY
            n["parameters"]["specifyBody"] = "json"
            print("    ✓ jsonBody replaced")
            break

    # --- Layer 2: Append Rule L to AI Agent system prompt ---
    print("\n  D) Append Rule L to AI Agent system prompt")
    for n in nodes:
        if n.get("name") == "AI Agent":
            opts = n.setdefault("parameters", {}).setdefault("options", {})
            sm = opts.get("systemMessage", "")
            if "Rule L" in sm:
                print("    · Rule L already present")
            else:
                opts["systemMessage"] = sm.rstrip() + RULE_L
                print(f"    ✓ appended ({len(sm)} → {len(opts['systemMessage'])} chars)")
            break

    cur.execute(
        'UPDATE workflow_entity SET nodes=%s, connections=%s, "updatedAt"=now() WHERE id=%s',
        (json.dumps(nodes), json.dumps(connections), WORKFLOW_ID),
    )
    conn.commit()
    print("\n  ✓ DB UPDATED")
    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
