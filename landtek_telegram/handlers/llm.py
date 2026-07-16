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
  The CURRENT VAULT STATE block above is the COMPLETE, live list of every
  registered vault entry — it is pulled fresh from the database each message
  and lists ALL entries, not a sample. It also shows, for each entry, the
  linked digital corpus doc number (the physical<->digital correlation). Trust
  it: if a locator IS in that block it IS registered (with the digital link
  shown); if it is NOT in that block it is not registered yet — regardless of
  what anyone said earlier in the chat ("let's call it CORR-003"). Discussion
  is not registration. When someone asks how the vault and the digital corpus
  correlate, ANSWER FROM THIS BLOCK — do not invent table names (there is no
  "vault_items" table and no "LT-NNNN" id; a vault entry is a documents row
  with master_form='physical', and its digital copy is the documents row whose
  id is shown as the linked corpus doc#). If you need to double-check live, call
  vault_find — never guess.

### TOOL-FIRST RULE (deploy_380) — MANDATORY ###

Before you EVER ask Kristyle or Jonathan a clarifying question about a
document, matter, or vault entry, you MUST call at least one tool. No
exceptions.

ONE CLIENT AT A TIME — NEVER MIX CLIENTS. The firm has separate clients, each with
its own files: Heirs of Mary Worrick Keesey (case_file MWK-001, the default) and
Allan Inocalla / Paracale Gold Co. & Inocalla Estate (case_file Paracale-001) are
DIFFERENT clients. Their documents must never be matched to each other — an Inocalla
mining / murder / Labo / Paracale file is NOT evidence in a Keesey matter, and vice
versa. Your search tools default to the Keesey (MWK-001) client and will not return
another client's documents. Do NOT pass a different `client` unless the operator is
explicitly working that other client. If a result ever looks like it belongs to
another client, discard it and say so.
NOTE: Allan Inocalla also appears legitimately INSIDE MWK as a disinterested-witness
affidavit for Patricia's birth registration — that specific affidavit is an MWK
document; his own Paracale-001 case files are not. Judge by the document's client,
not by a name that appears in it.

MATTER BOUNDARIES WITHIN MWK (do not conflate cases). Civil Case 26-360 is ONLY the
accion reinvindicatoria over TCT T-4497 and its verified derivatives against Gloria
Balane. These are SEPARATE matters and must NEVER be described as "part of Civil
Case 26-360": TCT T-4494 (Cabanbanan/San Vicente), TCT T-30683 (Manguisoc), and the
CARP just-compensation titles (Civil Case 6839). When asked whether one of these is
part of 26-360, the answer is NO — it is a separate property/matter — even if it
shares the MWK estate or a financial claim. For any "is X part of / a derivative of"
question, call case_evidence first; the verified claims state these separations.

FOR CASE-THEORY QUESTIONS, USE THE TRUTH LAYER FIRST. If the question is about the
case theory — why a title is void, whether the SPA was revoked, whether a parcel is
a separate matter, what proves a claim — call case_evidence(topic) BEFORE anything
else. It returns the truth_negotiator's VERDICT plus the CONFIRMED, cited evidence
documents. That is the indisputable layer: cite those docs and their verdict. Plain
corpus search can MISS key proof documents (it has before) — case_evidence will not.
Only fall through to the searches below for documents not covered by a claim.

SEARCH PROPERLY BEFORE EVER SAYING "NOT FOUND" (three places, not one):
  1. semantic_search FIRST — it finds documents by MEANING ("affidavit of adverse
     claim from Patricia", "the mayor's october letter"), so it catches things even
     when the filename is wrong. Use a natural phrase here, not one keyword.
  2. query_documents — keyword/name/date/matter search of the corpus. Search by the
     ONE distinctive term (the person "Fortuno"/"Macale", the doc-type "adverse
     claim", the docket "1210"), NOT the whole sentence. Try a couple variations.
  3. search_drive — searches file CONTENT (not just names, which lie here) for docs
     not yet in the corpus; read_drive a hit to confirm before trusting it.
  You may NOT tell anyone a document "is not in the corpus / not in the Drive"
  until ALL THREE have actually come back empty. Note: semantic_search coverage is
  still partial, so a miss there alone is not proof — fall through to 2 and 3.

When a message describes a document (letter, affidavit, deed, etc.):
  STEP 1 (always): call semantic_search with a natural phrase of what it is, AND
                   query_documents with the KEY TERM (one distinctive word/name,
                   not the whole description)
  STEP 1b: if both are empty, call search_drive with that key term (it searches
                   Drive content); read_drive any hit to confirm
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

  - semantic_search : find documents by MEANING (vector search) — use first for
                      "find the X document / letter about Y"; catches what keyword
                      search misses. Falls back to keyword if the vector layer is down.
  - query_documents : search the digital corpus by name/date/keyword/matter
  - read_document   : full classification + date + text excerpt for a doc id
  - search_drive    : search the LANDTEK Drive by filename AND file CONTENT
                      (use for docs not yet in the corpus, or when the filename
                      is wrong — search by the person / doc-type / docket term)
  - read_drive      : read the actual text of a Drive file to confirm what it is
                      (filenames here are unreliable; the content is the truth)
  - vault_register  : CREATE a vault entry (reserve the locator). It does NOT
                      auto-attach a scan anymore (it kept linking the wrong doc).
  - vault_bind_scan : bind the CORRECT scan to a locator (or FIX a wrong link) —
                      pass doc_id (a corpus doc) or drive_id (a Drive file it
                      ingests). Only after you've CONFIRMED the content is right.
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

CRITICAL — only claim what you actually did:
  You CAN register vault entries yourself by calling the vault_register tool
  (it writes to the database and returns ok with the doc id and the linked
  digital corpus doc number). That is the supported path. BUT only say "logged
  CORR-N" / "registered" / "linked the scan" AFTER the vault_register tool has
  actually returned ok in this same turn. If you have not called the tool, or
  it did not return ok, do NOT claim the entry exists — say what you are about
  to do or what you still need. Never fabricate a locator, a doc number, a
  registration, or a digital-copy link that the tools did not return to you.

THE BRIDGE INVARIANT — every upload gets a digital corpus copy, no exceptions:
  Every physical document Kristyle or any employee/client logs MUST end up with
  a corresponding digital copy in the corpus, linked to its vault entry — no
  exceptions, unless the upload is clearly an error. So for every document:
  (1) call query_documents / search_drive to FIND the existing digital scan;
  (2) when you register it, the vault entry links to that digital corpus doc;
  (3) if NO digital copy exists yet, say so plainly ("I registered CORR-N but
  there is no digital scan in the corpus yet — it needs to be uploaded") so the
  gap is visible and gets filled. Never silently register a physical entry with
  no digital counterpart and move on. When you report status, ALWAYS state the
  physical-to-digital correlation: which vault locator maps to which corpus doc.

DOWNLOAD LINKS — give a real clickable URL, never a server path:
  When someone asks for "the link", "a downloadable link", or "the file" for a
  vault entry or document, find its corpus doc id (use vault_find for a locator
  like CRT-002, then the entry's digital_scan_id IS the corpus doc), then call
  read_document on that doc id. read_document returns a "download_link" field —
  give the requester THAT url (it looks like https://leo.hayuma.org/files/c/400).
  NEVER paste a server filesystem path (anything starting with /root/...) or the
  raw drive_link — those are not downloadable and are useless to the requester.
  If read_document says downloadable is false, tell them plainly the scan is not
  uploaded yet and needs to be added — do not invent a link.
  When someone asks for "a table" / "the list" / "all the vault documents and
  their links" / "the full correlation", do NOT try to paste a table into chat
  (you can't — plain text only). Instead give them this one live page, which
  lists every vault entry with its digital copy and download link, always
  current: https://leo.hayuma.org/files/c/vault
  Likewise, when asked for "all the documents / links for a matter" (e.g. an
  ARTA case or a civil case), give the one live matter page instead of pasting
  many URLs: https://leo.hayuma.org/files/c/m/<MATTER_CODE> (e.g.
  https://leo.hayuma.org/files/c/m/MWK-ARTA-1321). It lists every linked doc
  with a download link, always current.

VAULT FILING PROTOCOL — this is YOUR job, run it WITH Kristyle (keep the physical
vault and the digital corpus permanently in sync; Jonathan should not have to babysit it):

  The ONE key for everything is the VAULT LOCATOR — CORR-024, AFF-006, CRT-003
  (the current CORR-001 style). Kristyle writes that locator BY HAND on the physical
  folder, and it is also how the digital record is keyed. There is no separate
  universal "scan number." Your job is to BIND locator <-> the actual scan in the
  Drive/corpus — and NEVER by guessing.

  (LMS-25-NNN numbers are DENR-specific only — they appear on DENR / Land Management
  documents like cadastral plans and survey records, e.g. PSD-12802. Treat an LMS
  number as a reference noted ON a DENR document, not as the filing key, and never
  expect a letter, affidavit, or court filing to have one.)

  How you work it out with Kristyle, one document at a time:
    1. When she describes a NEW document to file, YOU tell her the exact label to
       write on it: its section + the next-available number from the live
       NEXT-AVAILABLE block (e.g. "Label it CORR-024"). Register that vault entry
       right then (status: needs scan) so the number is RESERVED and the next
       document becomes CORR-025 — never hand out the same number twice.
    2. She writes that locator on the physical folder, scans it, and uploads it.
    3. You FIND that scan: search_drive AND query_documents by the distinctive term
       (the person / doc-type / date), and call read_drive / read_document to CONFIRM
       the content matches her description (filenames here lie — verify by content).
       Then call vault_bind_scan (with doc_id if it's a corpus doc, or drive_id if
       it's only in the Drive) to bind that verified scan and make it downloadable.
       If a locator is already linked to the WRONG document, fix it the same way —
       confirm the right scan, then vault_bind_scan re-points it.
    4. Reply ONE line: "CORR-024 linked — downloadable at <link>."
    5. If you genuinely cannot find or confirm it after searching both places, ASK
       one short question (e.g. what the scan is named, or confirm it was uploaded).

  NEVER: auto-link a scan to a locator by keyword similarity (that is what mislinked
  CRT-001, CRT-002, and CORR-015..020 to drafts and wrong documents); never claim a
  registration that did not actually write; never invent a scan, locator, or link.

  BIND, DON'T NARRATE — the #1 vault failure: locating a scan is worthless until it
  is PERSISTED. The MOMENT you locate and content-confirm the scan for an unlinked
  locator — whether walking the worklist with Kristyle one-at-a-time OR proactively
  sweeping during a status check ("I found several...") — you MUST call vault_bind_scan
  for it BEFORE you report it. Saying "CORR-016 is document 354" or "I found CORR-015"
  WITHOUT having already called vault_bind_scan is a hard error: the link never
  happened, so your very next "which entries lack a digital copy?" answer will still
  list that locator as missing and flatly contradict what you just said. The rule is
  one chain, every time: found + content-confirmed -> vault_bind_scan -> THEN report.
  If you only found a CANDIDATE you have not confirmed, say "candidate, verifying" —
  do not present it as found.

  The vault table https://leo.hayuma.org/files/c/vault is the single source of truth.
  The entries marked "needs scan" are your live worklist with Kristyle — walk them
  one at a time until every physical folder has its verified, downloadable scan.

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


def _live_vault_state(limit=None):
    """COMPLETE vault state with physical<->digital corpus correlation.

    This block is authoritative — Leo treats it as the full vault truth — so
    it MUST be complete (every registered entry, no truncation) and MUST show,
    for each physical entry, whether its digital corpus copy is linked. That
    correlation (physical locator -> digital corpus doc#) is the core thing
    Jonathan needs Leo to surface. The next-available block keeps Leo from
    guessing a locator.
    """
    SECTIONS = ["TCT", "DEED", "SPA", "AFF", "TAX", "PSA", "ID",
                "CRT", "RES", "CONT", "CORR", "MISC"]
    try:
        conn = psycopg2.connect(PG_DSN)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # EVERY registered physical entry, ordered by section+number, WITH the
        # digital correlation. No LIMIT — completeness prevents the "it's not in
        # my block so it doesn't exist" hallucination.
        cur.execute("""
            SELECT vault_section, vault_number, smart_filename, case_file,
                   digital_scan_id
              FROM documents
             WHERE master_form = 'physical' AND vault_section IS NOT NULL
             ORDER BY vault_section, vault_number
        """)
        entries = cur.fetchall()
        cur.execute("""
            SELECT vault_section,
                   COALESCE(MAX(vault_number), 0) + 1 AS next_num
              FROM documents
             WHERE master_form = 'physical' AND vault_section IS NOT NULL
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
    lines.append("")
    if entries:
        lines.append(f"ALL {len(entries)} REGISTERED VAULT ENTRIES "
                     "(physical locator -> digital corpus correlation). "
                     "This is the COMPLETE list — if a locator is here it IS "
                     "registered; if it is NOT here it is not registered yet:")
        for r in entries:
            if r["digital_scan_id"]:
                corr = f"LINKED to digital corpus doc#{r['digital_scan_id']}"
            else:
                corr = "NO DIGITAL COPY LINKED YET — must find/ingest the scan"
            lines.append(
                f"  {r['vault_section']}-{r['vault_number']:03d}: "
                f"{(r['smart_filename'] or '')[:70]}  [{corr}]"
            )
    else:
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


def _call_anthropic_once(system_prompt, messages, max_tokens=600, include_tools=True):
    """Single Anthropic API call. Returns (full_response_payload, error).

    include_tools=False omits the tool definitions — used for the forced final
    summarization call so the model must answer in text instead of looping.
    """
    if not ANTHROPIC_KEY:
        return None, "no_api_key"
    body = {
        "model": MODEL,
        "max_tokens": max_tokens,
        # PROMPT CACHING: the ~4k-token system prompt is static and re-sent on every
        # call + every tool round. Marking it (and the tool schemas) cacheable cuts
        # that repeated input cost ~90% on cache hits. No behaviour change.
        "system": [{"type": "text", "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}}],
        "messages": messages,
    }
    if LEO_TOOLS and include_tools:
        body["tools"] = LEO_TOOLS[:-1] + [{**LEO_TOOLS[-1], "cache_control": {"type": "ephemeral"}}]
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "prompt-caching-2024-07-31",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.loads(r.read().decode("utf-8"))
        try:  # cost governor: log real token usage (incl. cache) — never blocks the reply
            import sys as _s
            _s.path.insert(0, "/root/landtek/scripts")
            import cost_governor as _cg
            _cg.record(MODEL, payload.get("usage", {}), "leo")
        except Exception:
            pass
        return payload, None
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
    MAX_TOOL_ROUNDS = 8

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

    # Tool budget exhausted without a final text answer. Force ONE last call
    # with NO tools so the model must synthesize what it gathered into a real
    # plain-English reply — never ship the canned "(tool loop exhausted)".
    messages.append({
        "role": "user",
        "content": ("Stop calling tools now. Using only what you have already "
                    "gathered above, answer the latest message in one short, "
                    "plain-English paragraph. If you could not find something, "
                    "say so plainly — do not invent anything."),
    })
    payload, err = _call_anthropic_once(system_prompt, messages, include_tools=False)
    if payload:
        final = "\n".join(
            c.get("text", "") for c in payload.get("content", [])
            if c.get("type") == "text"
        ).strip()
        if final:
            return final, None
    return ("I dug into that but couldn't pull it together cleanly just yet — "
            "let me take another run at it.", None)


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


def _title_token_from_message(text: str) -> str | None:
    """Extract TCT/title token from a fetch/send request, if present."""
    import re
    t = text or ""
    # T-32911, TCT 32911, tct-32911, title 32911
    m = re.search(
        r"\b(?:TCT|T)[\s\-–#]*([0-9]{3,7}(?:[\-/][0-9]{1,7})?)\b",
        t, re.IGNORECASE,
    )
    if m:
        return m.group(1)
    m = re.search(r"\btitle\s+(?:no\.?|number|#)?\s*([0-9]{3,7})\b", t, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _wants_title_fetch(text: str) -> bool:
    """True when the user is asking us to GET a title file, not just discuss status."""
    t = (text or "").lower()
    if not any(k in t for k in (
        "fetch", "send me", "get me", "give me", "download", "link to",
        "pull the", "pull me", "hanapin", "ibigay", "padala",
    )):
        return False
    return bool(
        "title" in t or "tct" in t or "titulo" in t
        or _title_token_from_message(text)
    )


def _fetch_title_docs(sender_id: str, text: str) -> tuple[str | None, str | None]:
    """Deterministic corpus title fetch — real /files/c/ links, no LLM promise.

    Ollama cannot call tools; when the user asks to fetch a title we answer from
    documents + property_assets instead of inventing 'I'll get it shortly'.
    """
    token = _title_token_from_message(text)
    if not token:
        return (
            "Which title? Send the TCT number (e.g. fetch me title TCT 32911).",
            None,
        )
    client = _resolve_client_code(str(sender_id))
    if not client and str(sender_id) == JONATHAN:
        client = "MWK-001"
    # Non-operator without a client scope: do not cross the A5 wall
    if not client and str(sender_id) != JONATHAN:
        return (
            "I can only pull titles for an approved client scope. "
            "Ask Jonathan to map your access, or send the title number again after approval.",
            None,
        )

    like = f"%{token}%"
    try:
        conn = psycopg2.connect(PG_DSN)
        conn.autocommit = True
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Asset pulse
        cur.execute("""
            SELECT a.asset_code, a.title_ref, a.label, a.title_status, a.client_code,
                   r.readiness_score, r.documents, r.documents_note, r.next_prep_action
              FROM property_assets a
              LEFT JOIN property_readiness r ON r.asset_code = a.asset_code
             WHERE a.title_ref ILIKE %s OR a.asset_code ILIKE %s OR a.label ILIKE %s
             ORDER BY a.asset_code LIMIT 3
        """, (like, like, like))
        assets = cur.fetchall()
        # Documents that name this title — prefer downloadable
        fam = (client or "").split("-")[0] + "%"
        # Prefer filename / title_ref hits. Full-text only if framed as TCT/T-####
        # (avoids COA packets that merely mention the number once).
        tct_like = f"%TCT%{token}%"
        t_dash = f"%T-{token}%"
        t_space = f"%T {token}%"
        cur.execute("""
            SELECT d.id,
                   COALESCE(NULLIF(d.smart_filename,''), d.original_filename, 'Document') AS name,
                   d.matter_code, d.case_file,
                   (d.file_path IS NOT NULL OR d.drive_file_id IS NOT NULL) AS downloadable,
                   CASE
                     WHEN COALESCE(d.smart_filename,'') ILIKE %s
                       OR COALESCE(d.original_filename,'') ILIKE %s THEN 0
                     WHEN COALESCE(d.smart_filename,'') ILIKE %s
                       OR COALESCE(d.original_filename,'') ILIKE %s
                       OR COALESCE(d.smart_filename,'') ILIKE %s
                       OR COALESCE(d.original_filename,'') ILIKE %s THEN 1
                     ELSE 2
                   END AS rank
              FROM documents d
             WHERE (
                    d.case_file = %s
                 OR d.case_file LIKE %s
                 OR d.matter_code LIKE %s
                 OR (d.case_file IN ('MWK-001', 'Owner') AND %s LIKE 'MWK%%')
             )
               AND (
                    COALESCE(d.smart_filename,'') ILIKE %s
                 OR COALESCE(d.original_filename,'') ILIKE %s
                 OR COALESCE(d.smart_filename,'') ILIKE %s
                 OR COALESCE(d.original_filename,'') ILIKE %s
                 OR COALESCE(d.smart_filename,'') ILIKE %s
                 OR COALESCE(d.original_filename,'') ILIKE %s
                 OR COALESCE(d.extracted_text,'') ILIKE %s
                 OR COALESCE(d.extracted_text,'') ILIKE %s
               )
             ORDER BY rank ASC, downloadable DESC, d.id DESC
             LIMIT 12
        """, (
            like, like, tct_like, tct_like, t_dash, t_dash,
            client, fam, fam, client or "",
            like, like, tct_like, tct_like, t_dash, t_dash,
            tct_like, t_dash,
        ))
        docs = cur.fetchall()
        # Keep rank 0–1 always; rank 2 (body-only) only if nothing better
        ranked = list(docs or [])
        strong = [d for d in ranked if (d.get("rank") or 2) <= 1]
        docs = strong if strong else ranked[:5]
        cur.close(); conn.close()
    except Exception as e:
        return None, f"title_fetch_db:{type(e).__name__}:{e}"

    lines = [f"Title pack for TCT / T-{token}:"]
    if assets:
        for a in assets:
            sc = a.get("readiness_score")
            scs = f"{float(sc)*100:.0f}%" if sc is not None else "?"
            lines.append(
                f"• {a.get('title_ref') or a.get('asset_code')} "
                f"({a.get('client_code') or '—'}) status={a.get('title_status') or '—'} "
                f"readiness={scs} docs={a.get('documents') or '?'}"
            )
            note = (a.get("documents_note") or "")[:120]
            if note:
                lines.append(f"  note: {note}")
            nxt = (a.get("next_prep_action") or "")[:140]
            if nxt:
                lines.append(f"  next: {nxt}")
    else:
        lines.append(f"• No property_assets row matched T-{token} yet (title may still be in documents only).")

    dl_docs = [d for d in docs if d.get("downloadable")]
    other = [d for d in docs if not d.get("downloadable")]
    if dl_docs:
        lines.append("Downloadable from the corpus:")
        for d in dl_docs[:8]:
            name = (d.get("name") or "Document")[:90]
            lines.append(f"• {name}")
            lines.append(f"  https://leo.hayuma.org/files/c/{d['id']}")
    if other and not dl_docs:
        lines.append("Named in the record but no file bytes on disk/Drive yet:")
        for d in other[:5]:
            lines.append(f"• {(d.get('name') or 'Document')[:90]} (doc {d['id']})")
    if not docs:
        lines.append(
            "No document filename/text hit for that number in your scope. "
            "We may still need a CTC from the Registry of Deeds."
        )
    lines.append("I am not inventing a file — only linking what is already in the LandTek corpus.")
    return "\n".join(lines), None


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

    # Deterministic title FETCH before any LLM (Ollama has no tools — never "I'll fetch shortly")
    if _wants_title_fetch(text):
        pack, ferr = _fetch_title_docs(str(sender_id), text)
        if pack:
            _reply(chat_id, pack)
            return {"handler": "llm", "outcome": "replied_title_fetch", "reply_sent": True}
        # fall through to Ollama with error context if DB failed
        if ferr:
            print(f"[llm] title_fetch failed: {ferr}", file=sys.stderr)

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

    # ── A85 single chat brain: Ollama corpus first ($0). Anthropic is optional
    # secondary only when LANDTEK_ALLOW_ANTHROPIC_CHAT=1 — never dual-primary.
    allow_anthropic = os.environ.get("LANDTEK_ALLOW_ANTHROPIC_CHAT", "").strip().lower() in (
        "1", "true", "yes",
    )

    sov, sov_err = _sovereign_ollama_reply(str(sender_id), text)
    if sov:
        _reply(chat_id, sov)
        return {"handler": "llm", "outcome": "replied_ollama", "reply_sent": True}

    reply, err = (None, "anthropic_disabled")
    if allow_anthropic:
        reply, err = _call_anthropic(system_prompt, text, context)
        if reply is not None:
            _reply(chat_id, reply)
            return {"handler": "llm", "outcome": "replied_anthropic", "reply_sent": True}

    # Both paths failed — no billing finger-point (A85: cloud is not the product)
    _reply(chat_id,
           "I'm having trouble thinking right now. Give me a moment, "
           "or send a vault command if it's a vault action.")
    return {"handler": "llm",
            "outcome": f"api_failed:sov:{sov_err or '?'}|cloud:{(err or '')[:60]}"[:200],
            "reply_sent": True}
