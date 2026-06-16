#!/usr/bin/env python3
"""leo_wire_protocol.py — prepend the discernment protocol into Leo's AI-Agent systemMessage.

Step 1 of leo_wiring_runbook.md. The retrieve-before discipline that makes Leo reason from the
record. It only PREPENDS — the entire existing systemMessage (incl. the S1-S4 + S14 sim safety
rules) is preserved by construction (new = protocol + separator + old). Snapshot-first (via
backup_workflow.py), idempotent (skips if the marker is already present), dry-runnable. $0, no LLM.
The workflow is inactive, so this is safe with no live traffic; it takes effect on next activation.

  python3 scripts/leo_wire_protocol.py --dry      # show the plan, change nothing
  python3 scripts/leo_wire_protocol.py --apply     # backup_workflow first, then patch + verify
"""
import argparse
import json
import os
import subprocess
import sys

import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
WF = "vSDQv1vfn6627bnA"
AGENT_NODE = "AI Agent"
PROTO_MD = "/root/landtek/leo_discernment_protocol.md"
MARKER = "GROUNDING DISCIPLINE"          # idempotency sentinel (unique to the protocol block)
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_protocol():
    with open(PROTO_MD) as f:
        txt = f.read()
    parts = txt.split("```")
    if len(parts) < 3:
        sys.exit(f"no fenced protocol block found in {PROTO_MD}")
    block = parts[1].strip()
    if MARKER not in block:
        sys.exit(f"first fenced block in {PROTO_MD} does not contain the '{MARKER}' marker")
    return block


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    proto = load_protocol()

    conn = psycopg2.connect(DSN); conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SELECT nodes FROM workflow_entity WHERE id=%s", (WF,))
    row = cur.fetchone()
    if not row:
        sys.exit(f"workflow {WF} not found")
    nodes = row[0] if not isinstance(row[0], str) else json.loads(row[0])
    agent = next((n for n in nodes if n.get("name") == AGENT_NODE), None)
    if not agent:
        sys.exit(f"node '{AGENT_NODE}' not found")
    opts = agent.setdefault("parameters", {}).setdefault("options", {})
    sm = opts.get("systemMessage", "")

    print(f"[plan] systemMessage current len={len(sm)} | protocol len={len(proto)}")
    print(f"[plan] present now — protocol={MARKER in sm} | Rule S1={'Rule S1' in sm} | S14={'S14' in sm}")
    if MARKER in sm:
        print("[plan] protocol already present — idempotent no-op."); return

    new_sm = proto + "\n\n---\n\n" + sm
    # preservation guarantees (prepend-only): the entire old prompt + sim rules survive verbatim
    assert sm in new_sm and "Rule S1" in new_sm and "S14" in new_sm and MARKER in new_sm
    print(f"[plan] new len={len(new_sm)} (protocol + separator + full existing prompt preserved)")

    if not a.apply or a.dry:
        print("[dry] nothing written. Re-run with --apply to snapshot + patch.")
        return

    print("[apply] snapshot first ...")
    subprocess.run([sys.executable, os.path.join(REPO, "scripts", "backup_workflow.py"),
                    WF, "pre_wire_protocol"], check=True)
    opts["systemMessage"] = new_sm
    cur.execute('UPDATE workflow_entity SET nodes=%s::json, "updatedAt"=now() WHERE id=%s',
                (json.dumps(nodes), WF))
    conn.commit()

    # verify on disk: protocol present, sim rules intact, length grew by the protocol+sep
    cur.execute("""SELECT length(coalesce(n->'parameters'->'options'->>'systemMessage','')),
                          (n::text ILIKE '%GROUNDING DISCIPLINE%')::int,
                          (n::text ILIKE '%Rule S1%')::int, (n::text ILIKE '%S14%')::int
                   FROM workflow_entity w, json_array_elements(w.nodes) n
                   WHERE w.id=%s AND n->>'name'=%s""", (WF, AGENT_NODE))
    ln, mk, s1, s14 = cur.fetchone()
    print(f"[apply] DONE. on-disk systemMessage len={ln} | protocol={bool(mk)} S1={bool(s1)} S14={bool(s14)}")
    if not (mk and s1 and s14):
        print("[apply] ⚠ verification FAILED — restore from the snapshot in workflow_backups/")
        sys.exit(1)
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
