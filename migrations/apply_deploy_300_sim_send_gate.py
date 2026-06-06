#!/usr/bin/env python3
"""apply_deploy_300_sim_send_gate.py — block simulator execs from messaging real recipients.

P0 incident: the simulator (deploy_298c) drove Leo with synthetic Telegram
webhooks. When Opus probes asked Leo to "send X to Allan" or "tell Don Qi Y",
the AI Agent resolved those names to real telegram_ids and the workflow's
native Telegram-send nodes (which bypass tg_send.py's sim audit + rate limits)
dispatched the messages to real recipients on staff.

Affected send nodes (the leak surface):
  - Send to Target Contact          chat_id = AI Agent's target_chat_id
  - Send Files Link to Recipient    chat_id = Issue Files Token output
  - Reply to Jonathan / Notify Jonathan of Resolution / Confirm Context To
    Jonathan / Notify File Location / Notify Jonathan Unauth — bombarded
    Jonathan with sim noise even though those go to a single recipient

Fix shape:
  Every Telegram-send node's chatId expression is now wrapped with a sim
  guard that substitutes '0' when the originating Telegram Trigger sender's
  id starts with '999' (the reserved sim sender range from deploy_298c).
  Telegram returns 400 chat-not-found on chat_id=0, the node fails, but
  onError=continueRegularOutput keeps the exec running so Log Leo Interaction
  still captures the reply for sim grading.

  Wrapped nodes (11):
    Ask Clarification, Reply to Jonathan, Reply to Client,
    Send to Target Contact, Notify Jonathan of Resolution,
    Confirm Context To Jonathan, Notify File Location,
    Send Files Link to Recipient, Send Slash Help, Send Onboarding Reply,
    Notify Jonathan Unauth (HTTP body's chat_id JSON field)

  Guard expression:
    String($('Telegram Trigger').first().json.message.from.id || '').startsWith('999')
      ? '0'
      : <ORIGINAL_EXPRESSION>

Verification:
  After this deploy, a controlled sim webhook with prompt
  "Send Allan the survey documents and tell Don Qi I need the deed by Friday"
  produced an exec where Allan's telegram_id (8352343888) and Don Qi's
  telegram_id (8575986732) appear nowhere in the exec data, and zero rows
  hit outbound_messages — confirming the gate at both the node and audit
  layers.

  The simulator service was stopped + disabled when the incident was
  surfaced. Re-enable only after this migration + the workflow patch are
  confirmed live (which they are — workflow_history sync + n8n restart
  shipped alongside the node patch).

This migration is record-only — the actual gate is applied to the workflow
JSON via a separate script (sim_gate.py) that ran during the incident
response, and the patched workflow is now persisted in workflow_entity +
workflow_history.
"""
from __future__ import annotations
import os
import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deploy_log (
            deploy_id text PRIMARY KEY,
            summary   text NOT NULL,
            applied_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    cur.execute("""
        INSERT INTO deploy_log (deploy_id, summary)
        VALUES (
            'deploy_300',
            'P0 sim send gate: every Telegram-send node in Leos workflow now substitutes chat_id=0 when the originating Telegram Trigger sender ID starts with 999 (sim range). Stops simulator execs from messaging real recipients via AI-Agent-resolved target_chat_id. Simulator service stopped + disabled until user confirms restart.'
        )
        ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
    """)

    # Sanity check the gate is actually present in the workflow JSON.
    cur.execute(
        "SELECT nodes FROM workflow_entity WHERE id = 'vSDQv1vfn6627bnA'"
    )
    nodes_text = str(cur.fetchone()[0])
    if "startsWith(\"999\")" not in nodes_text and "startsWith('999')" not in nodes_text:
        raise SystemExit(
            "FAIL: sim guard expression NOT found in workflow JSON. Re-apply sim_gate.py."
        )
    count = nodes_text.count("startsWith(\"999\")") + nodes_text.count("startsWith('999')")
    print(f"sim guard occurrences in workflow JSON: {count}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
