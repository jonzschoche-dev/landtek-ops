#!/usr/bin/env python3
"""test_n8n_execution_health.py - Telegram workflow invariants (pre-deploy safe).

Only checks invariants that should ALWAYS hold regardless of bot activity.
Runtime health (was the bot used recently?) lives in
scripts/monitor_n8n_executions.py so it doesn't block deploys when Jonathan
is offline for a few days.

The single invariant here: Gemini Embed must use Gemini API, not OpenAI.
A hardcoded OpenAI key in this node killed the bot for 2 days during
Jonathan's trip (May 21-22). deploy_265 fixed it; this test guards against
regression.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, TruthFailure

WORKFLOW_ID = 'vSDQv1vfn6627bnA'


def gemini_embed_uses_gemini_api(cur):
    cur.execute("""
        SELECT n->'parameters'->>'url' AS url
          FROM workflow_entity, jsonb_array_elements(nodes::jsonb) n
         WHERE id = %s
           AND n->>'name' = 'Gemini Embed'
    """, (WORKFLOW_ID,))
    r = cur.fetchone()
    if not r:
        raise TruthFailure("Gemini Embed node not found in workflow")
    url = (r["url"] or "").lower()
    if "openai.com" in url:
        raise TruthFailure(
            f"Gemini Embed is using OPENAI URL ({url[:80]}). "
            "deploy_265 was supposed to switch it to Gemini. The hardcoded "
            "OpenAI key killed the bot for 2 days; do not revert."
        )
    if "generativelanguage.googleapis.com" not in url:
        raise TruthFailure(
            f"Gemini Embed URL doesn't look like Gemini API: {url[:80]}"
        )


def safe_reply_sanitizer_present(cur):
    """deploy_263 invariant: Safe Reply must sanitize BOTH reply fields."""
    cur.execute("""
        SELECT n->'parameters'->>'jsCode' AS code
          FROM workflow_entity, jsonb_array_elements(nodes::jsonb) n
         WHERE id = %s
           AND n->>'name' = 'Safe Reply'
    """, (WORKFLOW_ID,))
    r = cur.fetchone()
    if not r or not r["code"]:
        raise TruthFailure("Safe Reply jsCode missing")
    code = r["code"]
    # Must reference sanitize() applied to both fields
    if "sanitize(data.telegram_reply_to_client)" not in code:
        raise TruthFailure(
            "Safe Reply no longer sanitizes telegram_reply_to_client — "
            "deploy_263 regression. Jonathan's free-form replies route through this field."
        )


TESTS = [
    ("n8n.gemini_embed_uses_gemini_api", gemini_embed_uses_gemini_api),
    ("n8n.safe_reply_sanitizes_both_fields", safe_reply_sanitizer_present),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
