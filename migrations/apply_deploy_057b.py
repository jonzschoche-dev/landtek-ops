#!/usr/bin/env python3
"""Deploy 057b — Robust Parse Agent1 JSON extraction.

Bug: Leo's recent outputs contain MULTIPLE JSON code blocks (showing his
work — tool calls + tool results + final response). Parse Agent1 uses:
    const start = raw.indexOf('{');     // first '{' anywhere
    const end = raw.lastIndexOf('}');    // last '}' anywhere
    const extracted = raw.substring(start, end+1);

When Leo's output looks like:
    **Tool call: get_deadlines**
    ```json
    { "case_file": "MWK-001", "window_days": 90 }
    ```
    ```json
    { "tool": "get_deadlines", ..., "result": [] }
    ```
    ... (3 more tool calls + results) ...
    { "case_file": "MWK-001", "message_type": "text_only", ... }

...the indexOf+lastIndexOf approach pulls the entire range from the FIRST
{ (a tool-call param) to the LAST } (end of final response). That's not
valid JSON. JSON.parse fails -> Parse Agent1 returns its fallback object
("Sorry, I had trouble processing that") -> ALL downstream Insert nodes
get empty defaults -> 0 rows in action_items / chat_notes / calendar_events.

This is the upstream root cause of every persistence failure today.

Fix: walk backwards from the end, finding the LAST {} block that parses
as valid JSON AND has the expected schema marker (case_file field).
Falls back to a clean error path if nothing valid is found.
"""
import json, sys, psycopg2, re
from datetime import datetime, timezone

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")


def snapshot():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = f"/root/landtek/snapshots/leos_workflow_pre_057b_{ts}.json"
    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("""SELECT row_to_json(w)::text FROM (SELECT id, name, nodes, connections, "updatedAt" FROM workflow_entity WHERE name='Leos Workflow') w;""")
    with open(path, "w") as f: f.write(cur.fetchone()[0])
    cur.close(); conn.close()
    print(f" - snapshot: {path}")


# The new robust extractor logic (replaces just the extraction part; rest of Parse Agent1 stays the same)
ROBUST_EXTRACTOR = """const aiOutput = $input.first().json || {};
const context = $('Context Builder').first().json || {};

let raw = aiOutput.output || "";
raw = raw.toString().trim();

// ── Robust JSON extraction (deploy_057b) ─────────────────────────────────
// Leo's output may contain multiple JSON code blocks (tool calls + final
// response). Walk backwards from the end, finding the last balanced {}
// block whose parse yields an object containing 'case_file' (the schema
// marker). That's the actual final response.
function extractFinalSchemaJson(s) {
  s = String(s).trim();

  // Fast path: maybe the whole string is one valid JSON
  try {
    const obj = JSON.parse(s);
    if (obj && typeof obj === 'object' && !Array.isArray(obj) && obj.case_file !== undefined) {
      return obj;
    }
  } catch (e) {}

  // Strip markdown code fences (```json ... ```)
  const fenceClean = s.replace(/```(?:json)?\\s*/g, '').replace(/```/g, '');
  try {
    const obj = JSON.parse(fenceClean);
    if (obj && typeof obj === 'object' && !Array.isArray(obj) && obj.case_file !== undefined) {
      return obj;
    }
  } catch (e) {}

  // Walk: find every balanced {...} substring, parse, keep ones with case_file
  // Iterate from end backwards so we get the LAST schema-shaped object.
  let endIdx = s.lastIndexOf('}');
  while (endIdx > 0) {
    // Walk backward, counting braces, to find matching {
    let depth = 1;
    let inString = false;
    let escape = false;
    let i = endIdx - 1;
    while (i >= 0 && depth > 0) {
      const c = s[i];
      if (escape) { escape = false; i--; continue; }
      if (c === '\\\\') { escape = true; i--; continue; }
      if (c === '"') { inString = !inString; i--; continue; }
      if (!inString) {
        if (c === '}') depth++;
        else if (c === '{') depth--;
      }
      if (depth === 0) break;
      i--;
    }
    if (depth === 0 && i >= 0) {
      const candidate = s.substring(i, endIdx + 1);
      try {
        const obj = JSON.parse(candidate);
        if (obj && typeof obj === 'object' && !Array.isArray(obj) && obj.case_file !== undefined) {
          return obj;
        }
      } catch (e) {}
    }
    // Try the next earlier }
    endIdx = s.lastIndexOf('}', endIdx - 1);
  }
  return null;
}

let parsed = extractFinalSchemaJson(raw);
if (!parsed) {
  parsed = {
    needs_clarification: true,
    clarification_question: "Sorry, I had trouble processing that. Please try again.",
    message_type: "text_only",
    case_file: "Unknown",
    telegram_reply_to_client: "Sorry, I encountered a processing error. Please try again.",
    telegram_summary_for_jonathan: "Parse error on last message \\u2014 please review manually.",
    case_intelligence_update: {},
    action_items: [],
    new_contact_detected: false,
    create_new_client: false,
    new_client_data: {},
    authorize_contact: false,
    authorization_data: {},
    target_chat_id: "",
    target_message: ""
  };
}
"""


def main():
    snapshot()
    conn = psycopg2.connect(**DSN); conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes = cur.fetchone()

    for n in nodes:
        if n.get("name") != "Parse Agent1":
            continue
        js = n["parameters"].get("jsCode", "")
        if "extractFinalSchemaJson" in js:
            print(" - Parse Agent1: robust extractor already present, skipping")
            return

        # Replace from the start through to (and including) the existing parse fallback block
        old_pattern = re.compile(
            r"^const aiOutput.*?(?:parsed = \{[^}]*\}|try \{[^}]*?JSON\.parse[^}]*?\}.*?\})",
            re.DOTALL | re.MULTILINE
        )
        # Replace the entire start-to-fallback header section
        # Strategy: cut from start to "// Inject context from Context Builder" marker
        marker = "// Inject context from Context Builder"
        if marker not in js:
            print(f"ERROR: anchor marker '{marker}' not found in Parse Agent1 — refusing to patch blind")
            return
        cut_idx = js.index(marker)
        new_js = ROBUST_EXTRACTOR + "\n" + js[cut_idx:]
        n["parameters"]["jsCode"] = new_js
        print(f" - Parse Agent1: jsCode rewritten ({len(js)} -> {len(new_js)} chars)")

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
    msg = """Robust Parse Agent1 JSON extraction (the actual root cause)

Leo's outputs now contain multiple JSON blocks (tool calls + tool
results + final response). Parse Agent1's indexOf+lastIndexOf
extractor pulled the entire range from the first { to the last },
which is NOT valid JSON. JSON.parse failed -> fallback object ->
empty defaults -> 0 rows in action_items/chat_notes/calendar_events.

THIS is why deploy_055/055b's PK fix didn't deliver rows. The
upstream parse was failing before persistence even tried.

New extractor walks backwards from the end finding the LAST balanced
{} block that parses as valid JSON AND has the schema marker
(case_file field). Skips tool-call params and intermediate result
blocks. Markdown code fences are also pre-stripped.

Expected impact: Parse Agent1 success rate goes from <50% to ~100%.
Action items / chat notes / calendar events finally land in their
tables when Leo emits them."""
    commit_deploy("057b", msg)
