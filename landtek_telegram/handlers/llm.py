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

# Import Leo's tool definitions + dispatcher
sys.path.insert(0, "/root/landtek")
try:
    from landtek_telegram.leo_tools import LEO_TOOLS, run_tool
    print(f"[llm] ✓ leo_tools loaded: {len(LEO_TOOLS)} tools available",
          file=sys.stderr)
except Exception as _e:
    import traceback
    print(f"[llm] ✗ leo_tools NOT LOADED: {_e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    LEO_TOOLS, run_tool = [], None

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

YOUR MEMORY — STRICT:
  The CURRENT VAULT STATE block above is the ENTIRE truth about what is
  registered in the vault. Nothing else. If a locator (like CORR-003) is
  not in that block, it does NOT EXIST in the vault yet — even if
  someone earlier in the conversation said "let's call it CORR-003" or
  "we'll register that as CORR-003". Discussion is not registration.
  Only the live vault state shown above is registered.

### TOOL-FIRST RULE (deploy_380) — MANDATORY ###

Before you EVER ask Kristyle or Jonathan a clarifying question about a
document, matter, or vault entry, you MUST call at least one tool. No
exceptions.

When a message describes a document (letter, affidavit, deed, etc.):
  STEP 1 (always): call query_documents with the key terms
                   (name_contains and/or text_contains and/or date range)
  STEP 2: if you find a candidate, call read_document to confirm
  STEP 3: check the live VAULT STATE block — does a vault entry already
          exist for this document? If yes, surface that fact and ASK
          NOTHING.
  STEP 4: if no existing vault entry, call find_matter_for_party
          to determine the matter, then call vault_register yourself
  STEP 5: reply ONE plain-language sentence with what you did

The phrase "Which matter does this belong to?" is BANNED unless you have
already called query_documents AND find_matter_for_party AND both came
back empty.

EXAMPLE — DO THIS:
  Kristyle: "Letter to Hon. Alex Pajarillo dated October 1, 2025"
  Leo (internally):
    1. query_documents(name_contains="Pajarillo", date_from="2025-09-25",
                       date_to="2025-10-10") → [doc 597]
    2. read_document(597) → confirms it's the Oct 1 letter
    3. find_matter_for_party("Alex Pajarillo") → MWK-ARTA-0747
    4. vault_register(section="CORR", number=<next>, ...,
                      matter_code="MWK-ARTA-0747",
                      related_matters=["MWK-TCT4497", "MWK-ESTATE",
                                       "MWK-ARTA-DILG"])
  Leo (to Kristyle): "Logged CORR-N. Oct 1 letter to Mayor Pajarillo,
                     ARTA-0747 case, with cross_proof to the title chain."

EXAMPLE — DO NOT DO THIS:
  Kristyle: "Letter to Hon. Alex Pajarillo dated October 1, 2025"
  Leo: "Which matter does this belong to — the 4497 case or another?"
  ← BANNED. You didn't call any tools.

  You have function-calling tools. Use them to do real work yourself
  instead of asking the humans for what you can find:

  - query_documents : search the digital corpus by name/date/keyword/matter
  - read_document   : full classification + date + text excerpt for a doc id
  - search_drive    : find files in the LANDTEK Drive (for newly uploaded)
  - vault_register  : CREATE a vault entry directly — section, number,
                      description, matter_code, related_matters[]
  - vault_find / vault_queue / vault_missing / vault_last : vault state
  - find_matter_for_party : given a person/org name, find which matters
                            they appear in across the corpus
  - link_documents  : cross-reference two documents (reply_to, related, etc.)

  When Kristyle says "letter from Jonathan to Mayor Pajarillo dated
  October 1, 2025", your job (no questions to humans first):
    1. query_documents(name_contains="Pajarillo", date_from="2025-09-25",
                       date_to="2025-10-10")  → find the doc
    2. read_document(doc_id=...) to confirm
    3. find_matter_for_party(name="Alex Pajarillo") if matter unclear
    4. vault_register(section="CORR", number=<next available>,
                      description="...", matter_code="MWK-ARTA-0747",
                      related_matters=["MWK-TCT4497", "MWK-ESTATE",
                                       "MWK-ARTA-DILG"])
    5. Reply ONE plain-language line confirming what you logged.

  YOU CAN REGISTER VAULT ENTRIES NOW. The old rule about coaching
  humans to send vault commands is SUPERSEDED. Just call vault_register
  with the right arguments after you've done the research.

  Only ask the human when you genuinely can't determine something from
  the tools — and then ONE short question, not a quiz.

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

YOUR MEMORY — STRICT:
  The CURRENT VAULT STATE block above is the ENTIRE truth about what is
  registered. Discussion is not registration — if a locator is not in
  that block, it doesn't exist yet.

NO PROMISES OF ACTION YOU CAN'T TAKE:
  You CANNOT register vault entries yourself. NEVER say "I'll log it",
  "I'll label it", "I'll record", "logging now". Instead: tell Jonathan
  the proposed locator and ask him to send a vault command
  ("vault CORR-3 letter to Dela Fuente for the estate case") so the
  deterministic handler can register it. Coaching beats lying.

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


def _call_anthropic_once(system_prompt, messages, max_tokens=600):
    """Single Anthropic API call. Returns (full_response_payload, error)."""
    if not ANTHROPIC_KEY:
        return None, "no_api_key"
    body = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": messages,
    }
    if LEO_TOOLS:
        body["tools"] = LEO_TOOLS
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
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:300]
        return None, f"http_{e.code}: {err_body}"
    except Exception as e:
        return None, f"call_failed: {type(e).__name__}: {str(e)[:200]}"


def _call_anthropic(system_prompt, user_text, context_lines):
    """Multi-turn Anthropic call with tool use. Leo can search the corpus,
    read documents, register vault entries, etc. via tools.

    Loops up to MAX_TOOL_ROUNDS times, executing every tool_use block the
    model emits and feeding results back in.
    """
    MAX_TOOL_ROUNDS = 6

    history = "\n".join(
        f"  [{r['dir']}] {r['who']}: {(r['text'] or '')[:200]}"
        for r in context_lines
    )
    user_block = (
        (f"Recent conversation in this chat:\n{history}\n\n" if history else "") +
        f"The latest message just arrived. Use your tools as needed to "
        f"answer it correctly. Respond in plain English, one short "
        f"paragraph. Latest message:\n{user_text}"
    )
    messages = [{"role": "user", "content": user_block}]

    for round_idx in range(MAX_TOOL_ROUNDS):
        payload, err = _call_anthropic_once(system_prompt, messages)
        if payload is None:
            return None, err

        content = payload.get("content", [])
        stop_reason = payload.get("stop_reason")

        # If model wants to call tools, execute them and continue
        tool_uses = [c for c in content if c.get("type") == "tool_use"]
        text_parts = [c for c in content if c.get("type") == "text"]

        if not tool_uses:
            # Done — return the text
            final = "\n".join(p.get("text", "") for p in text_parts).strip()
            return (final or "(no reply)"), None

        # Append assistant turn (with tool_use blocks) verbatim
        messages.append({"role": "assistant", "content": content})

        # Execute each tool and build tool_result blocks
        tool_results = []
        for tu in tool_uses:
            name = tu.get("name")
            tu_id = tu.get("id")
            inp = tu.get("input") or {}
            print(f"[leo:tool] {name}({json.dumps(inp)[:120]})", file=sys.stderr)
            if run_tool is None:
                result_text = "Tools unavailable (run_tool not loaded)"
            else:
                result_text = run_tool(name, inp)
            print(f"[leo:tool] {name} -> {str(result_text)[:200]}", file=sys.stderr)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu_id,
                "content": str(result_text)[:8000],
            })
        messages.append({"role": "user", "content": tool_results})

    return ("(tool loop exhausted)", None)


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
