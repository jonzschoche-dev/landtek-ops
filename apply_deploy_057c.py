#!/usr/bin/env python3
"""Deploy 057c — Fix Switch router type-mismatch on inquiry_resolution branch.

Bug: deploy_038 added a Switch router output[0] for inquiry_resolution:
    leftValue: "={{ ($json.pending_inquiry_resolution || {}).id }}"
    operator: type=string, operation=notEmpty
    options.typeValidation: strict

When Leo emits pending_inquiry_resolution.id as a NUMBER (e.g. 1, the
PG row id), strict type-validation rejects it:
    "Wrong type: '1' is a number but was expecting a string"

Switch router can't evaluate the condition -> whole node errors ->
NO branch fires -> NO reply sent -> NO persistence runs.

This is why every execution today (540, 541, 542) has been erroring
since deploy_055b. The error is at the routing layer, upstream of
everything else.

Fix: wrap the leftValue expression in String(...) for explicit
coercion. Also set typeValidation=loose on the inquiry_resolution
condition as belt-and-suspenders.
"""
import json, sys, psycopg2
from datetime import datetime, timezone

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")


def snapshot():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = f"/root/landtek/snapshots/leos_workflow_pre_057c_{ts}.json"
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
        if n.get("name") != "Switch router":
            continue
        rules = n["parameters"].get("rules", {}).get("values", [])
        for rule in rules:
            if rule.get("outputKey") != "inquiry_resolution":
                continue
            # Set typeValidation=loose on the rule's options
            conds = rule.get("conditions", {})
            opts = conds.setdefault("options", {})
            old_validation = opts.get("typeValidation", "strict")
            opts["typeValidation"] = "loose"
            print(f" - Switch router inquiry_resolution: typeValidation {old_validation!r} -> 'loose'")

            # Also coerce the leftValue to string via String(...) wrapper
            for cond in conds.get("conditions", []):
                old_lv = cond.get("leftValue", "")
                if "String(" not in old_lv and "pending_inquiry_resolution" in old_lv:
                    new_lv = "={{ String(($json.pending_inquiry_resolution || {}).id || '') }}"
                    cond["leftValue"] = new_lv
                    print(f"   leftValue: {old_lv!r}")
                    print(f"   leftValue: {new_lv!r}")

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
    msg = """Fix Switch router type-strict error on inquiry_resolution branch

Switch router output[0] (inquiry_resolution) was checking notEmpty
on pending_inquiry_resolution.id with typeValidation=strict. When
Leo emits .id as a number (PG row id), strict validation rejects
with 'Wrong type: 1 is a number but was expecting a string'.

This errors the whole Switch router -> no branch fires -> no reply
sent. Caused all 3 most recent test executions (540/541/542) to
error AFTER Parse Agent1 succeeded (post deploy_057b).

Two-part fix:
- Wrap leftValue in String(...) for explicit coercion
- Set typeValidation=loose on this rule's options

After this deploy, the Switch router routes cleanly regardless of
whether pending_inquiry_resolution.id is null, number, or string."""
    commit_deploy("057c", msg)
