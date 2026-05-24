#!/usr/bin/env python3
"""Deploy 265 - Telegram reliability hardening + monitoring.

POSTMORTEM (Jonathan trip, May 21-22):
  - 0/11 successful executions May 21-22 (all errored at "Gemini Embed")
  - Root cause: node named "Gemini Embed" actually calls OpenAI embeddings
    with a HARDCODED API key (sk-proj-Ut2oC...) that is invalid/revoked.
  - I declared the bot healthy after deploy_263/264 by checking webhook
    status only. Never ran a real end-to-end execution test.
  - Even when Leo DOES execute, the May 22 reply ("Understood - Civil Case
    26-360 is the test case...") shows zero use of ACTIVE LANDSCAPE: no
    date, no open matters, no past-due demand letter, no May 22 meeting.

This deploy:
  A. Switch "Gemini Embed" node to ACTUALLY use Gemini API (gemini-embedding-001,
     768 dim - matches existing Qdrant). Add onError=continueRegularOutput so
     a future embed failure can't kill the whole execution.
  B. Strengthen AI Agent system prompt: STANDING BRIEF rules become MANDATORY
     pre-flight checks Leo must satisfy before emitting JSON, with concrete
     opening templates for common questions.
  C. n8n restart.

Separately (NOT in this script):
  - scripts/monitor_n8n_executions.py - health checker with nightly cron
  - truth_tests/test_n8n_execution_health.py - hard-fail if no exec in 24h
  These get pushed alongside but don't depend on the workflow patch.

Idempotent. Audited via app.actor='jonathan_deploy_265'.
"""
import json
import os
import subprocess
import sys

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
WORKFLOW_ID = "vSDQv1vfn6627bnA"


# Pull the Gemini key from .env so it's not hardcoded in this script
def load_gemini_key():
    env = "/root/landtek/.env"
    if not os.path.exists(env):
        env = os.path.expanduser("~/.env")
    with open(env) as f:
        for line in f:
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"\'')
    raise RuntimeError("GEMINI_API_KEY not found in .env")


GEMINI_EMBED_PARAMS = {
    "url": "=https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={{ $env.GEMINI_API_KEY }}",
    "method": "POST",
    "sendBody": True,
    "specifyBody": "json",
    "jsonBody": '{\n  "content": {\n    "parts": [{ "text": "{{ $(\'Parse Agent1\').first().json.case_file + \' | \' + $(\'Context Builder\').first().json.rawText + \' | \' + $(\'Parse Agent1\').first().json.telegram_summary_for_jonathan }}" }]\n  },\n  "outputDimensionality": 768\n}',
    "sendHeaders": True,
    "headerParameters": {
        "parameters": [
            {"name": "Content-Type", "value": "application/json"}
        ]
    },
    "options": {"timeout": 15000},
}


# Strengthened STANDING BRIEF — replaces the soft "Rules" with MANDATORY pre-flight
STANDING_BRIEF_V2 = """

# STANDING BRIEF (deploy_264, strengthened deploy_265 - 2026-05-22)

Every conversation turn includes an ACTIVE LANDSCAPE block in your input
summarizing today's date (Asia/Manila), all open matters with next_event or
next_deadline, recent activity (last 48h), and outstanding review queues.

MANDATORY PRE-FLIGHT (do this before composing your reply):

1. Read the ACTIVE LANDSCAPE block. State today's date silently to yourself.

2. Scan the open-matters list for:
   - any next_deadline within 3 days of today (Asia/Manila)
   - any next_deadline that is past-due (already in the past)
   - any matter whose next_event text mentions a specific date that falls
     today or tomorrow (e.g., "May 22 Naga meeting")

3. If the user is Jonathan (isJonathan=true) and ANY of the above are
   present AND the user did not already raise them, your
   telegram_summary_for_jonathan MUST END with a block like:

     Heads up (auto):
     - [MWK-TCT4497, past-due 2026-05-18] Send demand letter to RD Camarines Norte
     - [MWK-GUARDIANSHIP, today] May 22 Naga meeting agenda confirmed about guardianship

   Use exactly that format (matter_code, deadline tag, then next_event).

4. If the user asks an open-ended status question ("what's up", "status",
   "what's happening", "anything I need to know"), use ACTIVE LANDSCAPE as
   the primary source. Cite at least 3 specific matter_codes with their
   next_event in the first 6 lines of your reply. Do not call tools first.

5. Treat ACTIVE LANDSCAPE as ground truth. Do NOT call query_documents /
   get_deadlines / etc. to re-fetch what is already in the landscape.

6. If recent_activity_48h shows new_docs >= 5 OR new_emails >= 10, mention
   the count in the summary once (not in every reply).

Forbidden:
  - Replying with a generic restatement of the user's own message and
    nothing else. If you have nothing new to contribute from the landscape
    or tools, the LANDSCAPE alone gives you 13 open matters to mention.
  - Saying "I'll flag this for review" without proposing a concrete next
    step from the landscape.

"""


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'jonathan_deploy_265'")

    print("Deploy 265 - Telegram reliability hardening")
    print("=" * 60)

    cur.execute("SELECT nodes FROM workflow_entity WHERE id = %s", (WORKFLOW_ID,))
    row = cur.fetchone()
    if not row:
        print("  workflow not found")
        sys.exit(1)
    nodes = row["nodes"]
    if isinstance(nodes, str):
        nodes = json.loads(nodes)

    patched = {"Gemini Embed": False, "AI Agent": False}

    for n in nodes:
        if n.get("name") == "Gemini Embed" and n.get("type") == "n8n-nodes-base.httpRequest":
            old_url = n.get("parameters", {}).get("url", "")
            n["parameters"] = dict(GEMINI_EMBED_PARAMS)
            n["onError"] = "continueRegularOutput"
            print(f"  Gemini Embed switched from openai to gemini-embedding-001")
            print(f"    old url: {old_url[:60]}")
            print(f"    new url: {GEMINI_EMBED_PARAMS['url'][:90]}")
            print(f"    onError: continueRegularOutput")
            patched["Gemini Embed"] = True

        elif n.get("name") == "AI Agent" and n.get("type") == "@n8n/n8n-nodes-langchain.agent":
            opts = n.setdefault("parameters", {}).setdefault("options", {})
            old_prompt = opts.get("systemMessage", "")
            # Replace the deploy_264 STANDING BRIEF (the soft version) with v2
            anchor_start = "# STANDING BRIEF (deploy_264"
            anchor_end_idx = None
            if anchor_start in old_prompt:
                start_idx = old_prompt.index(anchor_start)
                # Find the next "# " heading after STANDING BRIEF (or end)
                tail = old_prompt[start_idx:]
                # Skip the heading itself
                next_section_relative = tail.find("\n# ", 5)
                if next_section_relative > 0:
                    new_prompt = old_prompt[:start_idx] + STANDING_BRIEF_V2.lstrip() + old_prompt[start_idx + next_section_relative + 1:]
                else:
                    new_prompt = old_prompt[:start_idx] + STANDING_BRIEF_V2.lstrip()
            else:
                # No prior STANDING BRIEF - append
                new_prompt = old_prompt.rstrip() + "\n" + STANDING_BRIEF_V2
            opts["systemMessage"] = new_prompt
            print(f"  AI Agent system prompt: {len(old_prompt)} -> {len(new_prompt)} chars")
            patched["AI Agent"] = True

    if not all(patched.values()):
        missing = [k for k, v in patched.items() if not v]
        print(f"  WARNING: not all nodes patched: {missing}")

    cur.execute(
        "UPDATE workflow_entity SET nodes = %s::jsonb, \"updatedAt\" = now() WHERE id = %s",
        (json.dumps(nodes), WORKFLOW_ID),
    )
    conn.commit()
    print(f"\n  workflow updated, patched: {[k for k,v in patched.items() if v]}")

    cur.close()
    conn.close()

    print("\n  Restarting n8n...")
    r = subprocess.run(["docker", "restart", "n8n-n8n-1"], capture_output=True, text=True)
    print(f"  {'restarted: ' + r.stdout.strip() if r.returncode == 0 else 'FAIL: ' + r.stderr.strip()}")


if __name__ == "__main__":
    main()
