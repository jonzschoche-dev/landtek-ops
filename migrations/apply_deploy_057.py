#!/usr/bin/env python3
"""Deploy 057 — Set Reply to Jonathan parse_mode=HTML.

Bug: Reply to Jonathan has additionalFields = {appendAttribution: false}
with NO parse_mode key. n8n's Telegram node defaults to Markdown when
parse_mode is unset. Leo's telegram_summary_for_jonathan routinely
contains underscores (e.g. "telegram_id:") which Markdown reads as
italics-start, triggering "Bad Request: can't parse entities: Can't
find end of the entity..."

deploy_032 was supposed to set parse_mode=HTML on this node but it
appears to have either never landed or been silently reverted before
the tripwire was installed.

Fix: set additionalFields.parse_mode='HTML'. Reply to Client already
has it; this matches.

Note on the double-send symptom (originally scoped for deploy_057):
Safe Reply has 4 incoming feeds (Code in JavaScript, Log Leo Interaction,
Switch router, Update row in sheet). At least 2 fire per text-only
message -> Safe Reply runs 2x -> Reply to Jonathan & Reply to Client
both run 2x. That's a separate workflow-topology fix, deferred to
deploy_057b. This deploy just gets Reply to Jonathan working at all.
"""
import json, sys, psycopg2
from datetime import datetime, timezone

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")


def snapshot():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = f"/root/landtek/snapshots/leos_workflow_pre_057_{ts}.json"
    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("""SELECT row_to_json(w)::text FROM (SELECT id, name, nodes, connections, "updatedAt" FROM workflow_entity WHERE name='Leos Workflow') w;""")
    with open(path, "w") as f: f.write(cur.fetchone()[0])
    cur.close(); conn.close()
    print(f" - snapshot: {path}")


def main():
    snapshot()
    conn = psycopg2.connect(**DSN); conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes = cur.fetchone()

    for n in nodes:
        if n.get("name") != "Reply to Jonathan":
            continue
        af = n["parameters"].setdefault("additionalFields", {})
        old = af.get("parse_mode", "<unset>")
        af["parse_mode"] = "HTML"
        print(f" - Reply to Jonathan: parse_mode {old!r} -> 'HTML'")

    cur.execute("""
        UPDATE workflow_entity SET nodes=%s::jsonb, "updatedAt"=now() WHERE id=%s
    """, (json.dumps(nodes), wf_id))
    conn.commit()
    print(f" - workflow_entity row updated (id={wf_id})")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
    sys.path.insert(0, "/root/landtek")
    from deploy_helpers import commit_deploy
    msg = """Set Reply to Jonathan parse_mode=HTML

Reply to Jonathan had additionalFields={appendAttribution:false}
with NO parse_mode. n8n's Telegram node defaults to Markdown when
parse_mode is unset. Leo's telegram_summary_for_jonathan contains
underscores (e.g. 'telegram_id:') which Markdown reads as italics-
start, triggering 'Bad Request: can't parse entities: Can't find
end of the entity starting at byte offset 22'.

deploy_032 was supposed to set this on both Reply to Jonathan and
Reply to Client. Reply to Client has it (confirmed); Reply to
Jonathan didn't. Cause: either deploy_032 missed this node or it
was silently reverted before workflow_audit was installed.

After this deploy, Safe Reply's HTML-entity escapes (deploy_056) +
HTML parse mode means underscores, asterisks, and the entire
markdown character set become safe.

Double-send (Safe Reply 4-feed -> 2x downstream) is a separate
fix, deferred to deploy_057b."""
    commit_deploy("057", msg)
