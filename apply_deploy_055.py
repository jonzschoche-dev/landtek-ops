#!/usr/bin/env python3
"""Deploy 055 — Fix workflow persistence pipeline (3 bugs).

Bug A: Remove "id": 0 from Insert Action Items column mapping
  (was conflicting with Postgres sequence default — PK collision on id=0)

Bug B: Rewrite Insert Chat Note column expressions to read from
  $('Parse Agent1').first().json.chat_note_to_save.* directly
  (was inheriting $json from Qdrant Write upstream → undefined fields)

Bug C: Wire Split Cal/Notes from Parse Agent1 (was orphaned).
  Also rewrite Insert Calendar Event column expressions to read from
  Parse Agent1 directly so the same context-loss bug doesn't bite it.
  Removes deploy_044 hack: Has Target Contact[false] -> Insert Chat Note

Verified pre-deploy: Leo IS emitting chat_note_to_save, calendar_event_to_save,
and action_items[] in raw_llm_output. v2.4 schema confirmed embedded.

Year-extrapolation bug (Leo defaulting to 2027 for "April 2") is real but
separate; scheduled as deploy_059 (prompt change).
"""
import json
import os
import sys
import psycopg2
from datetime import datetime, timezone

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")


def snapshot():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = f"/root/landtek/snapshots/leos_workflow_pre_055_{ts}.json"
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


CHAT_NOTE_COLS = {
    "content":          "={{ $('Parse Agent1').first().json.chat_note_to_save.content }}",
    "summary":          "={{ $('Parse Agent1').first().json.chat_note_to_save.summary }}",
    "topic":            "={{ ['legal_strategy','evidence','people','deadlines','communications','task','misc'].includes($('Parse Agent1').first().json.chat_note_to_save.topic) ? $('Parse Agent1').first().json.chat_note_to_save.topic : 'misc' }}",
    "importance":       "={{ $('Parse Agent1').first().json.chat_note_to_save.importance || 3 }}",
    "related_case":     "={{ $('Parse Agent1').first().json.chat_note_to_save.related_case || $('Parse Agent1').first().json.case_file }}",
    "related_tct":      "={{ $('Parse Agent1').first().json.chat_note_to_save.related_tct }}",
    "sender_id":        "={{ $('Context Builder').first().json.senderId }}",
    "sender_name":      "={{ $('Context Builder').first().json.senderName }}",
    "telegram_msg_id":  "={{ $('Telegram Trigger').first().json.message.message_id }}",
    "archived":         False,
}

CAL_EVENT_COLS = {
    "title":         "={{ $('Parse Agent1').first().json.calendar_event_to_save.title }}",
    "description":   "={{ $('Parse Agent1').first().json.calendar_event_to_save.description }}",
    "start_at":      "={{ $('Parse Agent1').first().json.calendar_event_to_save.start_at }}",
    "end_at":        "={{ $('Parse Agent1').first().json.calendar_event_to_save.end_at }}",
    "location":      "={{ $('Parse Agent1').first().json.calendar_event_to_save.location }}",
    "related_tct":   "={{ $('Parse Agent1').first().json.calendar_event_to_save.related_tct }}",
    "related_case":  "={{ $('Parse Agent1').first().json.calendar_event_to_save.related_case || $('Parse Agent1').first().json.case_file }}",
    "sender_id":     "={{ $('Context Builder').first().json.senderId }}",
    "source":        "telegram",
    "source_msg_id": "={{ $('Telegram Trigger').first().json.message.message_id }}",
    "status":        "scheduled",
}


def main():
    snapshot()

    conn = psycopg2.connect(**DSN)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes, conns = cur.fetchone()

    # ── Bug A: remove "id": 0 ────────────────────────────────────────────
    for n in nodes:
        if n.get("name") != "Insert Action Items":
            continue
        cols = n["parameters"].get("columns", {}).get("value", {})
        if "id" in cols:
            old = cols.pop("id")
            print(f" - Bug A: removed 'id': {old!r} from Insert Action Items")
        else:
            print(" - Bug A: 'id' already absent — skip")

    # ── Bug B: rewrite Insert Chat Note column expressions ───────────────
    for n in nodes:
        if n.get("name") != "Insert Chat Note":
            continue
        n["parameters"]["columns"]["value"] = CHAT_NOTE_COLS
        print(f" - Bug B: rewrote Insert Chat Note column expressions to read from "
              f"Parse Agent1.chat_note_to_save (10 columns)")

    # ── Bug C part 1: rewrite Insert Calendar Event column expressions ───
    for n in nodes:
        if n.get("name") != "Insert Calendar Event":
            continue
        n["parameters"]["columns"]["value"] = CAL_EVENT_COLS
        print(f" - Bug C: rewrote Insert Calendar Event column expressions to read from "
              f"Parse Agent1.calendar_event_to_save (11 columns)")

    # ── Bug C part 2: connection patches ─────────────────────────────────
    def find_edge(src, tgt, branch=0):
        if src not in conns: return None
        main = conns[src].get("main", [])
        if branch >= len(main): return None
        for i, e in enumerate(main[branch]):
            if e.get("node") == tgt: return (branch, i)
        return None

    def remove_edge(src, tgt, branch=0, label=""):
        loc = find_edge(src, tgt, branch)
        if loc is None:
            print(f"   = remove {label}: not present"); return
        b, i = loc
        del conns[src]["main"][b][i]
        print(f"   - remove {label}")

    def add_edge(src, tgt, branch=0, target_input=0, label=""):
        edge = {"node": tgt, "type": "main", "index": target_input}
        if src not in conns:
            conns[src] = {"main": [[]]}
        main = conns[src].setdefault("main", [[]])
        while len(main) <= branch:
            main.append([])
        if any(e == edge for e in main[branch]):
            print(f"   = add {label}: already present"); return
        main[branch].append(edge)
        print(f"   + add {label}")

    print(" - Connection patches:")
    add_edge("Parse Agent1", "Split Cal/Notes",
             label="Parse Agent1 -> Split Cal/Notes")
    remove_edge("Has Target Contact", "Insert Chat Note", branch=1,
                label="Has Target Contact[false] -> Insert Chat Note (deploy_044 hack)")

    cur.execute("""
        UPDATE workflow_entity SET nodes=%s::jsonb, connections=%s::jsonb,
               "updatedAt"=now() WHERE id=%s
    """, (json.dumps(nodes), json.dumps(conns), wf_id))
    conn.commit()
    print(f" - workflow_entity row updated (id={wf_id})")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
    sys.path.insert(0, "/root/landtek")
    from deploy_helpers import commit_deploy
    msg = """Fix workflow persistence pipeline (3 bugs)

- Bug A: Remove "id": 0 from Insert Action Items column mapping
  (was conflicting with Postgres sequence default)
- Bug B: Rewrite Insert Chat Note column expressions to read
  from $('Parse Agent1').first().json.chat_note_to_save.* directly
  (was inheriting $json from Qdrant Write upstream -> undefined)
- Bug C: Wire Split Cal/Notes from Parse Agent1 (was orphaned)
  Removes deploy-044 hack of feeding Insert Chat Note from
  Has Target Contact[false]

Verified pre-deploy: Leo IS emitting chat_note_to_save,
calendar_event_to_save, and action_items in raw_llm_output.
v2.4 schema confirmed embedded in System Message.

Test post-deploy: Don Qi Style "Hello, test note for team
meeting Tuesday May 19 at 2pm" should produce 1 row each in
conversations, action_items, chat_notes, calendar_events.

Year-extrapolation bug (Leo defaulting to 2027 for "April 2")
is real but separate; scheduled as deploy_059 (prompt change)."""
    commit_deploy("055", msg)
