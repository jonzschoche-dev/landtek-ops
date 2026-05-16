#!/usr/bin/env python3
"""Deploy 091 — Specificity + no operator-narration leaks in client replies.

Incident (2026-05-16 ~10:30 Manila):
  Leo to Don Qi: "your upcoming meeting: when is it scheduled, and what should
                  we be preparing on our end?"
  Don Qi:        "which meeting?"
  Leo:           "Which meeting are you referring to? (Asking Don Qi to clarify
                  what meeting he has coming up.)"

Two faults:
  A. Generic referent. Leo had inquiry id 7 ("Ask Don Qi about his impending
     meeting") AND a prior resolved inquiry id 1 where Don Qi mentioned the
     Naga meeting end of next week with Atty Botor. Leo should have followed
     up with "the Naga meeting with Atty Botor you mentioned" — not "your
     upcoming meeting" (under-specified).

  B. Operator-narration leak. The parenthetical "(Asking Don Qi to clarify...)"
     is Leo's internal reasoning leaked into the client-facing reply. This
     content belongs in telegram_summary_for_jonathan ONLY.

Fix: prompt — two new constraints under Rule B / Rule E.
"""
import json, os, sys, argparse, time
sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

WF_NAME = "Leos Workflow"

ANCHOR = "### File status queries — resolve referent first (added 2026-05-16 — deploy_088)"

ADDITION = """### Specificity when following up on relayed inquiries (added 2026-05-16 — deploy_091)

When `pendingInquiries[]` has an open item AND you are following up with the client about it:

- **Reference the SPECIFIC subject already established in conversation history.** If the inquiry is generic ("about his impending meeting") but conversation history shows Don Qi mentioned a "tentative meeting end of next week with Atty Botor in Naga", say "the Naga meeting with Atty Botor you mentioned for end of next week", NOT "your upcoming meeting".
- If you cannot identify the specific subject from conversation history + the inquiry's `relayed_message`, ASK Jonathan to clarify in `telegram_summary_for_jonathan` (back-channel) rather than asking the client a vague question.
- When the client responds "which X?" / "what are you talking about?" — that's a sign you under-specified. RECOVER by re-stating the specific subject from your context, NOT by asking them another question. Example:
  WRONG: "Which meeting are you referring to?"
  RIGHT: "The Naga trip you mentioned earlier — tentatively end of next week with Atty. Botor — wanted to check if the date firmed up."

### No operator-narration in client-facing replies (added 2026-05-16 — deploy_091)

`telegram_reply_to_client` is what the CLIENT reads. It must NEVER contain:
- Parenthetical narration of your own intent: "(Asking Don Qi to clarify…)"
- Third-person commentary about yourself: "Leo is checking the file…"
- Operator-side metadata: "(per Rule C)", "(low confidence)", "(see chat_note_to_save)"
- Internal references: "(see DOC 623)" — bare doc references can appear, but never with a parenthetical explaining your reasoning to the client

All of the above belong in `telegram_summary_for_jonathan` ONLY. The client sees ONLY natural, direct prose addressed to them in second person ("you", "your"). If you find yourself wanting to add a parenthetical reasoning, MOVE IT to the Jonathan summary.

"""


def patch(node):
    p = node["parameters"]["options"]["systemMessage"]
    if "Specificity when following up on relayed inquiries" in p:
        return False
    if ANCHOR not in p:
        raise ValueError("anchor not found")
    p = p.replace(ANCHOR, ANCHOR + "\n\n" + ADDITION)
    node["parameters"]["options"]["systemMessage"] = p
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["staging", "prod"], required=True)
    args = ap.parse_args()
    DSN = dict(host="172.18.0.3", port=5432, dbname="n8n", user="n8n", password="n8npassword") if args.target == "prod" else dict(host="127.0.0.1", port=5433, dbname="n8n", user="n8n", password="n8npassword")
    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb FROM workflow_entity WHERE name=%s", (WF_NAME,))
    wf_id, nodes = cur.fetchone()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_091_{args.target}_{ts}.json"
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")
    aia = next((n for n in nodes if n["name"] == "AI Agent"), None)
    if aia and patch(aia):
        print("  ✓ AI Agent prompt: specificity + no-narration rules added")
    else:
        print("  ⚠ already patched")
    cur.close(); conn.close()

    if args.target == "prod":
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes)
    else:
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute('UPDATE workflow_entity SET nodes=%s::jsonb, "updatedAt"=now() WHERE id=%s', (json.dumps(nodes), wf_id))
        cur.execute("""UPDATE workflow_history SET nodes=%s::json WHERE "workflowId"=%s AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""", (json.dumps(nodes), wf_id, wf_id))
        cur.execute('UPDATE workflow_entity SET active=false WHERE id=%s', (wf_id,))
        conn.commit(); time.sleep(2)
        cur.execute('UPDATE workflow_entity SET active=true WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()


if __name__ == "__main__":
    main()
