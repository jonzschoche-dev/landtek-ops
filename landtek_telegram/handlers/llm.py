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

SYSTEM_PROMPT_GROUP_TEMPLATE = """You are Leo, the LandTek operations assistant.

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

ALL ACTIVE MATTERS (canonical codes — recognize ALL of these; "6839"
means MWK-CV6839, "26360" means MWK-CV26360, etc.):
{matters_block}

CURRENT VAULT STATE — recently registered entries:
{vault_state_block}

FORMAT — STRICT:
  Plain English prose ONLY. No markdown. No asterisks. No headers like
  "Section:" or "Locator:". No bullet lists. No numbered lists. No emojis.
  No 👉 or any other character to point at something. No instructional
  scaffolding like "Reply with your answer." Talk like a coworker across
  a desk.
  One point per message. Warm but professional. Brief.
  When you don't know, say "I don't have that yet" — never invent.
  Never reply with a generic template like "How can I assist you?" — that
  is a failure mode. Read the actual message and respond to it.
  NEVER guess a next-available locator. The NEXT AVAILABLE NUMBER block
  above is the truth — use it.

CRITICAL — do not lie about actions:
  You CANNOT directly register vault entries through chat — the deterministic
  vault command path does that. NEVER say "I'll log it" or "I'll record CORR-001"
  or "logging now" unless the message contains a structured command that the
  vault handler can parse. Instead say: "Once you (or Jonathan) confirm the
  exact section, number, and matter, that gets registered through the vault
  command — type something like 'vault CORR-1 letter to Judge Dizon for
  MWK-CV6839' and it goes in."

If the sender's message is operational filing work, help them do it. If
it's a status/observation ("Kristyle has logged the first document"),
acknowledge naturally and ask the next useful question."""

SYSTEM_PROMPT_PRIVATE_JONATHAN_TEMPLATE = """You are Leo, the LandTek
operations assistant, in private chat with Jonathan Zschoche (operator).

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

ALL MATTERS Jonathan manages (recognize ALL of these — "6839" means
MWK-CV6839, "1210" means MWK-ARTA-1210, etc.):
{matters_block}

CURRENT VAULT STATE — recently registered entries:
{vault_state_block}

CRITICAL — do not lie about actions:
  You CANNOT directly register vault entries through chat. NEVER say "I'll
  log it" / "I'll record" / "logging now" unless you literally see the
  structured command in the message. Coach Jonathan to send the vault
  command if a registration is needed.

When unsure, ask one short clarifying question."""


def _reply(chat_id, text):
    if tg_send is None:
        print(f"[llm] would reply: {text[:120]}", file=sys.stderr)
        return False
    ok, _ = tg_send(chat_id=str(chat_id), text=text, source="llm_handler",
                    override_pacing=True, override_rate_limit=True,
                    human_readable=False)
    return ok


def _live_matters_block():
    """Pull every matter from the matters table — live, not hardcoded.
    Returns a string block to inject into the system prompt."""
    try:
        conn = psycopg2.connect(PG_DSN)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT matter_code, case_file, status
              FROM matters
             WHERE matter_code NOT LIKE 'AUTO-%' AND matter_code NOT LIKE 'ARCHIVE-%'
             ORDER BY case_file NULLS LAST, matter_code
        """)
        rows = cur.fetchall()
        cur.close(); conn.close()
    except Exception:
        return "(matter list unavailable — query failed)"
    by_book = {}
    for r in rows:
        book = r["case_file"] or "unfiled"
        by_book.setdefault(book, []).append(f"{r['matter_code']} ({r['status']})")
    lines = []
    for book, codes in sorted(by_book.items()):
        lines.append(f"  {book}: " + "; ".join(codes))
    return "\n".join(lines) if lines else "(no matters)"


def _live_vault_state(limit=12):
    """Recent vault entries + computed next-available number per section.

    The next-available block is what Leo MUST reference when suggesting a
    locator. Don't make him guess — give him the answer.
    """
    SECTIONS = ["TCT", "DEED", "SPA", "AFF", "TAX", "PSA", "ID",
                "CRT", "RES", "CONT", "CORR", "MISC"]
    try:
        conn = psycopg2.connect(PG_DSN)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT vault_section, vault_number, smart_filename, case_file
              FROM documents
             WHERE master_form = 'physical'
             ORDER BY id DESC
             LIMIT %s
        """, (limit,))
        recent = cur.fetchall()
        # Next-available per section
        cur.execute("""
            SELECT vault_section,
                   COALESCE(MAX(vault_number), 0) + 1 AS next_num
              FROM documents
             WHERE master_form = 'physical'
             GROUP BY vault_section
        """)
        next_map = {r["vault_section"]: r["next_num"] for r in cur.fetchall()}
        cur.close(); conn.close()
    except Exception:
        return "(vault state unavailable)"

    lines = ["NEXT AVAILABLE NUMBER per section (use these when suggesting a locator):"]
    for s in SECTIONS:
        n = next_map.get(s, 1)
        lines.append(f"  {s}: next = {s}-{n:03d}")
    if recent:
        lines.append("")
        lines.append("Recent entries (most recent first):")
        for r in recent:
            lines.append(
                f"  {r['vault_section']}-{r['vault_number']:03d}: "
                f"{(r['smart_filename'] or '')[:90]}"
            )
    else:
        lines.append("")
        lines.append("(no entries yet — every section starts at 001)")
    return "\n".join(lines)


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

    # Build live blocks at call time so matters and vault state are always fresh
    matters_block = _live_matters_block()
    vault_block = _live_vault_state()

    if chat_id == DB_GROUP:
        system_prompt = SYSTEM_PROMPT_GROUP_TEMPLATE.format(
            matters_block=matters_block, vault_state_block=vault_block)
    elif sender_id == JONATHAN:
        system_prompt = SYSTEM_PROMPT_PRIVATE_JONATHAN_TEMPLATE.format(
            matters_block=matters_block, vault_state_block=vault_block)
    else:
        system_prompt = SYSTEM_PROMPT_GROUP_TEMPLATE.format(
            matters_block=matters_block, vault_state_block=vault_block)

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
