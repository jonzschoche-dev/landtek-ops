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

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("LANDTEK_LLM_MODEL", "claude-sonnet-4-5-20250929")
PG_DSN = os.environ.get("LANDTEK_TG_PG_DSN",
                        "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
DB_GROUP = "-5138695222"
JONATHAN = "6513067717"
KRISTYLE = "5992075757"

SYSTEM_PROMPT_GROUP = """You are Leo, the LandTek operations assistant.

You are in the DB group chat. Participants:
  - Jonathan Zschoche (the operator)
  - Joy Kristyle Cerdon (the filing assistant — builds the physical vault)
  - You (LeoLandtekBot)

The DB group's purpose: coordinate the physical-document vault.

Vault rules:
  Sections (codes): TCT (titles), DEED, SPA (special powers of attorney),
    AFF (notarized affidavits), TAX, PSA (civil registry), ID,
    CRT (court returning copies), RES (resolutions), CONT (contracts),
    CORR (correspondence with weight), MISC.
  Numbers run separately within each section: AFF-001, AFF-002, etc.
  Kristyle assigns the number when she labels the physical folder.

When she or Jonathan describes a vault event in plain words ("Kristyle
labeled the first document", "we just put the affidavit in folder AFF-1"),
propose the structured command back: "Sounds like AFF-1. What's the matter
— 4497 case, ARTA-1210, or another?"

Active matters (use the canonical code in any tool call):
  MWK-TCT4497 (the 4497 case / mother title), MWK-CV26360 (civil case /
  Balane), MWK-OP-PETITION (OP case), MWK-ESTATE, MWK-GUARDIANSHIP,
  MWK-ARTA-1210, MWK-ARTA-0747, MWK-ARTA-1212, MWK-ARTA-1378,
  MWK-ARTA-1319, MWK-ARTA-1321, MWK-ARTA-1891, MWK-ARTA-0690,
  MWK-ARTA-0792, PAR-CAPACUAN, PAR-GOLDEN-SAND, PAR-VITO-CRUZ,
  PAR-TCT1616.

Style:
  Plain English. No markdown bold, no bullet lists, no formal headers.
  One point per message. Warm but professional. Brief.
  When you don't know, say "I don't have that yet" — never invent.
  Never reply with a generic template like "How can I assist you?" — that
  is a failure mode. Read the actual message and respond to it.

If the sender's message is operational filing work, help them do it. If
it's a status/observation ("Kristyle has logged the first document"),
acknowledge naturally and ask the next useful question."""

SYSTEM_PROMPT_PRIVATE_JONATHAN = """You are Leo, the LandTek operations
assistant, in private chat with Jonathan Zschoche (operator).

He owns LandTek; you serve him directly. No defensive gating, no "I can't
share that" — he authorized everyone else in this system.

Style: plain English, brief, no bullet lists or markdown. One point per
message. If asked about case substance you don't have, say so honestly.
Never invent facts, dates, or document content.

The system you run on: a deterministic vault pipeline (vault_register,
vault_find, vault_queue, vault_missing, vault_last via HTTP endpoints on
:8765), plus a Python webhook receiver that replaces n8n in the critical
path. The DB group chat (chat_id -5138695222) is where you coordinate
vault entries with Kristyle (filing assistant).

Active matter for which pretrial is set August 1: Civil Case 26-360
(Zschoche v. Balane), TCT T-4497 derivative chain. Counsel: Atty.
Barandon Jr. (RTC matter only — ARTA matters are filed by Jonathan as
AIF for Patricia Keesey Zschoche).

When unsure, ask one short clarifying question."""


def _reply(chat_id, text):
    if tg_send is None:
        print(f"[llm] would reply: {text[:120]}", file=sys.stderr)
        return False
    ok, _ = tg_send(chat_id=str(chat_id), text=text, source="llm_handler",
                    override_pacing=True, override_rate_limit=True,
                    human_readable=False)
    return ok


def _recent_context(chat_id, limit=8):
    """Pull recent inbox + outbound messages for this chat to give the LLM
    real conversational context."""
    conn = psycopg2.connect(PG_DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT received_at AS ts, 'in' AS dir, sender_name AS who,
               text_content AS text
          FROM telegram_inbox
         WHERE chat_id = %s AND text_content IS NOT NULL
         ORDER BY received_at DESC LIMIT %s
    """, (str(chat_id), limit))
    in_msgs = list(cur.fetchall())
    cur.execute("""
        SELECT sent_at AS ts, 'out' AS dir, 'Leo' AS who,
               content_preview AS text
          FROM outbound_messages
         WHERE chat_id = %s AND success = true
         ORDER BY sent_at DESC LIMIT %s
    """, (str(chat_id), limit))
    out_msgs = list(cur.fetchall())
    cur.close(); conn.close()
    combined = sorted(in_msgs + out_msgs, key=lambda r: r["ts"])
    return combined[-limit*2:]


def _call_anthropic(system_prompt, user_text, context_lines):
    """Make one HTTP call to Anthropic Messages API. No SDK dependency."""
    if not ANTHROPIC_KEY:
        return None, "no_api_key"
    # Build a single user turn with the conversation history inline
    history = "\n".join(
        f"  [{r['dir']}] {r['who']}: {(r['text'] or '')[:200]}"
        for r in context_lines
    )
    user_block = (
        (f"Recent conversation in this chat:\n{history}\n\n" if history else "") +
        f"The latest message just arrived. Respond to it directly in plain "
        f"English, one short paragraph. Latest message:\n{user_text}"
    )
    body = {
        "model": MODEL,
        "max_tokens": 400,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_block}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read().decode("utf-8"))
        parts = payload.get("content") or []
        for p in parts:
            if p.get("type") == "text":
                return p.get("text", "").strip(), None
        return None, "no_text_in_response"
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:300]
        return None, f"http_{e.code}: {err_body}"
    except Exception as e:
        return None, f"call_failed: {type(e).__name__}: {str(e)[:200]}"


def handle(row):
    chat_id = row.get("chat_id")
    sender_id = row.get("sender_id") or ""
    text = (row.get("text_content") or "").strip()

    if not text:
        return {"handler": "llm", "outcome": "skip_empty", "reply_sent": False}

    if chat_id == DB_GROUP:
        system_prompt = SYSTEM_PROMPT_GROUP
    elif sender_id == JONATHAN:
        system_prompt = SYSTEM_PROMPT_PRIVATE_JONATHAN
    else:
        # Default to the group prompt for any other authorized chat (Kristyle direct)
        system_prompt = SYSTEM_PROMPT_GROUP

    context = _recent_context(chat_id)
    reply, err = _call_anthropic(system_prompt, text, context)
    if reply is None:
        # API failed — fall back to a concise honest message rather than ghost
        _reply(chat_id, "I'm having trouble thinking right now — give me a moment, "
                       "or send the message as a vault command if it's a vault action.")
        return {"handler": "llm", "outcome": f"api_failed:{err[:80]}",
                "reply_sent": True}

    _reply(chat_id, reply)
    return {"handler": "llm", "outcome": "replied", "reply_sent": True}
