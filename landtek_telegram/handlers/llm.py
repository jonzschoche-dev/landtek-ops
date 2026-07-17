#!/usr/bin/env python3
"""landtek_telegram/handlers/llm.py — conversational LLM for non-vault messages.

Direct Anthropic SDK call. No n8n. Used when a message is from a real
human, has text content, but isn't a deterministic vault command.

System prompt is TIGHT and focused:
  - Leo is the LandTek assistant
  - In the DB group, his job is filing coordination with Kristyle and Jonathan
  - In private chats, he's an aide for case/operations questions
  - Plain language, brief, warm
  - Don't invent. If unknown, say so.

When Kristyle/Jonathan describes a vault event in narrative form ("Kristyle
labeled the first document" / "we just put the affidavit in folder AFF-1"),
the LLM should propose the structured command back and ask one short
confirmation question.

Reads context from chat_notes + vault state so replies are grounded.
"""
from __future__ import annotations
import json
import os
import sys
import urllib.request
import urllib.error

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
try:
    from tg_send import send as tg_send
except Exception:
    tg_send = None

# NB: the Anthropic tool-loop (and its LEO_TOOLS consumer) was RETIRED here (deploy_965, A85 —
# one brain owns replies). The tool registry `landtek_telegram/leo_tools.py` stays as the source
# for porting those tools into the governed spine (agent_specs/004 §what-moves-where).
sys.path.insert(0, "/root/landtek")

PG_DSN = os.environ.get("LANDTEK_TG_PG_DSN",
                        "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
DB_GROUP = "-5138695222"
JONATHAN = "6513067717"
KRISTYLE = "5992075757"

def _reply(chat_id, text):
    if tg_send is None:
        print(f"[llm] would reply: {text[:120]}", file=sys.stderr)
        return False
    ok, _ = tg_send(chat_id=str(chat_id), text=text, source="llm_handler",
                    override_pacing=True, override_rate_limit=True,
                    human_readable=False)
    return ok


def _resolve_client_code(sender_id: str) -> str | None:
    """Map Telegram sender → client_code (channel_users / authorized_users)."""
    if not sender_id:
        return None
    try:
        conn = psycopg2.connect(PG_DSN)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("""
            SELECT cu.mapped_client_code
              FROM channel_users cu
              JOIN channels c ON c.id = cu.channel_id
             WHERE c.name = 'telegram' AND cu.channel_user_id = %s
               AND coalesce(cu.mapped_client_code, '') <> ''
             LIMIT 1""", (str(sender_id),))
        r = cur.fetchone()
        if r and r[0]:
            cur.close(); conn.close()
            return r[0]
        # authorized_users.role owner/operator → no client scope; leave None
        # filing_assistant / client rows sometimes carry case hints in name only
        cur.close(); conn.close()
    except Exception:
        pass
    return None


def _fetch_title_docs(sender_id: str, text: str) -> tuple[str | None, str | None]:
    """Shared title pack (scripts/title_fetch) — Telegram + Messenger same ability."""
    sys.path.insert(0, "/root/landtek/scripts")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
    try:
        import title_fetch as tf
    except Exception as e:
        return None, f"title_fetch_import:{e}"
    client = _resolve_client_code(str(sender_id))
    if not client and str(sender_id) == JONATHAN:
        client = "MWK-001"
    if not client and str(sender_id) != JONATHAN:
        return (
            "I can only pull titles for an approved client scope. "
            "Ask Jonathan to map your access, or send the title number again after approval.",
            None,
        )
    try:
        conn = psycopg2.connect(PG_DSN)
        conn.autocommit = True
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        pack, err = tf.fetch_title_pack(cur, client, text)
        cur.close(); conn.close()
        return pack, err
    except Exception as e:
        return None, f"title_fetch:{type(e).__name__}:{e}"


def _wants_title_fetch(text: str) -> bool:
    sys.path.insert(0, "/root/landtek/scripts")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
    try:
        import title_fetch as tf
        return tf.wants_title_fetch(text)
    except Exception:
        return False


def _sovereign_ollama_reply(sender_id: str, text: str) -> tuple[str | None, str | None]:
    """$0 local Ollama via leo_service — same corpus/readiness spine as Messenger headless.

    Used when Anthropic is out of credit or unreachable so Telegram never dead-ends
    on a billing message while the sovereign model is up.
    """
    try:
        sys.path.insert(0, "/root/landtek/scripts")
        sys.path.insert(0, "/root/landtek")
        import leo_service as ls
        import platform_coordinator as coord
    except Exception as e:
        return None, f"sovereign_import:{type(e).__name__}:{e}"

    conn = None
    try:
        conn = psycopg2.connect(PG_DSN)
        conn.autocommit = True
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        client = None
        try:
            client = coord.client_of(cur, "telegram", str(sender_id))
        except Exception:
            client = None
        if not client:
            client = _resolve_client_code(str(sender_id))
        # Operator portfolio default only for Jonathan's Telegram id — never invent
        # a client_code for unknown senders (would leak another family's corpus).
        if not client and str(sender_id) == JONATHAN:
            client = "MWK-001"
        out = ls.generate_reply(
            cur, "telegram", str(sender_id), text, client, inbound_msg_id=None)
        cur.close()
        text_out = (out or {}).get("text")
        if text_out and str(text_out).strip():
            return str(text_out).strip(), None
        return None, f"sovereign_empty:{(out or {}).get('error') or 'no_text'}"
    except Exception as e:
        return None, f"sovereign_fail:{type(e).__name__}:{str(e)[:160]}"
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def handle(row):
    chat_id = row.get("chat_id")
    sender_id = row.get("sender_id") or ""
    text = (row.get("text_content") or "").strip()

    if not text:
        return {"handler": "llm", "outcome": "skip_empty", "reply_sent": False}

    # Staff directory gate (phone + email) — same state machine as Messenger onboarding.
    # Private chats only; group vault work is not interrupted.
    if str(chat_id) == str(sender_id) or (
        str(chat_id).lstrip("-").isdigit() and not str(chat_id).startswith("-")
    ):
        try:
            import requests as _rq
            r = _rq.post(
                "http://127.0.0.1:8765/api/onboard",
                json={
                    "channel": "telegram",
                    "channel_user_id": str(sender_id),
                    "display_name": row.get("sender_name"),
                    "message": text,
                    "adapter_logged": True,
                },
                timeout=20,
            )
            if r.status_code == 200:
                j = r.json() or {}
                if j.get("passthrough"):
                    pass  # free chat — continue to LLM
                elif j.get("reply"):
                    _reply(chat_id, j["reply"])
                    return {
                        "handler": "llm",
                        "outcome": f"staff_contact:{j.get('state_after')}",
                        "reply_sent": True,
                    }
        except Exception as e:
            print(f"[llm] staff_contact_gate: {e}", file=sys.stderr)

    # A85: same purpose router as leo_service / CAM (title, ARTA/OP, mprb, …)
    try:
        sys.path.insert(0, "/root/landtek/scripts")
        import leo_service as _ls
        import platform_coordinator as _coord
        conn_r = psycopg2.connect(PG_DSN)
        conn_r.autocommit = True
        cur_r = conn_r.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        client_r = None
        try:
            client_r = _coord.client_of(cur_r, "telegram", str(sender_id))
        except Exception:
            client_r = _resolve_client_code(str(sender_id))
        if not client_r and str(sender_id) == JONATHAN:
            client_r = "MWK-001"
        if client_r:
            route = _ls.try_purpose_route(cur_r, client_r, text,
                                          channel="telegram", channel_user_id=str(sender_id))
            if route and route.get("text"):
                _reply(chat_id, route["text"])
                cur_r.close(); conn_r.close()
                return {"handler": "llm",
                        "outcome": f"replied_route:{route.get('via')}",
                        "reply_sent": True, "preformed": True}
            # Hard gate: inquiries never reach free Ollama/Anthropic
            if _ls.is_inquiry(text):
                _reply(chat_id, getattr(_ls, "STACK_CLOSED_TEXT",
                    "I do not have a grounded answer from the corpus stack. I will not invent."))
                cur_r.close(); conn_r.close()
                return {"handler": "llm", "outcome": "stack_closed",
                        "reply_sent": True, "preformed": True}
        cur_r.close(); conn_r.close()
    except Exception as e:
        print(f"[llm] purpose_route: {e}", file=sys.stderr)

    # ── Sovereign spine ONLY (deploy_965): the Anthropic tool-loop is RETIRED per A85 — one brain
    # owns replies; model choice lives in the spine's config, never in a per-channel second brain.
    sov, sov_err = _sovereign_ollama_reply(str(sender_id), text)
    if sov:
        _reply(chat_id, sov)
        return {"handler": "llm", "outcome": "replied_ollama", "reply_sent": True}

    _reply(chat_id,
           "I'm having trouble thinking right now. Give me a moment, "
           "or send a vault command if it's a vault action.")
    return {"handler": "llm",
            "outcome": f"sovereign_failed:{sov_err or '?'}"[:200],
            "reply_sent": True}
