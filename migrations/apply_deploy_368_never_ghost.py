#!/usr/bin/env python3
"""apply_deploy_368_never_ghost.py — supersede Rule N with a NEVER-GHOST rule.

deploy_367 was too aggressive — it told Leo to skip reply on any empty-text
trigger. Jonathan's directive 2026-06-07: "Leo cannot ghost employees or
clients ever that is unacceptable."

This rewrites Rule N: every inbound from a human (text, caption, photo,
voice, sticker, file, etc.) MUST get a reply. Only pure Telegram platform
events (members joined/left, title changes — message with NO human-
authored content of any kind) may be skipped. Default in every ambiguous
case is REPLY.

Already applied live ~03:51 UTC (snapshot 1696). Idempotent record.
"""
from __future__ import annotations
import json, os
import psycopg2

PG_DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"

OLD_START = "## Rule N — Silence on empty messages (deploy_367)"
OLD_END = "## END Rule N"

NEW_RULE = """## Rule N — NEVER ghost employees or clients (deploy_368, supersedes 367)

This is non-negotiable. EVERY inbound message from a human (Jonathan,
Kristyle, an authorized client, an unauth person reaching out) MUST get
a reply. Silence is not an option.

If the inbound has no text:
- It might be a photo, voice note, sticker, document, video, location.
  Respond to what the message IS: "Got the photo — what does this go
  with?" / "Got your file. Naming it for the vault?" / "Saw the sticker.
  Did you mean something specific?"
- Never assume blank means ignore. The human typed something or did
  something on purpose. Acknowledge it.

If the inbound is genuinely a Telegram PLATFORM event (members joined,
members left, chat title change, pinned message notice, etc.) AND there
is NO human-authored content (no text, no caption, no media), THEN it is
OK to skip the reply — those aren't messages from a person, they're
metadata about the chat. Set telegram_reply_to_client to "".

Test for skipping: only skip when the message object has NO text, NO
caption, NO photo, NO document, NO voice, NO video, NO sticker, NO
location, NO contact — basically nothing a human composed.

Default in every other case: REPLY. Even a brief one-line acknowledgment
beats silence every single time.

## END Rule N
"""


def main():
    conn = psycopg2.connect(PG_DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT nodes, connections FROM workflow_entity WHERE id = %s", (WORKFLOW_ID,))
    nodes_raw, conns_raw = cur.fetchone()
    nodes = json.loads(nodes_raw) if isinstance(nodes_raw, str) else nodes_raw
    conns_json = conns_raw if isinstance(conns_raw, str) else json.dumps(conns_raw)
    cur.execute("""INSERT INTO leo_workflow_snapshots (workflow_id, reason, nodes_json, connections_json)
        VALUES (%s,%s,%s,%s) RETURNING id""",
        (WORKFLOW_ID, "pre-deploy_368 never ghost", json.dumps(nodes), conns_json))
    print(f"snapshot: {cur.fetchone()[0]}")
    for i, n in enumerate(nodes):
        if n.get("type") == "@n8n/n8n-nodes-langchain.agent":
            sm = n["parameters"]["options"]["systemMessage"]
            if OLD_START in sm and OLD_END in sm:
                s = sm.index(OLD_START); e = sm.index(OLD_END) + len(OLD_END)
                new_sm = sm[:s] + NEW_RULE.strip() + sm[e:]
            else:
                new_sm = sm.rstrip() + "\n\n" + NEW_RULE.strip() + "\n"
            nodes[i]["parameters"]["options"]["systemMessage"] = new_sm
            print(f"systemMessage now {len(new_sm)} chars")
            break
    cur.execute('UPDATE workflow_entity SET nodes=%s, "updatedAt"=NOW() WHERE id=%s',
                (json.dumps(nodes), WORKFLOW_ID))
    print("done")


if __name__ == "__main__":
    main()
