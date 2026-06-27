#!/usr/bin/env python3
"""agent_alert.py — the unified decision-log + severity-aware alert router for the resident agents.

Every agent that surfaces something for the operator calls emit(). It ALWAYS logs to agent_audit (the
blueprint's central decision log: who/what/when/grounding/confidence/operator-action) — $0, idempotent
via dedup_key, so re-runs don't duplicate. Routing:

  • HIGH  → an immediate Telegram to the operator THROUGH tg_send (S14 human-readability + no-double-tap
            pacing enforced) — but ONLY when LANDTEK_AGENT_ALERTS_LIVE=1. Architecture-first: the path is
            built and tested, OFF by default, flip on when ready (mirrors the §6.5 activation pattern).
  • MED/LOW → always flow to the daily digest (build_digest reads agent_audit). No phone interruption.

Nothing here is outward-facing — alerts go to the operator (Jonathan), never to counsel/clients; the
counsel-escalation ladder stays operator-triggered. Agents propose into the log; the operator disposes.

  from agent_alert import emit
  emit("filing_monitor", "new_filing", "Balane counsel filed a Manifestation",
       matter="MWK-CV26360", severity="high", grounding="doc:1088", dedup_key="filing:1088")
"""
import os

import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN_CHAT_ID = "6513067717"
ALERTS_LIVE = os.environ.get("LANDTEK_AGENT_ALERTS_LIVE", "") == "1"


def emit(agent_name, event_type, summary, *, matter=None, severity="medium",
         grounding=None, confidence=None, dedup_key=None):
    """Log a decision to agent_audit (always) and route by severity. Returns the new row id, or None
    if this logical event was already logged (dedup). Opens its own short-lived connection — $0, local."""
    severity = severity if severity in ("high", "medium", "low") else "medium"
    c = psycopg2.connect(DSN); c.autocommit = True
    try:
        cur = c.cursor()
        cur.execute(
            """INSERT INTO agent_audit
                   (agent_name, matter_code, event_type, severity, summary, grounding, confidence, dedup_key)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (dedup_key) WHERE dedup_key IS NOT NULL DO NOTHING
               RETURNING id""",
            (agent_name, matter, event_type, severity, summary, grounding, confidence, dedup_key))
        row = cur.fetchone()
        if row is None:
            return None  # already logged (idempotent)
        audit_id = row[0]
        if severity == "high" and ALERTS_LIVE:
            if _send(summary, matter):
                cur.execute("UPDATE agent_audit SET delivered_at = now() WHERE id = %s", (audit_id,))
        return audit_id
    finally:
        c.close()


def _send(summary, matter):
    """Immediate operator alert via tg_send (S14 sanitize + no-double-tap pacing). $0 (direct Telegram)."""
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from tg_send import send
        text = (f"[{matter}] " if matter else "") + summary
        ok, _info = send(chat_id=JONATHAN_CHAT_ID, text=text, source="agent_alert")
        return ok
    except Exception:
        return False  # never let a delivery hiccup break the agent's run


def recent(conn, hours=24, severities=("medium", "low")):
    """Read recent agent_audit rows for the digest. Returns list of (agent, matter, severity, summary, grounding)."""
    cur = conn.cursor()
    cur.execute(
        """SELECT agent_name, matter_code, severity, summary, grounding
             FROM agent_audit
            WHERE created_at > now() - (%s || ' hours')::interval
              AND severity = ANY(%s)
            ORDER BY array_position(ARRAY['high','medium','low']::text[], severity), created_at DESC""",
        (hours, list(severities)))
    return cur.fetchall()
