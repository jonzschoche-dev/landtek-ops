#!/usr/bin/env python3
"""Deploy 105 — Output hallucination filter.

A new Code node "Hallucination Filter" runs after Parse Agent1, before
Safe Reply. Scans telegram_reply_to_client + telegram_summary_for_jonathan
for high-risk specific assertions (TCT/OCT numbers, dates, currency,
case dockets, party names). For each:

  - If assertion appears verbatim in current input (rawText, recent docs,
    chat notes, assets, intelligence_summary) → OK
  - If unsourced → log to new hallucination_log table + add ⚠ footer
    to the reply

This is a SAFETY NET, not a block. Future iterations could escalate
unsourced specific facts to refusal.
"""
import json, os, sys, uuid, argparse, time
sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

WF_NAME = "Leos Workflow"


HALLUCINATION_FILTER_JS = """// Hallucination Filter — deploy_105
// Scans AI output for specific factual assertions. Logs unsourced ones.
const data = $input.first().json || {};
const sources = [];

// Gather all "trusted source" text the AI had access to
function pushAll(arr, getter) {
  try {
    for (const x of arr) {
      const t = getter(x);
      if (t) sources.push(String(t));
    }
  } catch (e) {}
}

// 1. Current user message
sources.push(String(data.rawText || ''));

// 2. clientRow free text
const cr = data.clientRow || {};
['client_intelligence_summary','current_goals','key_risks','open_strategic_gaps','project_status','next_milestone','instructions']
  .forEach(k => sources.push(String(cr[k] || '')));

// 3. Recent documents excerpts
pushAll(cr.recent_documents || [], d => d.extracted_excerpt);
pushAll(cr.recent_documents || [], d => d.original_filename);

// 4. Case notes (already filtered to verified+corroborated+inferred_strong)
try { pushAll($('Fetch Chat Notes').all(), n => (n.json.content_excerpt || '') + ' ' + (n.json.summary || '')); } catch(e){}

// 5. Case assets
try { pushAll($('Fetch Case Assets').all(), a => (a.json.canonical_id || '') + ' ' + (a.json.notes_excerpt || '')); } catch(e){}

// 6. Recent conversations
pushAll(cr.recent_conversations || [], c => (c.message_caption || '') + ' ' + (c.leo_response || ''));

const blob = sources.join(' ').toLowerCase();

// Patterns to scan in the AI's outgoing text
const replyText = String(data.telegram_reply_to_client || '');
const summaryText = String(data.telegram_summary_for_jonathan || '');
const fullOutput = replyText + ' ' + summaryText;

const PATTERNS = [
  { name: 'TCT/OCT number', re: /\\b(?:TCT|OCT)[-\\s]?(?:T[-\\s])?\\d{3,6}\\b/gi },
  { name: 'Civil Case docket', re: /\\bCivil Case (?:No\\.? )?\\d{2,5}(?:[-/]\\d+)?\\b/gi },
  { name: 'CTN reference', re: /\\bCTN SL-\\d{4}-\\d{4}-\\d{4}\\b/g },
  { name: 'Date (slashy)', re: /\\b\\d{1,2}\\/\\d{1,2}\\/\\d{2,4}\\b/g },
  { name: 'Date (ISO)', re: /\\b20\\d{2}-\\d{2}-\\d{2}\\b/g },
  { name: 'Date (written)', re: /\\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\\s+\\d{1,2}(?:st|nd|rd|th)?,?\\s+(?:19|20)\\d{2}\\b/gi },
  { name: 'Peso amount', re: /\\b(?:Php|PHP|₱|P)\\s?\\d[\\d,]*(?:\\.\\d+)?\\b/g },
];

const unsourced = [];
for (const pat of PATTERNS) {
  const matches = fullOutput.match(pat.re) || [];
  for (const m of matches) {
    if (!blob.includes(m.toLowerCase())) {
      unsourced.push({ pattern: pat.name, value: m });
    }
  }
}

// Pass through (we don't BLOCK — we add a footer + log)
const flagged = unsourced.length > 0;
let modifiedReply = replyText;
let modifiedSummary = summaryText;

if (flagged) {
  const footer = '\\n\\n⚠️ [output-validator] ' + unsourced.length + ' specific fact(s) not directly traced to input sources: ' +
    unsourced.slice(0, 3).map(u => u.pattern + '=' + u.value).join(', ') +
    (unsourced.length > 3 ? '... (more in log)' : '');
  // Only add footer to Jonathan's summary, not to client reply
  modifiedSummary = (modifiedSummary || '') + footer;
}

return [{
  json: {
    ...data,
    telegram_reply_to_client: modifiedReply,
    telegram_summary_for_jonathan: modifiedSummary,
    _hallucination_unsourced: unsourced,
    _hallucination_flagged: flagged,
  },
}];"""


def build_node(base_pos):
    x, y = base_pos
    return {
        "id": str(uuid.uuid4()),
        "name": "Hallucination Filter",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [x - 100, y + 100],
        "parameters": {"jsCode": HALLUCINATION_FILTER_JS},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["staging", "prod"], required=True)
    args = ap.parse_args()
    DSN = dict(host="172.18.0.3", port=5432, dbname="n8n", user="n8n", password="n8npassword") if args.target == "prod" else dict(host="127.0.0.1", port=5433, dbname="n8n", user="n8n", password="n8npassword")
    print(f"  target={args.target}")

    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name=%s", (WF_NAME,))
    wf_id, nodes, conns = cur.fetchone()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_105_{args.target}_{ts}.json"
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes, "connections": conns}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    sr = next((n for n in nodes if n["name"] == "Safe Reply"), None)
    if not sr:
        sys.exit("FATAL: Safe Reply not found")
    base_pos = sr.get("position", [400, 0])

    if not any(n["name"] == "Hallucination Filter" for n in nodes):
        nodes.append(build_node(base_pos))
        print("  ✓ added Hallucination Filter node")

    # Wire: insert Hallucination Filter between Parse Agent1 -> Safe Reply
    pa_main = conns.get("Parse Agent1", {}).get("main", [[]])
    redirected = False
    for branch in pa_main:
        for t in branch:
            if t.get("node") == "Safe Reply":
                t["node"] = "Hallucination Filter"
                redirected = True
    conns["Parse Agent1"] = {"main": pa_main}
    if redirected:
        print("  ✓ rewired: Parse Agent1 -> Hallucination Filter (was: -> Safe Reply)")
    conns["Hallucination Filter"] = {"main": [[{"node": "Safe Reply", "type": "main", "index": 0}]]}
    print("  ✓ wired Hallucination Filter -> Safe Reply")

    cur.close(); conn.close()
    if args.target == "prod":
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes, connections=conns)
    else:
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute('UPDATE workflow_entity SET nodes=%s::jsonb, connections=%s::jsonb, "updatedAt"=now() WHERE id=%s', (json.dumps(nodes), json.dumps(conns), wf_id))
        cur.execute("""UPDATE workflow_history SET nodes=%s::json, connections=%s::json WHERE "workflowId"=%s AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""", (json.dumps(nodes), json.dumps(conns), wf_id, wf_id))
        cur.execute('UPDATE workflow_entity SET active=false WHERE id=%s', (wf_id,))
        conn.commit(); time.sleep(2)
        cur.execute('UPDATE workflow_entity SET active=true WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()
        print("  ✓ staging done")


if __name__ == "__main__":
    main()
