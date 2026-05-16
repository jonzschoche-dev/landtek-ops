#!/usr/bin/env python3
"""Deploy 056 — Safe Reply HTML escape.

Bug: Reply to Jonathan + Reply to Client run with parse_mode=HTML. Leo's
telegram_summary_for_jonathan and telegram_reply_to_client occasionally
contain <, >, or & characters (e.g. when quoting a filename like
"<Application>" or a comparison like "amount > 500"). Telegram's HTML
parser rejects these as malformed entities and returns
  "Bad Request: can't parse entities: Can't find end of the entity..."

This kills the entire execution (NodeApiError propagates up), preventing
the parallel Insert chains from running, which is why deploy_055's
persistence fix hasn't actually delivered rows yet.

Fix: Add HTML-entity escaping to sanitizeTelegramText() in the Safe Reply
node. Order matters: & must be escaped FIRST (otherwise we'd double-escape
the & we just inserted for < and >).

Why we don't switch parse_mode to plain: HTML mode is currently used for
basic formatting downstream (the previous Markdown-underscore bug pushed
us off Markdown to HTML in deploy_032).
"""
import json
import sys
import psycopg2
from datetime import datetime, timezone

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")


def snapshot():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = f"/root/landtek/snapshots/leos_workflow_pre_056_{ts}.json"
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    cur.execute("""
        SELECT row_to_json(w)::text
          FROM (SELECT id, name, nodes, connections, "updatedAt"
                  FROM workflow_entity WHERE name='Leos Workflow') w;
    """)
    with open(path, "w") as f:
        f.write(cur.fetchone()[0])
    cur.close(); conn.close()
    print(f" - snapshot: {path}")


def main():
    snapshot()
    conn = psycopg2.connect(**DSN)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes = cur.fetchone()

    for n in nodes:
        if n.get("name") != "Safe Reply":
            continue
        js = n["parameters"].get("jsCode", "")
        if "&amp;" in js:
            print(" - Safe Reply: HTML escapes already present, skipping")
            return
        # Inject the 3 HTML-entity escapes at the TOP of sanitizeTelegramText.
        # & must be escaped FIRST to avoid double-escaping the entities we add for < and >.
        old_block = (
            "function sanitizeTelegramText(text) {\n"
            "      if (!text) return text;\n"
            "      return text\n"
            "          .replace(/\\[/g, '(')\n"
            "                .replace(/\\]/g, ')')\n"
            "                .replace(/`/g, \"'\");\n"
            "}"
        )
        new_block = (
            "function sanitizeTelegramText(text) {\n"
            "      if (!text) return text;\n"
            "      // HTML entities must be escaped first (Telegram parse_mode=HTML).\n"
            "      // & must be replaced BEFORE < and > to avoid double-escaping.\n"
            "      return text\n"
            "          .replace(/&/g, '&amp;')\n"
            "          .replace(/</g, '&lt;')\n"
            "          .replace(/>/g, '&gt;')\n"
            "          .replace(/\\[/g, '(')\n"
            "          .replace(/\\]/g, ')')\n"
            "          .replace(/`/g, \"'\");\n"
            "}"
        )
        if old_block in js:
            new_js = js.replace(old_block, new_block, 1)
            n["parameters"]["jsCode"] = new_js
            print(f" - Safe Reply: HTML escapes added ({len(js)} -> {len(new_js)} chars)")
        else:
            # Fallback: brute-force inject after the if-empty check
            anchor = "if (!text) return text;\n"
            if anchor in js:
                inject = (
                    "if (!text) return text;\n"
                    "      // HTML entities (Telegram parse_mode=HTML) — & FIRST to avoid double-escape\n"
                    "      text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');\n"
                )
                new_js = js.replace(anchor, inject, 1)
                n["parameters"]["jsCode"] = new_js
                print(f" - Safe Reply: HTML escapes added via fallback injection ({len(js)} -> {len(new_js)} chars)")
            else:
                raise RuntimeError("Safe Reply: neither expected old_block nor anchor found")

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
    msg = """Safe Reply HTML escape — unblocks Reply to Jonathan

Telegram parse_mode=HTML rejects <, >, & in message text as
malformed entities, returning Bad Request 400. This was killing
Reply to Jonathan and preventing parallel Insert chains from
running (which is why deploy_055's persistence fix hasn't
landed rows yet).

Fix: extend sanitizeTelegramText() in Safe Reply to escape:
  & -> &amp;   (must be first)
  < -> &lt;
  > -> &gt;

Order matters: & FIRST so we don't double-escape the entities
we add for < and >.

Test post-deploy: send a message where Leo's reply contains
'<' or '>' or '&'. Reply to Jonathan should succeed (no
parse-entities 400). Insert chains should then run, populating
action_items / chat_notes / calendar_events."""
    commit_deploy("056", msg)
