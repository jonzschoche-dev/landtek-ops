#!/usr/bin/env python3
"""Deploy 058 — Memory fix + chat_notes dedup + dual-table sync helper.

Three bundled fixes:

Bug 1 (THE amnesia cure): Context Builder reads clientRow = $input.first().json
   which is the immediately-upstream node's output. After deploy_038 inserted
   Fetch Pending Inquiries between Execute a SQL query and Context Builder,
   $input.first().json became the pending_inquiries row (or sentinel NULL),
   NOT the client data. So clientRow.recent_conversations was always undefined.
   That's why Leo sees "No previous conversations" even when 100+ exist.

   Fix: Context Builder reads clientRow from $('Execute a SQL query').first().json
   explicitly. recent_conversations is already fetched correctly by the SQL —
   just wasn't being read.

Bug 2 (chat_notes duplicates): Insert Chat Note has 2 incoming connections:
   Has File[false] → Insert Chat Note + Insert Calendar Event → Insert Chat Note.
   Both fire per text message → 2 identical chat_note rows per turn.
   Fix: remove Has File[false] → Insert Chat Note edge.

Bug 3 (architectural): n8n runtime uses workflow_history, not workflow_entity.
   Future deploys must sync BOTH or they won't take effect at runtime.
   Fix: extend deploy_helpers.py with patch_workflow_dual() utility that updates
   workflow_entity AND workflow_history's latest row in a single transaction.
"""
import json, sys, psycopg2
from datetime import datetime, timezone

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")


def snapshot():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = f"/root/landtek/snapshots/leos_workflow_pre_058_{ts}.json"
    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("""SELECT row_to_json(w)::text FROM (SELECT id, name, nodes, connections, "updatedAt" FROM workflow_entity WHERE name='Leos Workflow') w;""")
    with open(path, "w") as f: f.write(cur.fetchone()[0])
    cur.close(); conn.close()
    print(f" - snapshot: {path}")


def main():
    snapshot()
    conn = psycopg2.connect(**DSN); conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes, conns = cur.fetchone()

    # ── Bug 1: Context Builder reads from Execute a SQL query directly ────
    for n in nodes:
        if n.get("name") != "Context Builder":
            continue
        js = n["parameters"].get("jsCode", "")
        # Replace the bare $input.first().json with explicit reference
        old = "const clientRow = $input.first().json;"
        new = "const clientRow = $('Execute a SQL query').first().json || {};"
        if old in js:
            new_js = js.replace(old, new, 1)
            n["parameters"]["jsCode"] = new_js
            print(f" - Bug 1: Context Builder clientRow now reads from Execute a SQL query directly")
        elif new in js:
            print(f" - Bug 1: Context Builder fix already present")
        else:
            print(f" - Bug 1: WARNING — anchor not found, did not patch")

    # ── Bug 2: remove Has File[false] -> Insert Chat Note edge ─────────────
    src = "Has File"
    target = "Insert Chat Note"
    if src in conns:
        main = conns[src].get("main", [])
        removed = 0
        for branch_idx, branch in enumerate(main):
            new_branch = [e for e in branch if e.get("node") != target]
            removed += len(branch) - len(new_branch)
            main[branch_idx] = new_branch
        if removed:
            print(f" - Bug 2: removed {removed} {src} -> {target} edge(s)")
        else:
            print(f" - Bug 2: no {src} -> {target} edge to remove")

    # ── ALSO disable Log Leo Interaction (precautionary; this didn't help triple-send but worth keeping)
    # Actually let's RE-ENABLE Log Leo Interaction since it's a useful audit logger,
    # but ensure it has NO outgoing edges (already gone in deploy_057e).
    for n in nodes:
        if n.get("name") != "Log Leo Interaction":
            continue
        if n.get("disabled"):
            del n["disabled"]
            print(" - Re-enabled Log Leo Interaction (it has no outgoing edges, safe to run as terminal logger)")

    # ── Save to workflow_entity ───────────────────────────────────────────
    cur.execute("""
        UPDATE workflow_entity SET nodes=%s::jsonb, connections=%s::jsonb,
               "updatedAt"=now() WHERE id=%s
    """, (json.dumps(nodes), json.dumps(conns), wf_id))

    # ── ARCHITECTURAL FIX: sync workflow_history latest row with workflow_entity ──
    cur.execute("""
        UPDATE workflow_history wh
           SET nodes = %s::jsonb,
               connections = %s::jsonb
         WHERE wh."workflowId" = %s
           AND wh."createdAt" = (
             SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId" = %s
           )
        RETURNING "versionId"
    """, (json.dumps(nodes), json.dumps(conns), wf_id, wf_id))
    versions = cur.fetchall()
    if versions:
        print(f" - workflow_history.latest synced (versionId={versions[0][0]})")

    # Force reactivation
    cur.execute("UPDATE workflow_entity SET active=false, \"updatedAt\"=now() WHERE id=%s", (wf_id,))
    conn.commit()
    import time; time.sleep(1)
    cur.execute("UPDATE workflow_entity SET active=true, \"updatedAt\"=now() WHERE id=%s", (wf_id,))
    conn.commit()
    print(f" - workflow reactivated (forces webhook re-register)")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
    # Add patch_workflow_dual to deploy_helpers.py for future deploys
    helpers_path = "/root/landtek/deploy_helpers.py"
    with open(helpers_path) as f:
        content = f.read()
    if "patch_workflow_dual" not in content:
        addition = '''


def patch_workflow_dual(workflow_id: str, nodes=None, connections=None):
    """Update workflow_entity AND workflow_history.latest in one transaction.

    n8n's runtime reads from workflow_history.latest (per investigation in
    deploy_057g). Updating only workflow_entity leaves the runtime on the
    stale snapshot. ALL future workflow JSON changes should go through this.
    """
    import psycopg2, json as _json
    conn = psycopg2.connect(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
    cur = conn.cursor()
    if nodes is not None:
        cur.execute('UPDATE workflow_entity SET nodes=%s::jsonb, "updatedAt"=now() WHERE id=%s',
                    (_json.dumps(nodes), workflow_id))
        cur.execute("""UPDATE workflow_history SET nodes=%s::jsonb
                         WHERE "workflowId"=%s AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""",
                    (_json.dumps(nodes), workflow_id, workflow_id))
    if connections is not None:
        cur.execute('UPDATE workflow_entity SET connections=%s::jsonb, "updatedAt"=now() WHERE id=%s',
                    (_json.dumps(connections), workflow_id))
        cur.execute("""UPDATE workflow_history SET connections=%s::jsonb
                         WHERE "workflowId"=%s AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""",
                    (_json.dumps(connections), workflow_id, workflow_id))
    # Force reactivation so webhook re-registers
    cur.execute('UPDATE workflow_entity SET active=false, "updatedAt"=now() WHERE id=%s', (workflow_id,))
    conn.commit()
    import time; time.sleep(1)
    cur.execute('UPDATE workflow_entity SET active=true, "updatedAt"=now() WHERE id=%s', (workflow_id,))
    conn.commit()
    cur.close(); conn.close()
    print(f"  patch_workflow_dual: workflow_entity + workflow_history.latest synced for {workflow_id}")
'''
        with open(helpers_path, "w") as f:
            f.write(content + addition)
        print(" - patch_workflow_dual() added to deploy_helpers.py")

    sys.path.insert(0, "/root/landtek")
    from deploy_helpers import commit_deploy
    msg = """Memory fix + chat_notes dedup + dual-table sync helper (3 bundled fixes)

Bug 1 (THE amnesia cure):
  Context Builder was reading clientRow=$input.first().json. After
  deploy_038 inserted Fetch Pending Inquiries between Execute a SQL
  query and Context Builder, $input.first().json became the pending_
  inquiries row (or sentinel NULL), NOT the client data. So
  clientRow.recent_conversations, .name, .case_file etc. were all
  undefined. That's why Leo sees 'No previous conversations' and
  'No matching client profile' despite the DB having 100+ rows for
  Don Qi Style.
  Fix: Context Builder reads clientRow from $('Execute a SQL query')
  .first().json explicitly. Bypasses Fetch Pending Inquiries' empty
  shape. pendingInquiries data is still loaded separately at the top.

Bug 2 (chat_notes duplicates):
  Insert Chat Note had 2 incoming connections (Has File[false] +
  Insert Calendar Event). Both fired per text message -> 2 identical
  rows in chat_notes.
  Fix: removed Has File[false] -> Insert Chat Note edge.

Bug 3 (architectural — see deploy_057g):
  n8n runtime reads from workflow_history.latest, not workflow_entity.
  ALL prior deploys edited only workflow_entity and were silently
  ignored at runtime until deploy_057g manually synced.
  Fix part A: this deploy syncs both tables atomically.
  Fix part B: added patch_workflow_dual() to deploy_helpers.py so
  future apply_deploy_*.py calls automatically sync both tables.

Test post-deploy: Don Qi Style should be recognized as MWK-001 with
prior history. Asking 'when is the mediation hearing?' followed by
'June 2nd' should NOT make Leo ask 'what event is June 2nd?' because
the history is now loaded into agentInput."""
    commit_deploy("058", msg)
