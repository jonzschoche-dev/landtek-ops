#!/usr/bin/env python3
"""Deploy 271 - Empty Promise Guard with auto-recovery to actual docs.

Postmortem May 25 5:08 AM: Jonathan asked twice for sustainable-development
docs on Inocalla property. Leo replied "On it - searching now." TWICE with no
tool calls and no follow-up. Despite deploy_268's NO EMPTY PROMISES rule
being live in the system prompt AND deploy_270's DRIVE LINKS rule both being
in workflow_entity AND workflow_history.

The Gemini model is ignoring soft rules. Structural enforcement now:

Modify Safe Reply node to detect empty-promise replies and AUTO-RECOVER:
  1. Detect a forbidden pattern ("on it", "searching now", "let me look",
     "checking now", etc.) on telegram_reply_to_client + action_items empty
  2. If the user's rawText also looks like a doc-retrieval request
     (contains "document", "doc", "paper", "find", "show", "retriev", etc.)
  3. Make a synchronous HTTP GET to leo-tools /api/query_documents with the
     most distinctive keyword extracted from rawText
  4. Format the top 5 results as drive_link rows
  5. REPLACE telegram_reply_to_client with the formatted list
  6. Tag the override in telegram_summary_for_jonathan so I can audit it

If recovery fails (no keyword, HTTP error, no results), substitute with an
honest 'AI fumbled - please re-ask with X keyword' message instead of the
broken placeholder. Either way Jonathan gets something actionable, not
silence.

Idempotent. Audited via app.actor='jonathan_deploy_271'.
"""
import json
import subprocess
import sys

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
WORKFLOW_ID = "vSDQv1vfn6627bnA"


NEW_SAFE_REPLY = r"""const data = $('Parse Agent1').first().json || {};
const ctx = $('Context Builder').first().json || {};
const rawText = (ctx.rawText || '').trim();

// Optimized sanitizer for Telegram parse_mode=HTML (deploy_263).
function sanitize(text) {
  if (!text) return '';
  let t = String(text);
  t = t.replace(/<thinking>[\s\S]*?<\/thinking>/gi, '');
  t = t.replace(/^#{1,6}\s+(.+)$/gm, '<b>$1</b>');
  t = t.replace(/\*\*([^*\n]+?)\*\*/g, '<b>$1</b>');
  t = t.replace(/__([^_\n]+?)__/g, '<b>$1</b>');
  t = t.replace(/(^|[^*])\*([^*\n][^*\n]*?)\*(?!\*)/g, '$1<i>$2</i>');
  t = t.replace(/(^|[^_])_([^_\n][^_\n]*?)_(?!_)/g, '$1<i>$2</i>');
  t = t.replace(/`([^`\n]+?)`/g, '<code>$1</code>');
  const allowed = [];
  t = t.replace(/<\/?(b|i|code|pre|s|u)>/g, function(m) {
    allowed.push(m);
    return '@@LEOSAFE' + (allowed.length - 1) + '@@';
  });
  t = t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  t = t.replace(/@@LEOSAFE(\d+)@@/g, function(_, i) { return allowed[parseInt(i, 10)]; });
  const MAX = 3900;
  if (t.length > MAX) t = t.substring(0, MAX) + "\n\n(truncated; full text in DB log)";
  return t.trim();
}

// EMPTY PROMISE GUARD (deploy_271)
const FORBIDDEN_PATTERNS = [
  /^on it[.!\s]*$/i,
  /^on it[ -]+search/i,
  /searching now/i,
  /let me look/i,
  /let me check/i,
  /checking (now|our|the)/i,
  /i'?ll (pull|get back|look|find|check)/i,
  /one moment/i,
  /give me a (sec|moment|minute)/i,
  /pulling up/i,
  /will follow up/i,
  /^(checking|searching|looking)[.\s]*$/i
];
function isEmptyPromise(text) {
  if (!text) return false;
  if (text.length > 250) return false; // long replies probably had content
  return FORBIDDEN_PATTERNS.some(re => re.test(text));
}
function isDocRequest(text) {
  if (!text) return false;
  return /\b(document|docs?|papers?|records?|files?|find|show|pull|retriev|where (is|are)|do we have|any (info|data))/i.test(text);
}
function extractKeyword(text) {
  if (!text) return null;
  // Prefer proper nouns (capitalized words past the first word).
  const stop = new Set(['need','help','about','have','find','show','pull','document','documents','documentation','docs','paper','papers','record','records','file','files','property','retriev','retrieving','retrieved','retrieve','please','want','know','can','you','the','any','our','for','from','this','with','that','sustainable','development','community','plans','plan','project','about','have','know','jonathan','leo']);
  const tokens = text.match(/[A-Za-z][a-zA-Z-]+/g) || [];
  if (!tokens.length) return null;
  // Skip the first token (sentence-start capitalization is unreliable).
  const rest = tokens.slice(1);
  // Pass 1: proper nouns (capitalized, length >= 4, not stopword)
  const propers = rest.filter(w => /^[A-Z]/.test(w) && w.length >= 4 && !stop.has(w.toLowerCase()));
  if (propers.length) {
    propers.sort((a, b) => b.length - a.length);
    return propers[0];
  }
  // Pass 2: any distinctive word, length >= 5 (raised from 4)
  const others = tokens.filter(w => w.length >= 5 && !stop.has(w.toLowerCase()));
  others.sort((a, b) => b.length - a.length);
  return others[0] || null;
}

let clientReply = data.telegram_reply_to_client || '';
const hasNoActions = !data.action_items || data.action_items.length === 0;
let guardFired = false;
let guardNote = '';

if (isEmptyPromise(clientReply) && isDocRequest(rawText) && hasNoActions) {
  guardFired = true;
  const kw = extractKeyword(rawText);
  if (kw) {
    try {
      const r = await this.helpers.httpRequest({
        method: 'GET',
        url: 'http://localhost:8765/api/query_documents',
        qs: { keyword: kw, limit: 5 },
        json: true,
        timeout: 8000,
      });
      const docs = (r && r.documents) || [];
      if (docs.length) {
        const lines = docs.slice(0, 5).map(d => {
          const title = d.title || d.file || ('doc #' + d.doc_id);
          const link = d.drive_link || '(no Drive link)';
          const mc = d.matter_code ? ' [' + d.matter_code + ']' : '';
          return 'doc#' + d.doc_id + mc + '  ' + title + '\n' + link;
        });
        clientReply = 'Found ' + docs.length + ' doc(s) matching "' + kw + '":\n\n' + lines.join('\n\n');
        guardNote = '[empty_promise_guard] AI emitted "' + (data.telegram_reply_to_client || '').slice(0,60) + '" without tools; auto-recovered with query_documents keyword="' + kw + '" (' + docs.length + ' hits)';
      } else {
        clientReply = 'I searched for "' + kw + '" but found no documents matching. Try a different keyword or be more specific.';
        guardNote = '[empty_promise_guard] AI fumbled "' + (data.telegram_reply_to_client || '').slice(0,60) + '"; auto-recovery via keyword="' + kw + '" returned 0 results';
      }
    } catch (e) {
      clientReply = 'I tried to look up "' + kw + '" but the lookup failed (' + (e.message || e) + '). Please re-ask.';
      guardNote = '[empty_promise_guard] AI fumbled; auto-recovery threw ' + (e.message || e);
    }
  } else {
    clientReply = 'I dropped your question — please re-ask with a specific keyword (e.g. "Inocalla sustainable" or "Balane title").';
    guardNote = '[empty_promise_guard] AI fumbled and no keyword extractable from rawText';
  }
}

const safeClientReply = (clientReply && clientReply.trim() !== "")
  ? sanitize(clientReply)
  : !data.rowNumber
    ? "Hello! I'm LeoLandTek, the Landtek property management assistant. Please share your full name, contact number, and how we can help you today. Someone from our team will follow up shortly."
    : "Thank you. I've noted your message and will process it accordingly.";

let safeJonathanSummary = (data.telegram_summary_for_jonathan &&
                           data.telegram_summary_for_jonathan.trim() !== "")
  ? sanitize(data.telegram_summary_for_jonathan)
  : "";

if (guardFired) {
  safeJonathanSummary = safeJonathanSummary
    ? (safeJonathanSummary + '\n\n' + guardNote)
    : guardNote;
}

return [{
  json: Object.assign({}, data, {
    telegram_reply_to_client: safeClientReply,
    telegram_summary_for_jonathan: safeJonathanSummary,
    target_chat_id: data.target_chat_id || "",
    target_message: data.target_message || "",
    empty_promise_guard_fired: guardFired,
  })
}];
"""


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'jonathan_deploy_271'")

    print("Deploy 271 - Empty Promise Guard with auto-recovery")
    print("=" * 60)

    cur.execute("SELECT nodes FROM workflow_entity WHERE id = %s", (WORKFLOW_ID,))
    nodes_raw = cur.fetchone()["nodes"]
    nodes = nodes_raw if isinstance(nodes_raw, list) else json.loads(nodes_raw)

    patched = False
    for n in nodes:
        if n.get("name") == "Safe Reply" and n.get("type") == "n8n-nodes-base.code":
            old_len = len(n.get("parameters", {}).get("jsCode", ""))
            n.setdefault("parameters", {})["jsCode"] = NEW_SAFE_REPLY
            print(f"  Safe Reply jsCode: {old_len} -> {len(NEW_SAFE_REPLY)} chars")
            patched = True

    if not patched:
        print("  Safe Reply not found")
        sys.exit(1)

    cur.execute(
        "UPDATE workflow_entity SET nodes = %s::json, \"updatedAt\" = now() WHERE id = %s",
        (json.dumps(nodes), WORKFLOW_ID),
    )
    conn.commit()
    cur.close()
    conn.close()
    print("  workflow_entity updated")

    print("\n  syncing workflow_history...")
    r = subprocess.run(["python3", "/root/landtek/scripts/sync_workflow_history.py", WORKFLOW_ID],
                       capture_output=True, text=True)
    print("  " + r.stdout.strip())

    print("\n  re-registering webhook (defensive)...")
    r = subprocess.run(["python3", "/root/landtek/scripts/sync_telegram_webhook.py"],
                       capture_output=True, text=True)
    print("  " + (r.stdout.split('\n')[-2] if r.stdout else ''))

    print("\n  smoke test...")
    r = subprocess.run(["python3", "/root/landtek/scripts/post_deploy_smoke.py"],
                       capture_output=True, text=True)
    print("  " + r.stdout.strip().replace("\n", "\n  "))


if __name__ == "__main__":
    main()
