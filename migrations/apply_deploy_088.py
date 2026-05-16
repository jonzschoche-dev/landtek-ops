#!/usr/bin/env python3
"""Deploy 088 — Resolve 'the file' to recent uploads (Jonathan's status checks).

Incident (2026-05-16 10:16 Manila):
  Don Qi uploads 2 files at 10:14. Leo logs them as DOC 689 + 690 (MWK-001).
  Jonathan: "Was the file scanned and onboarded into the proper directory?"
  Leo:      "Could you re-send the file here? I don't see any upload..."
  -> Leo had 689 + 690 in recent_documents but interpreted "the file" as a
     missing upload from Jonathan, not the recent uploads from Don Qi.

Fix: prompt clarification (Rule B subsection) — when ANY sender asks about
the status / scan / onboarding / classification of "the file" / "the upload" /
"this document" / "those files":

1. FIRST look at RECENT DOCUMENTS UPLOADED BY THIS CLIENT[0..3] — these
   are the most recent uploads (for Jonathan, across ALL clients per
   deploy_081).
2. If a recent doc is present, that IS the referent. Answer with:
   - scan status: "extracted_excerpt" length > 0 means scanned
   - directory: file_path is the on-disk location
   - case_file: the classification
   - follow-up status: were follow-ups deferred (per deploy_081)?
3. NEVER ask "could you re-send" if recent_documents has an upload from
   the last ~15 minutes.
"""
import json, os, sys, argparse, time
sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

WF_NAME = "Leos Workflow"

RULE_MARKER = "### File location & retrieval (added 2026-05-16 — deploy_081)"

RULE_ADDITION = """### File status queries — resolve referent first (added 2026-05-16 — deploy_088)

When the sender asks STATUS questions about uploads — "was the file scanned?", "did you onboard the upload?", "is this filed correctly?", "what did you see in the document?", "follow-up questions after the scan?":

**Step 1**: Identify the referent.
- The referent is the most recent doc in `RECENT DOCUMENTS UPLOADED BY THIS CLIENT[0]` (and possibly [1], [2]).
- For Jonathan (operator), recent_documents spans ALL clients — so "the file" could be a client's recent upload, NOT necessarily Jonathan's own.
- Look at the timestamp on recent_documents[0] — if it's within ~15 minutes of NOW, that IS the referent. Treat as such.

**Step 2**: Answer concretely from the doc's fields.
- **Scanned?** → extracted_excerpt non-empty + char_count > 0 means yes.
- **Onboarded / classified?** → case_file value. If "Unknown" or empty, note that classification is pending (keyword vote may run, or GPT may classify on next turn).
- **In directory?** → file_path (e.g. `/root/landtek/uploads/MWK-001/689_filename.pdf`) is the canonical location.
- **Follow-up questions asked?** → If you (Leo) deferred per the "file uploads — defer follow-up until extracted" rule (deploy_081), say so honestly: "No follow-ups yet — I deferred until extraction was complete, which it now is."

**Step 3**: Offer the next action.
- "Want me to read the doc now and pull out the key facts?"
- "Want me to update the classification?"
- "Want me to send <client> a link to it?"

**INVIOLABLE**: NEVER reply "Could you re-send the file?" / "I don't see any upload" / "Which file are you looking for?" when recent_documents[0] has a doc from the last 15 minutes. The data is RIGHT THERE — use it.

If no recent_documents row at all (truly nothing), THEN ask the sender to specify or upload."""


def patch_prompt(node):
    p = node["parameters"]["options"]["systemMessage"]
    if "File status queries — resolve referent first" in p:
        return False
    if RULE_MARKER not in p:
        raise ValueError("RULE_MARKER not found")
    p = p.replace(RULE_MARKER, RULE_MARKER + "\n\n" + RULE_ADDITION)
    node["parameters"]["options"]["systemMessage"] = p
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["staging", "prod"], required=True)
    args = parser.parse_args()
    DSN = (dict(host="127.0.0.1", port=5433, dbname="n8n", user="n8n", password="n8npassword")
           if args.target == "staging"
           else dict(host="172.18.0.3", port=5432, dbname="n8n", user="n8n", password="n8npassword"))
    print(f"  target={args.target}")

    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb FROM workflow_entity WHERE name=%s", (WF_NAME,))
    wf_id, nodes = cur.fetchone()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_088_{args.target}_{ts}.json"
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    aia = next((n for n in nodes if n["name"] == "AI Agent"), None)
    if aia and patch_prompt(aia):
        print("  ✓ AI Agent prompt: file-status referent resolution rule added")
    else:
        print("  ⚠ Already patched")

    cur.close(); conn.close()
    if args.target == "staging":
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute('UPDATE workflow_entity SET nodes=%s::jsonb, "updatedAt"=now() WHERE id=%s', (json.dumps(nodes), wf_id))
        cur.execute("""UPDATE workflow_history SET nodes=%s::json
                         WHERE "workflowId"=%s AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""",
                    (json.dumps(nodes), wf_id, wf_id))
        cur.execute('UPDATE workflow_entity SET active=false, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); time.sleep(2)
        cur.execute('UPDATE workflow_entity SET active=true, "updatedAt"=now() WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()
        print("  ✓ staging done")
    else:
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes)


if __name__ == "__main__":
    main()
