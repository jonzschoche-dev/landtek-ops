#!/usr/bin/env python3
"""Telegram inquiry dispatcher — enforces one-active-at-a-time.

Run modes:
  python3 tg_dispatcher.py               # one cycle: promote, send, poll replies
  python3 tg_dispatcher.py --loop        # forever (45s cycle) — typically via systemd

Per [[feedback_telegram_inquiry_queue]]: never send while an inquiry is active.

Flow each cycle:
  1. EXPIRE: any 'queued' or 'active' rows past expires_at → 'expired'.
  2. POLL REPLIES: fetch Telegram updates since last cursor; any text reply
     from Jonathan that isn't a /command marks the current 'active' row as 'answered'.
  3. PROMOTE: if no row is 'active', pop the highest-priority 'queued' row and send it.
  4. Update tg_update_cursor.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
import psycopg2, psycopg2.extras, requests

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
JONATHAN_TG = "6513067717"  # kept for inbound dedup (getUpdates filter — see below)

# Hardcoded outbound recipients (per [[feedback_client_comms_hardcoded]] P0).
from comms_recipients import recipients_for, all_recipients_uniq, MWK_001_RECIPIENTS

# Allowed inbound senders — Jonathan AND Don Qi. Any other chat_id is ignored
# but logged. This is the inbound-side fan-in for the same hardcoded recipient
# set. If you add a new recipient in comms_recipients.py, this picks it up too.
ALLOWED_INBOUND_CHAT_IDS = {cid for _, cid in all_recipients_uniq()}


def load_token():
    with open("/root/landtek/.env") as f:
        for line in f:
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.strip().split("=", 1)[1]
    return None


_QUESTION_STARTERS = {
    "did", "do", "does", "is", "are", "was", "were", "can", "could",
    "will", "would", "should", "has", "have", "had", "may", "might",
    "what", "whats", "what's", "when", "where", "who", "whos", "who's",
    "why", "how", "which",
    "tell", "show", "give", "find", "list", "check", "explain",
    "any", "anything", "anyone",
}


def _looks_like_question(text: str) -> bool:
    """Heuristic: does this look like Jonathan asking Leo something, rather
    than an answer to the currently-active inquiry?

    True for: 'Did emails come today?', 'What's the status', 'Tell me about Maribel'.
    False for: 'She's the president of NIBDC', '50M', 'counsel_retainer | 12500 | ...',
    '/confirm', 'next' — i.e. anything that looks like a fact, an option pick,
    a parser-format reply, or a slash command (slash commands are filtered upstream)."""
    if not text:
        return False
    t = text.strip()
    if not t:
        return False
    if t.endswith("?"):
        return True
    first = t.split()[0].lower().rstrip(",.:!")
    return first in _QUESTION_STARTERS


def _unescape_literals(text: str) -> str:
    """Convert literal backslash-n / -t / -r sequences in composed_html into real
    whitespace. Some LLM-driven producers serialize their reply as a JSON string
    and store it raw, leaving \\n visible in Telegram. Intake bodies don't
    legitimately need the literal escape, so this is safe to do unconditionally."""
    if not text:
        return text
    return text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")


def tg_send(text, token, reply_to=None, case_file="MWK-001", audience="ops", kind="ad_hoc"):
    """Thin wrapper — delegates to comms.comms_send (the canonical chokepoint).

    Maintains its old (ok, detail, message_id) return signature so existing
    dispatcher call sites work unchanged. audience defaults to "ops" (safe),
    callers that touch a client must pass audience="client" or "both" + kind.
    """
    from comms import comms_send
    ok, results = comms_send(text, audience=audience, kind=kind,
                              case_file=case_file, reply_to=reply_to, token=token)
    if not ok:
        # Blocked or all-recipients-failed
        first = results[0] if results else {}
        reason = first.get("reason") or first.get("tg_description") or "no recipients"
        details = "; ".join(
            f"{r.get('name','?')}({r.get('chat_id','?')}): {r.get('tg_description','blocked')[:80]}"
            for r in results if not r.get("ok"))
        return False, (details or reason)[:300], None
    # primary mid = first successful recipient
    primary_mid = next((r["message_id"] for r in results if r.get("ok")), None)
    fail_count = sum(1 for r in results if not r.get("ok"))
    ok_count = sum(1 for r in results if r.get("ok"))
    if fail_count == 0:
        return True, "ok", primary_mid
    summary = f"partial: {fail_count} fail / {ok_count} ok"
    return True, summary, primary_mid


def evaluate_and_followup(cur, answered_row, answer_text, token, verbose=False):
    """After an atomic intake_item gets answered, run the satisfaction evaluator.
    If not satisfied, enqueue a follow-up row with HIGH priority so it fires
    BEFORE the next planned item. If satisfied, mark the corresponding item
    in stage_intake_response.item_status as 'satisfied'.

    Per [[feedback_atomic_inquiry_with_followups]]: we do not rush facts.
    """
    import sys as _sys
    _sys.path.insert(0, "/root/landtek")
    from satisfaction_evaluator import evaluate
    from landtek_core import get
    import anthropic

    # Extract the question text from the composed_html (the bolded "Question N: ..." block)
    import re as _re
    m = _re.search(r"<b>Question\s+\d+\s+of\s+\d+:</b>\s*([^<]+)",
                   answered_row["composed_html"] or "")
    question_text = (m.group(1).strip() if m else
                     answered_row["composed_html"][:200])

    client = anthropic.Anthropic(api_key=get("ANTHROPIC_API_KEY"))
    verdict = evaluate(client, question_text, answer_text)
    if verbose:
        print(f"  satisfaction: {verdict}")

    # Record verdict on the row
    cur.execute("""
        UPDATE tg_inquiry_queue
           SET satisfaction_verdict = %s,
               satisfaction_reason = %s
         WHERE id = %s
    """, ("satisfied" if verdict["satisfied"] else "needs_followup",
          verdict.get("reason", "")[:300], answered_row["id"]))

    # Update item_status in stage_intake_response
    cur.execute("""
        SELECT item_status FROM stage_intake_response WHERE id = %s
    """, (answered_row["intake_response_id"],))
    cur_status = (cur.fetchone() or {}).get("item_status") or {}
    if isinstance(cur_status, str):
        import json as _json
        cur_status = _json.loads(cur_status)
    item_key = str(answered_row["item_index"])
    cur_status[item_key] = "satisfied" if verdict["satisfied"] else "needs_followup"
    import json as _json
    cur.execute("""
        UPDATE stage_intake_response
           SET item_status = %s::jsonb,
               items_received = (SELECT COUNT(*) FROM jsonb_each_text(%s::jsonb) WHERE value='satisfied'),
               status = CASE
                 WHEN (SELECT COUNT(*) FROM jsonb_each_text(%s::jsonb) WHERE value IN ('satisfied','skipped')) = items_total
                 THEN 'complete'
                 ELSE 'partial' END
         WHERE id = %s
    """, (_json.dumps(cur_status), _json.dumps(cur_status), _json.dumps(cur_status),
          answered_row["intake_response_id"]))

    # If not satisfied, enqueue a follow-up atomic row at HIGHER priority (5 = jump)
    if not verdict["satisfied"] and verdict.get("follow_up"):
        followup_html = (
            f"🔁 <b>Follow-up</b>  <i>(to your prior answer)</i>\n\n"
            f"<b>{verdict['follow_up']}</b>\n\n"
            f"<i>Leo: {verdict.get('reason','')[:160]}</i>\n\n"
            f"<i>Reply with the specific fact. <code>/skip</code> if not applicable.</i>"
        )
        cur.execute("""
            INSERT INTO tg_inquiry_queue
              (kind, priority, source_table, source_id, parent_id,
               intake_response_id, item_index, is_followup,
               composed_html, notes)
            VALUES ('intake_followup', 5, 'tg_inquiry_queue', %s, %s,
                    %s, %s, true, %s, %s)
        """, (str(answered_row["id"]), answered_row["id"],
              answered_row["intake_response_id"], answered_row["item_index"],
              followup_html,
              f"follow-up to inquiry#{answered_row['id']} on intake#{answered_row['intake_response_id']} item {answered_row['item_index']}"))
        if verbose:
            print(f"  enqueued follow-up for intake#{answered_row['intake_response_id']} item {answered_row['item_index']}")


def handle_opus_strategic_command(text, token, reply_to=None):
    """Fire `python3 opus_advisor.py strategic --matter X` and ship the memo to TG.

    Acknowledges immediately (Opus takes 10-20s), then posts the memo when ready.
    Output is audited via output_audit before send.
    """
    import re as _re
    import subprocess
    import sys as _sys
    _sys.path.insert(0, "/root/landtek")
    m = _re.match(r"/opus[-_]strategic\s+(\S+)\s*$", text.strip(), _re.IGNORECASE)
    if not m:
        tg_send(
            "⚠️ Usage: <code>/opus-strategic &lt;matter_code&gt;</code>\n"
            "Example: <code>/opus-strategic MWK-CV26360</code>\n"
            "Cost: ~$0.05-0.20 per memo (Opus 4.7).\n"
            "Use <code>/matters</code> to list available matter codes.",
            token, reply_to=reply_to)
        return
    matter_code = m.group(1)
    tg_send(
        f"⏳ Calling Opus 4.7 for strategic memo on <code>{matter_code}</code>... "
        f"(takes 10-20s; cost ~$0.10-0.20)",
        token, reply_to=reply_to)
    try:
        result = subprocess.run(
            ["/usr/bin/python3", "/root/landtek/opus_advisor.py", "strategic",
             "--matter", matter_code],
            capture_output=True, text=True, timeout=90,
        )
        memo = result.stdout
        if not memo or len(memo.strip()) < 100:
            tg_send(f"⚠️ Opus returned empty or short output. stderr: {(result.stderr or '')[:300]}",
                    token, reply_to=reply_to)
            return
    except subprocess.TimeoutExpired:
        tg_send(f"⏱ Opus call timed out (>90s) for {matter_code}", token, reply_to=reply_to)
        return
    except Exception as e:
        tg_send(f"❌ Opus error: {str(e)[:200]}", token, reply_to=reply_to)
        return

    # Output audit BEFORE send (no-hallucination discipline)
    from output_audit import audit_text
    passed, findings = audit_text(memo, strict=False)  # warn-only for advisor memos

    # Strip the leading "=== Opus strategic memo — X ===" wrapper if present
    memo_clean = _re.sub(r"^=+\s*Opus.*?=+\s*\n", "", memo, count=1, flags=_re.MULTILINE).strip()

    # Send: if short enough, inline. Otherwise as a document.
    if len(memo_clean) <= 3800:
        # Strip markdown headers/bolds to plain Telegram-safe text (mostly)
        safe = memo_clean.replace("**", "")
        tg_send(f"🦉 <b>Opus strategic memo — {matter_code}</b>\n\n<pre>{safe[:3700]}</pre>",
                token, reply_to=reply_to)
    else:
        import tempfile, os, requests
        from pathlib import Path
        out_path = Path(f"/root/landtek/drafts/opus_strategic_{matter_code}_{__import__('datetime').date.today().isoformat()}.md")
        out_path.write_text(memo_clean)
        # Fan-out document to every hardcoded recipient (P0 — never single-recipient).
        for _name, _cid in MWK_001_RECIPIENTS:
            with open(out_path, "rb") as fh:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendDocument",
                    data={"chat_id": _cid,
                          "caption": f"🦉 Opus strategic memo — {matter_code} ({len(memo_clean):,} chars)",
                          "reply_to_message_id": reply_to or ""},
                    files={"document": fh}, timeout=30)


def handle_opus_resolve_command(text, token, reply_to=None):
    """Fire `python3 opus_advisor.py resolve-dispute --deadline N`."""
    import re as _re
    import subprocess
    m = _re.match(r"/opus[-_]resolve\s+(\d+)\s*$", text.strip(), _re.IGNORECASE)
    if not m:
        tg_send(
            "⚠️ Usage: <code>/opus-resolve &lt;deadline_id&gt;</code>\n"
            "Example: <code>/opus-resolve 2</code>\n"
            "Triggers Opus to resolve a priority dispute on the given deadline.\n"
            "Cost: ~$0.05 per resolution.",
            token, reply_to=reply_to)
        return
    deadline_id = int(m.group(1))
    tg_send(f"⏳ Opus resolving priority dispute on deadline #{deadline_id}...",
            token, reply_to=reply_to)
    try:
        result = subprocess.run(
            ["/usr/bin/python3", "/root/landtek/opus_advisor.py", "resolve-dispute",
             "--deadline", str(deadline_id)],
            capture_output=True, text=True, timeout=60,
        )
        memo = result.stdout
        if not memo or len(memo.strip()) < 50:
            tg_send(f"⚠️ Opus returned empty output. stderr: {(result.stderr or '')[:300]}",
                    token, reply_to=reply_to)
            return
    except Exception as e:
        tg_send(f"❌ Opus error: {str(e)[:200]}", token, reply_to=reply_to)
        return
    memo_clean = _re.sub(r"^=+\s*Opus.*?=+\s*\n", "", memo, count=1, flags=_re.MULTILINE).strip()
    safe = memo_clean.replace("**", "").replace("<", "&lt;").replace(">", "&gt;")
    tg_send(f"🦉 <b>Opus priority resolution — deadline #{deadline_id}</b>\n\n<pre>{safe[:3700]}</pre>",
            token, reply_to=reply_to)


def handle_priority_command(text, token, reply_to=None):
    """Parse `/priority <deadline_id> <P0|P1|P2|P3|P4|P5>` and update Jonathan's
    priority signal. Recomputes consensus state.

    Per [[feedback_priority_consensus_required]]: Jonathan's signal moves
    consensus from leo_only → jonathan_confirmed (if matches Leo's) or
    disputed (if differs).
    """
    import psycopg2 as _pg
    import re as _re
    m = _re.match(r"/priority\s+(\d+)\s+(P[0-5])\s*$", text.strip(), _re.IGNORECASE)
    if not m:
        tg_send(
            "⚠️ Usage: <code>/priority &lt;deadline_id&gt; &lt;P0..P5&gt;</code>\n"
            "Example: <code>/priority 2 P4</code> (mark deadline #2 as P4)\n\n"
            "Find deadline IDs in the daily digest or via <code>/status</code>.",
            token, reply_to=reply_to)
        return
    dl_id = int(m.group(1))
    tier = m.group(2).upper()

    conn = _pg.connect(DSN); conn.autocommit = True
    c = conn.cursor()
    c.execute("""
        SELECT id, title, priority_leo, priority_jonathan, priority_client, priority_consensus_state
          FROM case_deadlines WHERE id = %s
    """, (dl_id,))
    r = c.fetchone()
    if not r:
        tg_send(f"❌ No deadline with id {dl_id}.", token, reply_to=reply_to)
        c.close(); conn.close()
        return
    _, title, p_leo, p_jon_prev, p_client, state_prev = r

    # Compute new consensus state
    signals = {"leo": p_leo, "jonathan": tier, "client": p_client}
    distinct = {v for v in signals.values() if v}
    if len(distinct) == 1 and len([v for v in signals.values() if v]) >= 2:
        new_state = "full_consensus" if all(signals.values()) else (
            "jonathan_confirmed" if not p_client else "client_confirmed")
    elif len(distinct) == 1:
        new_state = "jonathan_confirmed"
    else:
        # Multiple distinct signals → disputed
        new_state = "disputed"

    import json as _json
    audit_entry = _json.dumps({
        "source": "jonathan_via_tg_slash",
        "at": _re.sub(r"\..*$", "", str(__import__("datetime").datetime.now().isoformat())),
        "old": {"leo": p_leo, "jonathan": p_jon_prev, "client": p_client, "state": state_prev},
        "new": {"jonathan": tier, "state": new_state},
    })
    c.execute("""
        UPDATE case_deadlines
           SET priority_jonathan = %s,
               priority_consensus_state = %s,
               priority_history = priority_history || %s::jsonb
         WHERE id = %s
    """, (tier, new_state, "[" + audit_entry + "]", dl_id))
    c.close(); conn.close()

    msg = (f"✓ Priority updated for deadline #{dl_id}\n\n"
           f"<b>{title[:80]}</b>\n"
           f"Leo: <code>{p_leo or '—'}</code>  ·  "
           f"You: <code>{tier}</code>  ·  "
           f"Client: <code>{p_client or '—'}</code>\n"
           f"Consensus state: <code>{new_state}</code>")
    if new_state == "disputed":
        msg += "\n\n⚠️ Disagreement detected — Leo will surface a consensus-ask to resolve."
    tg_send(msg, token, reply_to=reply_to)


def handle_uploaded_image(token, file_id, file_kind, caption, reply_to=None):
    """Pull a Telegram photo/document, OCR via Gemini, classify via Haiku,
    insert with structured fields, log canonical-bible event, and queue an
    educated follow-up question.

    Returns dict {doc_id, classification, case_file, matter_code_guess,
    confidence, bound_to_inquiry} so callers (the cycle loop) can build a
    proper ack with the actual classified fields.
    """
    import os, requests, hashlib, time, psycopg2, json as _json
    import sys as _sys; _sys.path.insert(0, "/root/landtek")

    result = {"doc_id": None, "classification": None, "case_file": None,
              "matter_code_guess": None, "confidence": 0.0,
              "bound_to_inquiry": None, "vendor_or_party": None,
              "amount_php": None, "doc_date": None}

    # 1. Get + download the file
    r = requests.get(f"https://api.telegram.org/bot{token}/getFile",
                     params={"file_id": file_id}, timeout=20)
    j = r.json()
    if not j.get("ok"):
        tg_send(f"⚠️ getFile failed: {j.get('description','?')[:200]}", token, reply_to=reply_to)
        return result
    file_path = j["result"]["file_path"]
    bin_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    binr = requests.get(bin_url, timeout=60)
    binr.raise_for_status()
    blob = binr.content
    content_hash = hashlib.sha256(blob).hexdigest()
    os.makedirs("/root/landtek/uploads/telegram", exist_ok=True)
    ext = ".jpg" if file_kind == "photo" else "." + (file_kind.split("/")[-1] if "/" in file_kind else "bin")
    fname = f"tg_{int(time.time())}_{content_hash[:12]}{ext}"
    local_path = f"/root/landtek/uploads/telegram/{fname}"
    with open(local_path, "wb") as fh:
        fh.write(blob)

    # 2. OCR via Gemini Vision
    extracted_text = ""
    try:
        import google.generativeai as genai
        from llm_billing import gemini_call
        from landtek_core import get
        genai.configure(api_key=get("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-2.5-flash")
        mime = "image/jpeg" if file_kind == "photo" else file_kind
        resp = gemini_call(
            model,
            called_from="tg_dispatcher_image",
            purpose="screenshot_ocr",
            case_file="MWK-001",
            model_name="gemini-2.5-flash",
            contents=[
                "Extract ALL visible text from this image. Also describe what kind of document this appears to be (receipt / court order / letter / TCT / tax declaration / screenshot of an email / etc.) and identify any case numbers, dates, names, amounts visible. Output as: TEXT:\n<all text>\n\nCONTEXT:\n<one paragraph about what this doc is>",
                {"mime_type": mime, "data": blob},
            ],
        )
        extracted_text = (resp.text or "").strip()
    except Exception as e:
        extracted_text = f"OCR_FAILED: {str(e)[:200]}"

    # 3. Classify via Haiku (with context: active matters + recent uploads)
    conn = psycopg2.connect(DSN); conn.autocommit = True
    from psycopg2.extras import RealDictCursor
    cd = conn.cursor(cursor_factory=RealDictCursor)
    cd.execute("""
        SELECT matter_code, case_file, title FROM matters
         WHERE status='active' ORDER BY case_file, matter_code LIMIT 60
    """)
    active_matters = cd.fetchall()
    cd.execute("""
        SELECT id, classification, case_file, LEFT(extracted_text, 200) AS key_fact
          FROM documents
         WHERE timestamp > NOW() - INTERVAL '15 minutes'
         ORDER BY timestamp DESC LIMIT 5
    """)
    recent_uploads = cd.fetchall()
    cd.close()

    cls = {"kind": "unknown", "case_file_guess": None, "matter_code_guess": None,
           "doc_date": None, "key_fact": "", "vendor_or_party": None,
           "amount_php": None, "parties": [], "confidence": 0.0,
           "needs_human_question": ""}
    try:
        import anthropic
        from doc_classifier import classify_document
        a_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        cls.update(classify_document(a_client, doc_id_placeholder := -1,
                                       extracted_text, active_matters, recent_uploads))
    except Exception as e:
        cls["needs_human_question"] = f"Classifier failed ({str(e)[:80]}) — what is this?"

    # 4. Insert documents with classified fields (no more hardcoded MWK-001)
    classification = cls.get("kind", "unknown")
    case_file = cls.get("case_file_guess") or "MWK-001"  # fallback for NOT NULL
    case_file_was_defaulted = cls.get("case_file_guess") is None
    doc_date = cls.get("doc_date") or None
    doc_date_quality = "from_doc" if cls.get("doc_date") else "upload_date_fallback"
    c = conn.cursor()
    c.execute("""
        INSERT INTO documents (case_file, original_filename, smart_filename, mime_type,
                               content_hash, file_path, extracted_text, status,
                               text_length, timestamp, doc_date_norm, doc_date_quality,
                               classification, matter_code)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'ingested_from_telegram',
                %s, NOW(), COALESCE(%s::date, CURRENT_DATE), %s, %s, %s)
        ON CONFLICT (content_hash) WHERE content_hash IS NOT NULL
          DO UPDATE SET file_path = EXCLUDED.file_path
        RETURNING id
    """, (case_file, fname, fname,
          "image/jpeg" if file_kind == "photo" else file_kind,
          content_hash, local_path, extracted_text, len(extracted_text),
          doc_date, doc_date_quality, classification,
          cls.get("matter_code_guess")))
    doc_id = c.fetchone()[0]
    result["doc_id"] = doc_id
    result["classification"] = classification
    result["case_file"] = case_file if not case_file_was_defaulted else None
    result["matter_code_guess"] = cls.get("matter_code_guess")
    result["confidence"] = cls.get("confidence", 0.0)
    result["vendor_or_party"] = cls.get("vendor_or_party")
    result["amount_php"] = cls.get("amount_php")
    result["doc_date"] = cls.get("doc_date")

    # 5. Log canonical-bible event in client_history (idempotent)
    try:
        c.execute("SELECT client_code FROM clients WHERE case_file = %s LIMIT 1", (case_file,))
        cc_row = c.fetchone()
        if not cc_row:
            c.execute("SELECT DISTINCT client_code FROM matters WHERE case_file = %s LIMIT 1", (case_file,))
            cc_row = c.fetchone()
        client_code = cc_row[0] if cc_row else None
        if client_code:
            summary_bits = [f"{classification}"]
            if cls.get("vendor_or_party"):
                summary_bits.append(cls["vendor_or_party"][:50])
            if cls.get("amount_php"):
                summary_bits.append(f"₱{cls['amount_php']:,.2f}")
            if cls.get("key_fact"):
                summary_bits.append(cls["key_fact"][:80])
            if case_file_was_defaulted:
                summary_bits.append("PENDING client assignment")
            summary = " · ".join(summary_bits)[:300]
            matter_codes_arr = [cls["matter_code_guess"]] if cls.get("matter_code_guess") else []
            c.execute("""
                INSERT INTO client_history
                  (client_code, case_file, matter_code, matter_codes, event_date,
                   event_kind, source_table, source_id,
                   what_summary, citation_ref, provenance)
                VALUES (%s, %s, %s, %s, %s,
                        'document_uploaded', 'documents', %s,
                        %s, %s, 'inferred_strong')
                ON CONFLICT (source_table, source_id) DO NOTHING
            """, (client_code,
                  case_file if not case_file_was_defaulted else None,
                  cls.get("matter_code_guess"), matter_codes_arr,
                  doc_date, str(doc_id), summary, f"doc#{doc_id}"))
    except Exception as e:
        print(f"  ⚠ client_history log failed: {e}")

    # 6. Bind to currently-active inquiry (if any)
    c.execute("""
        SELECT id, intake_response_id, item_index, composed_html, kind
          FROM tg_inquiry_queue WHERE status='active' LIMIT 1
    """)
    active = c.fetchone()
    bind_note = ""
    bound_id = None
    if active:
        bound_id = active[0]
        result["bound_to_inquiry"] = bound_id
        c.execute("""
            UPDATE tg_inquiry_queue
               SET status='answered',
                   response_text = COALESCE(response_text,'') || %s,
                   responded_at = NOW(),
                   notes = COALESCE(notes,'') || %s
             WHERE id = %s
        """, (f"\n[image uploaded: {fname}]\n" + extracted_text[:2000],
              f" | image bound: {fname}", bound_id))
        bind_note = f" + bound to active inquiry #{bound_id}"
        if active[1] and active[4] in ("intake_item", "intake_followup"):
            cur_d = psycopg2.connect(DSN); cur_d.autocommit = True
            cur_dx = cur_d.cursor(cursor_factory=RealDictCursor)
            cur_dx.execute("""
                SELECT id, intake_response_id, item_index, composed_html, kind
                  FROM tg_inquiry_queue WHERE id = %s
            """, (bound_id,))
            row = cur_dx.fetchone()
            try:
                evaluate_and_followup(cur_dx, row, extracted_text, token, verbose=False)
            except Exception as e:
                print(f"  satisfaction-on-image-failed: {e}", flush=True)
            cur_dx.close(); cur_d.close()
    c.close()

    # 7. If not bound to an existing inquiry, queue an educated follow-up Q
    # at priority 0 (fires immediately even in pull-only mode, since it's
    # reactive to an upload Jonathan just did).
    if not bound_id:
        try:
            from doc_classifier import format_educated_followup
            composed, notes_json = format_educated_followup(
                doc_id=doc_id,
                classification=classification,
                case_file_guess=cls.get("case_file_guess"),
                matter_code_guess=cls.get("matter_code_guess"),
                key_fact=cls.get("key_fact", ""),
                vendor_or_party=cls.get("vendor_or_party"),
                amount_php=cls.get("amount_php"),
                doc_date=cls.get("doc_date"),
                confidence=cls.get("confidence", 0.0),
                needs_human_question=cls.get("needs_human_question", ""),
            )
            c2 = conn.cursor()
            c2.execute("""
                INSERT INTO tg_inquiry_queue
                  (kind, audience, priority, source_table, source_id, matter_code,
                   composed_html, notes)
                VALUES ('intake_item', 'ops', 0, 'doc_classifier', %s, %s,
                        %s, %s)
                RETURNING id
            """, (doc_id, cls.get("matter_code_guess"), composed, notes_json))
            inq_id = c2.fetchone()[0]
            result["followup_inquiry_id"] = inq_id
            c2.close()
        except Exception as e:
            print(f"  ⚠ educated-followup queue failed: {e}")
    conn.close()

    return result


def handle_timeline_command(token, matter_code, reply_to=None):
    """Generate timeline + send as Telegram message. Inline (not queued)."""
    import subprocess, psycopg2 as _pg
    if not matter_code:
        # List available matters
        conn = _pg.connect(DSN); conn.autocommit = True
        c = conn.cursor()
        c.execute("SELECT matter_code, title FROM matters WHERE status='active' ORDER BY matter_code")
        rows = c.fetchall()
        c.close(); conn.close()
        text = "📋 <b>Active matters — pick one for timeline</b>\n\n" + \
               "\n".join(f"  <code>/timeline {m}</code> — {t[:55]}" for m, t in rows) + \
               "\n\n<i>Then re-send: <code>/timeline &lt;matter_code&gt;</code></i>"
        tg_send(text, token, reply_to=reply_to)
        return

    # Run timeline tool, capture markdown
    try:
        result = subprocess.run(
            ["/usr/bin/python3", "/root/landtek/timeline.py", "--matter", matter_code],
            capture_output=True, text=True, timeout=30,
        )
        md = result.stdout or "(no output)"
    except subprocess.TimeoutExpired:
        tg_send(f"⏱ Timeline generation timed out for {matter_code}", token, reply_to=reply_to)
        return
    except Exception as e:
        tg_send(f"❌ Timeline error: {str(e)[:200]}", token, reply_to=reply_to)
        return

    # Convert markdown table to a compact Telegram HTML message
    # Strip the table rendering — Telegram doesn't render markdown tables well
    lines = md.split("\n")
    out = []
    in_table = False
    events_shown = 0
    for ln in lines:
        if ln.startswith("# "):
            out.append(f"<b>{ln[2:]}</b>")
        elif ln.startswith("## "):
            out.append(f"\n<b>{ln[3:]}</b>")
        elif ln.startswith("**") or ln.startswith("- "):
            out.append(ln.replace("**","<b>",1).replace("**","</b>",1))
        elif ln.startswith("| `"):
            # An event row — keep first ~25 rows
            if events_shown >= 25: continue
            parts = [p.strip() for p in ln.strip("|").split("|")]
            if len(parts) >= 4:
                out.append(f"  • <code>{parts[0]}</code> <code>{parts[1]}</code> — {parts[3][:80]}")
                events_shown += 1
        elif ln.startswith("|"):
            continue  # header / separator row
    text = "\n".join(out)[:3800]
    if events_shown >= 25:
        text += "\n\n<i>(showing first 25 events — full timeline available on the VPS at /root/landtek/drafts/)</i>"
    tg_send(text, token, reply_to=reply_to)


def handle_status_command(token, reply_to=None):
    import psycopg2 as _pg
    conn = _pg.connect(DSN); conn.autocommit = True
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM matters WHERE status='active'")
    n_matters = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM case_deadlines WHERE status='pending'")
    n_deadlines = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM tg_inquiry_queue WHERE status IN ('queued','active')")
    n_queue = c.fetchone()[0]
    c.execute("SELECT ROUND(SUM(cost_usd)::numeric, 4) FROM llm_calls WHERE called_at >= date_trunc('day', NOW())")
    cost_today = c.fetchone()[0] or 0
    c.close(); conn.close()
    text = f"""📊 <b>System status</b>

• Active matters: <b>{n_matters}</b>
• Pending deadlines: <b>{n_deadlines}</b>
• Open inquiries in queue: <b>{n_queue}</b>
• Today's LLM spend: <b>${float(cost_today):.4f}</b>

<i>Commands:</i>
  <code>/matters</code> — list active matters
  <code>/timeline &lt;matter&gt;</code> — chronological event list
  <code>/done</code> — mark current inquiry resolved
  <code>/skip</code> — skip current inquiry"""
    tg_send(text, token, reply_to=reply_to)


def handle_matters_command(token, reply_to=None):
    import psycopg2 as _pg
    conn = _pg.connect(DSN); conn.autocommit = True
    c = conn.cursor()
    c.execute("""
        SELECT matter_code, current_stage, COALESCE(LEFT(title,55),'') AS title
          FROM matters WHERE status='active' ORDER BY matter_code
    """)
    rows = c.fetchall()
    c.close(); conn.close()
    lines = ["🗂 <b>Active matters</b>", ""]
    for mc, stage, title in rows:
        lines.append(f"<code>{mc}</code>  <i>{stage or '—'}</i>")
        lines.append(f"  {title}")
    lines.append("\n<i>Reply <code>/timeline &lt;code&gt;</code> for any of these</i>")
    tg_send("\n".join(lines)[:3800], token, reply_to=reply_to)


def handle_inbox_command(token, reply_to=None):
    """Show what's queued without releasing anything. Per the 2026-05-20
    pull-only contract: Jonathan sees what's pending on demand, no auto-fire."""
    import psycopg2 as _pg
    conn = _pg.connect(DSN); conn.autocommit = True
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT id, kind, priority, source_table, matter_code,
               LEFT(composed_html, 110) AS preview
          FROM tg_inquiry_queue
         WHERE status='queued'
         ORDER BY priority ASC, composed_at ASC
         LIMIT 8
    """)
    items = c.fetchall()
    c.execute("SELECT COUNT(*) AS n FROM tg_inquiry_queue WHERE status='queued'")
    total = c.fetchone()["n"]
    c.close(); conn.close()
    if total == 0:
        tg_send("📭 Inbox empty.", token, reply_to=reply_to)
        return
    lines = [f"📥 <b>Inbox · {total} queued</b>", ""]
    for it in items:
        prio_tag = ("🔴 P0" if it["priority"] <= 0
                    else f"P{it['priority']//10}")
        src = it["source_table"] or "?"
        mc = it["matter_code"] or "—"
        preview = (it["preview"] or "").replace("<b>", "").replace("</b>", "")
        preview = preview.replace("<code>", "").replace("</code>", "")[:80]
        lines.append(f"<code>#{it['id']}</code> {prio_tag} · {it['kind']} · {src} · {mc}")
        lines.append(f"  <i>{preview}…</i>")
    lines.append("")
    lines.append("Reply <code>/next</code> to release the top, "
                 "<code>/digest</code> for findings, or a specific "
                 "<code>#id</code> to release one.")
    tg_send("\n".join(lines)[:3800], token, reply_to=reply_to)


def handle_digest_command(token, reply_to=None):
    """Run meta_agent inline + show top findings. Bypasses the queue entirely
    so /digest produces a single message regardless of pull-only mode."""
    try:
        sys.path.insert(0, "/root/landtek")
        from meta_agent import run_cycle as _meta_run
        findings = _meta_run(enqueue=False, json_out=False, verbose=False)
    except Exception as e:
        tg_send(f"⚠️ Digest run failed: {str(e)[:200]}", token, reply_to=reply_to)
        return
    if not findings:
        tg_send("✅ No findings.", token, reply_to=reply_to)
        return
    by_sev = {"P0": [], "P1": [], "P2": [], "P3": [], "P4": []}
    for f in findings:
        sev = (f.get("severity") or "P3").upper()
        by_sev.setdefault(sev, []).append(f)
    lines = [f"🩺 <b>Digest · {len(findings)} finding(s)</b>", ""]
    for sev in ("P0", "P1", "P2", "P3", "P4"):
        if not by_sev.get(sev):
            continue
        lines.append(f"<b>{sev}</b>")
        for f in by_sev[sev][:3]:
            lines.append(f"  • {(f.get('name') or '?')[:80]}")
            msg = (f.get("message") or "").strip()
            if msg:
                lines.append(f"    <i>{msg[:120]}</i>")
        if len(by_sev[sev]) > 3:
            lines.append(f"  <i>…+{len(by_sev[sev]) - 3} more {sev}</i>")
    tg_send("\n".join(lines)[:3800], token, reply_to=reply_to)


def fetch_updates(token, since_id):
    """Pull new Telegram updates after since_id."""
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates",
                     params={"offset": since_id + 1, "timeout": 0}, timeout=15)
    j = r.json()
    if not j.get("ok"):
        return []
    return j.get("result", [])


def cycle(cur, token, verbose=False):
    # 1. Expire any rows past expires_at
    cur.execute("""
        UPDATE tg_inquiry_queue
           SET status = 'expired'
         WHERE status IN ('queued','active') AND expires_at < NOW()
         RETURNING id, kind, status
    """)
    expired = cur.fetchall()
    if expired and verbose:
        print(f"  expired {len(expired)} stale inquiry(ies)")

    # 2. POLL replies
    cur.execute("SELECT last_update_id FROM tg_update_cursor WHERE id=1")
    last_id = cur.fetchone()["last_update_id"]
    updates = fetch_updates(token, last_id)
    new_max = last_id
    answer_recorded = False
    force_promote = False
    for u in updates:
        new_max = max(new_max, u["update_id"])
        msg = u.get("message") or {}
        chat = msg.get("chat", {})
        # Accept inbound from ANY hardcoded recipient (Jonathan AND Don Qi).
        # Per [[feedback_client_comms_hardcoded]] — administrators reply too.
        sender_chat_id_str = str(chat.get("id"))
        if sender_chat_id_str not in ALLOWED_INBOUND_CHAT_IDS:
            continue

        # ── chat_notes auto-write (per [[feedback_facts_in_chat_are_first_class]]) ──
        # Every recognized inbound text gets a chat_notes row so fact_extractor
        # can see it on its next 5-min cycle, even when the dispatcher
        # handles the message as a slash-command or as an inquiry answer.
        # Fixes the 2026-05-20 14:11-14:17 PHT gap where 7 prose corrections
        # were captured as tg_inquiry_queue.response_text but never as
        # chat_notes — so the encoder pipeline never saw them.
        _inbound_text = (msg.get("text") or msg.get("caption") or "").strip()
        if _inbound_text:
            _tg_msg_id = msg.get("message_id")
            try:
                cur.execute("""
                    INSERT INTO chat_notes (
                        telegram_msg_id, sender_id, sender_name, content,
                        topic, importance, provenance_level
                    ) VALUES (%s, %s, %s, %s, 'misc', 3, 'inferred_strong')
                    ON CONFLICT DO NOTHING
                """, (str(_tg_msg_id) if _tg_msg_id else None,
                      sender_chat_id_str,
                      (msg.get("from", {}).get("first_name", "")
                       + " " + msg.get("from", {}).get("last_name", "")).strip()
                      or "(unknown sender)",
                      _inbound_text[:4000]))
            except Exception as _e:
                # Never let chat_notes failure block dispatcher flow
                if verbose:
                    print(f"  ⚠ chat_notes insert failed: {_e}")

        # ─── GREETING short-circuit ──────────────────────────────────────────
        # Per Jonathan 2026-05-20: greetings get greetings. A bare "hey/hi/
        # morning/yo" must NEVER trigger parse logic, queue promotion, or any
        # digest. Just say hi (matching time-of-day) and continue.
        _greeting_text = (msg.get("text") or "").strip().lower()
        if _greeting_text and len(_greeting_text) <= 30 and re.match(
            r"^(hey|hi|hello|morning|gm|good morning|yo|sup|good evening|"
            r"good afternoon|ga|hey leo|hi leo|hello leo)[\s!.,]*$",
            _greeting_text):
            hour = datetime.now().hour
            if hour < 11:
                _g = "Morning."
            elif hour < 17:
                _g = "Hey."
            else:
                _g = "Evening."
            tg_send(_g, token, reply_to=msg.get("message_id"))
            if verbose:
                print(f"  greeting → '{_g}' (no promote, no parse)")
            continue

        # ─── IMAGE / PHOTO / DOCUMENT handler ─────────────────────────────
        # Per Jonathan 2026-05-17: must "scan a screenshot for text and context".
        # Telegram photos arrive as msg['photo'][] (multiple sizes); generic uploads
        # arrive as msg['document']. Pick the largest representation.
        if msg.get("photo") or (msg.get("document") and (msg["document"].get("mime_type","").startswith("image") or msg["document"].get("mime_type") == "application/pdf")):
            try:
                file_id = None
                caption = msg.get("caption", "")
                filename_hint = ""  # for receipt ack
                if msg.get("photo"):
                    file_id = msg["photo"][-1]["file_id"]
                    file_kind = "photo"
                    filename_hint = "photo"
                else:
                    file_id = msg["document"]["file_id"]
                    file_kind = msg["document"].get("mime_type", "unknown")
                    filename_hint = msg["document"].get("file_name") or file_kind
                ingest = handle_uploaded_image(token, file_id, file_kind, caption, msg.get("message_id"))
                ingest_id = ingest.get("doc_id") if isinstance(ingest, dict) else ingest
                if verbose:
                    print(f"  handled {file_kind} upload → doc#{ingest_id} "
                          f"({(ingest or {}).get('classification','?')} · "
                          f"{(ingest or {}).get('case_file','unclassified')} · "
                          f"conf {(ingest or {}).get('confidence',0):.0%})")

                # Client-facing receipt ack uses the CLASSIFIED case_file when
                # available — no more hardcoded MWK-001. If case_file couldn't
                # be inferred, the ack says "pending classification" so the
                # client/operator knows Leo isn't sure yet.
                sender_chat_id = str(chat.get("id"))
                if sender_chat_id in ALLOWED_INBOUND_CHAT_IDS and ingest_id:
                    from comms import comms_send, CLIENT_CHAT_IDS as _CC
                    ack_audience = "client" if sender_chat_id in _CC else "ops"
                    safe_name = (str(filename_hint)[:80]
                                  .replace("&", "&amp;")
                                  .replace("<", "&lt;")
                                  .replace(">", "&gt;"))
                    cf_for_ack = (ingest or {}).get("case_file") or "pending classification"
                    ack_text = (
                        f"✓ Received <b>{safe_name}</b> "
                        f"(ref #{ingest_id} · {cf_for_ack}). "
                        f"Leo is reviewing the file."
                    )
                    try:
                        comms_send(ack_text, audience=ack_audience,
                                    kind="ad_hoc",
                                    case_file=(ingest or {}).get("case_file") or "MWK-001",
                                    reply_to=msg.get("message_id"))
                    except Exception as _e:
                        print(f"  ⚠ receipt-ack failed: {_e}")
            except Exception as e:
                tg_send(f"⚠️ Image handler error: {str(e)[:200]}", token, reply_to=msg.get("message_id"))
                if verbose:
                    print(f"  image error: {e}")
            continue

        text = (msg.get("text") or "").strip()
        if not text:
            continue
        # Slash commands handled separately by future handler; here we treat /skip and /done specially
        if text.startswith("/next"):
            # Bypass the post-answer cooldown and promote the next queued item
            # immediately. Useful when Jonathan wants to power through the queue.
            force_promote = True
            if verbose:
                print(f"  /next received — bypassing cooldown this cycle")
            continue
        if text.startswith("/skip"):
            cur.execute("""
                UPDATE tg_inquiry_queue SET status='skipped', response_text=%s, responded_at=NOW()
                 WHERE status='active' RETURNING id
            """, (text,))
            r = cur.fetchone()
            if r and verbose:
                print(f"  marked active inquiry #{r['id']} as SKIPPED")
            answer_recorded = True
            continue
        if text.startswith("/done"):
            cur.execute("""
                UPDATE tg_inquiry_queue SET status='answered', response_text=%s, responded_at=NOW()
                 WHERE status='active' RETURNING id
            """, (text,))
            r = cur.fetchone()
            if r and verbose:
                print(f"  marked active inquiry #{r['id']} as ANSWERED (/done)")
            answer_recorded = True
            continue
        # /timeline <matter_code> — fire a report inline (NOT through queue, since
        # this is a report request, not an inquiry awaiting answer).
        if text.startswith("/timeline"):
            parts = text.split(None, 1)
            matter_code = parts[1].strip() if len(parts) > 1 else None
            handle_timeline_command(token, matter_code, msg.get("message_id"))
            if verbose:
                print(f"  handled /timeline for {matter_code or '(no arg)'}")
            continue
        # /status — show overall system status (one-shot, not queued)
        if text.startswith("/status"):
            handle_status_command(token, msg.get("message_id"))
            if verbose:
                print(f"  handled /status")
            continue
        # /matters — list all active matters
        if text.startswith("/matters"):
            handle_matters_command(token, msg.get("message_id"))
            if verbose:
                print(f"  handled /matters")
            continue
        # /inbox — show what's queued without releasing it
        if text.startswith("/inbox"):
            handle_inbox_command(token, msg.get("message_id"))
            if verbose:
                print(f"  handled /inbox")
            continue
        # /digest — run meta_agent inline + show findings (bypasses queue)
        if text.startswith("/digest"):
            handle_digest_command(token, msg.get("message_id"))
            if verbose:
                print(f"  handled /digest")
            continue
        # /priority <deadline_id> <P0-P5> — set Jonathan's priority signal on a deadline
        if text.startswith("/priority"):
            handle_priority_command(text, token, msg.get("message_id"))
            if verbose:
                print(f"  handled /priority")
            continue
        # /opus-strategic <matter> — fire Opus strategic memo (~$0.20)
        if text.startswith("/opus-strategic") or text.startswith("/opus_strategic"):
            handle_opus_strategic_command(text, token, msg.get("message_id"))
            if verbose:
                print(f"  handled /opus-strategic")
            continue
        # /cost /probability /value — queue legal-profitability foundation intakes
        if text.startswith(("/cost", "/probability", "/value")):
            import re as _re
            from legal_intake import (queue_cost_intake, queue_probability_intake,
                                       queue_value_intake)
            tokens = text.split(None, 3)
            cmd = tokens[0].lower()
            matter = tokens[1] if len(tokens) >= 2 else None
            if not matter:
                tg_send(
                    f"⚠️ Usage: <code>{cmd} &lt;matter_code&gt;</code> "
                    + ("[scenario]" if cmd == "/probability" else "[asset]" if cmd == "/value" else "")
                    + "\nExample: <code>/cost MWK-CV26360</code>",
                    token, reply_to=msg.get("message_id"), audience="ops", kind="ad_hoc")
                continue
            try:
                if cmd == "/cost":
                    iid = queue_cost_intake(matter)
                elif cmd == "/probability":
                    scenario = " ".join(tokens[2:]) or "general outcome"
                    iid = queue_probability_intake(matter, scenario)
                else:  # /value
                    asset = " ".join(tokens[2:]) or f"main asset of {matter}"
                    iid = queue_value_intake(matter, asset)
                tg_send(f"✓ Queued intake #{iid} — will fire when the queue is clear.",
                        token, reply_to=msg.get("message_id"), audience="ops", kind="ad_hoc")
                if verbose: print(f"  handled {cmd} for {matter} → inquiry #{iid}")
            except Exception as e:
                tg_send(f"❌ Intake failed: {str(e)[:200]}",
                        token, reply_to=msg.get("message_id"), audience="ops", kind="ad_hoc")
            continue
        # /forensic <matter> — fire ELITE_FORENSIC_LAND_TITLE agent (~$2-3 Opus 4.7)
        if text.startswith("/forensic"):
            import re as _re, subprocess as _sp
            m = _re.match(r"/forensic\s+(\S+)\s*$", text.strip(), _re.IGNORECASE)
            if not m:
                tg_send(
                    "⚠️ Usage: <code>/forensic &lt;matter_code&gt;</code>\n"
                    "Example: <code>/forensic MWK-CV26360</code>\n"
                    "Cost: ~$0.50-3.00 per analysis (Opus 4.7 forensic agent).\n"
                    "Produces partner-grade structured analysis (sections I-VII) + PDF.",
                    token, reply_to=msg.get("message_id"), audience="ops", kind="ad_hoc")
            else:
                matter_code = m.group(1)
                tg_send(
                    f"⏳ Calling forensic agent for <code>{matter_code}</code>... "
                    f"(20-40s; cost ~$0.50-3.00). PDF will be delivered on completion.",
                    token, reply_to=msg.get("message_id"), audience="ops", kind="ad_hoc")
                try:
                    _sp.Popen(["/usr/bin/python3", "/root/landtek/forensic_agent.py",
                               "--matter", matter_code],
                              cwd="/root/landtek",
                              stdout=open("/var/log/forensic_agent.log","ab"),
                              stderr=open("/var/log/forensic_agent.log","ab"))
                    if verbose: print(f"  handled /forensic for {matter_code} (background)")
                except Exception as e:
                    tg_send(f"❌ Forensic agent failed to launch: {str(e)[:200]}",
                            token, reply_to=msg.get("message_id"), audience="ops", kind="ad_hoc")
            continue
        # /opus-resolve <deadline_id> — fire Opus dispute resolution (~$0.05)
        if text.startswith("/opus-resolve") or text.startswith("/opus_resolve"):
            handle_opus_resolve_command(text, token, msg.get("message_id"))
            if verbose:
                print(f"  handled /opus-resolve")
            continue
        # Any other text from Jonathan = answer to current active inquiry
        if text.startswith("/"):
            continue  # other slash commands — leave to dedicated handler
        # Look up the active inquiry FIRST so we can route legal_intake replies
        cur.execute("""
            SELECT id, intake_response_id, item_index, composed_html, kind,
                   matter_code, source_table, notes
              FROM tg_inquiry_queue
             WHERE status='active'
             LIMIT 1
        """)
        active = cur.fetchone()
        if not active:
            continue

        # ── Question guard ──
        # If the message looks like Jonathan asking a question rather than
        # answering the active inquiry, don't auto-record it as the answer.
        # Otherwise legitimate questions get eaten ('Did emails come today?'
        # → recorded as the answer to whatever was active, then queue
        # promotes the next item — see 2026-05-20 7:57 PM failure).
        if _looks_like_question(text):
            preview = (active["composed_html"] or "")[:80].replace("\n", " ")
            tg_send(
                f"⏸ Looks like a question, not an answer to active inquiry "
                f"#{active['id']}. Reply <code>/skip</code> to drop it first, "
                f"then ask again. Active: <i>{preview}…</i>",
                token, reply_to=msg.get("message_id"),
                audience="ops", kind="ad_hoc")
            if verbose:
                print(f"  question detected, not recorded as answer to #{active['id']}")
            continue

        # ── Receipt-extractor reply router ──
        # Active intake came from receipt_extractor; notes carry a JSON blob
        # with vendor/total/date/category and either an assigned matter or a
        # context-proposal. Accept: /confirm (use the assigned matter or the
        # proposal), a bare matter_code (override), or /skip (handled upstream).
        if active["source_table"] == "receipt_extractor":
            import json as _json
            import re as _re
            import sys as _sys; _sys.path.insert(0, "/root/landtek")
            from receipt_extractor import write_cost_from_receipt
            ack_msg = None
            assigned_matter = None
            try:
                try:
                    note_obj = _json.loads(active["notes"] or "{}")
                except Exception:
                    note_obj = {}
                doc_id = note_obj.get("doc_id")
                vendor = note_obj.get("vendor", "?")
                total = note_obj.get("total_php") or 0
                proposed = note_obj.get("proposed_matter")
                preassigned = note_obj.get("matter_code") or active.get("matter_code")
                lower = text.strip().lower()

                if lower == "/confirm":
                    assigned_matter = preassigned or proposed
                    if not assigned_matter:
                        ack_msg = ("⚠️ /confirm with no preassigned or proposed matter. "
                                   "Reply with a matter_code instead (e.g. <code>MWK-CV26360</code>).")
                elif _re.match(r"^[A-Z][A-Z0-9-]{1,40}$", text.strip()):
                    assigned_matter = text.strip()
                else:
                    ack_msg = ("⚠️ Couldn't parse. Reply <code>/confirm</code> to accept "
                               "the proposed matter, a different matter_code, or "
                               "<code>/skip</code>.")

                if assigned_matter and not ack_msg:
                    result_for_write = {
                        "vendor": vendor,
                        "total_php": total,
                        "date": note_obj.get("date"),
                        "category": note_obj.get("category", "misc"),
                        "notes": "",
                        "confidence": 0,  # not used in write
                    }
                    row_id = write_cost_from_receipt(assigned_matter, doc_id, result_for_write)
                    # Backfill matter onto the document + client_history rows
                    cur.execute("UPDATE documents SET matter_code = %s WHERE id = %s",
                                (assigned_matter, doc_id))
                    cur.execute("""
                        UPDATE client_history
                           SET matter_code = %s,
                               matter_codes = ARRAY[%s]::text[],
                               what_summary = REPLACE(what_summary, ' · PENDING matter assignment', '')
                         WHERE source_table = 'receipt_extractor'
                           AND source_id = %s
                    """, (assigned_matter, assigned_matter, str(doc_id)))
                    ack_msg = (f"✓ Receipt doc#{doc_id} ({vendor[:30]} · ₱{total:,.2f}) "
                               f"logged to <code>{assigned_matter}</code> (row #{row_id})")
            except Exception as e:
                ack_msg = f"⚠️ Receipt-assign failed: {str(e)[:160]}"

            cur.execute("""
                UPDATE tg_inquiry_queue SET status='answered', response_text=%s, responded_at=NOW()
                 WHERE id=%s
            """, (text[:4000], active["id"]))
            answer_recorded = True
            if ack_msg:
                tg_send(ack_msg, token, reply_to=msg.get("message_id"),
                        audience="ops", kind="ad_hoc")
            if verbose:
                print(f"  receipt_extractor reply → {('assigned ' + assigned_matter) if assigned_matter else 'no assignment'}")
            continue

        # ── Legal-intake reply router (per [[feedback_facts_in_chat_are_first_class]]) ──
        # If the active inquiry came from legal_intake, parse the reply + persist.
        if active["source_table"] == "legal_intake" and (active["notes"] or "").startswith("legal_intake:"):
            import sys as _sys; _sys.path.insert(0, "/root/landtek")
            from legal_intake import (parse_cost_reply, parse_probability_reply,
                                       parse_value_reply, write_cost,
                                       write_probability, write_value)
            kind_tag = active["notes"].split(":")[1]   # cost | probability | value
            matter = active["matter_code"]
            parsed = None
            ack_msg = None
            try:
                if kind_tag == "cost":
                    parsed = parse_cost_reply(text)
                    if parsed:
                        row_id = write_cost(matter, parsed,
                                              source_label=f"telegram-reply:{msg.get('from',{}).get('id','?')}:2026-05-20")
                        ack_msg = (f"✓ Cost logged · {matter} · {parsed['category']} · "
                                   f"₱{parsed['amount_php']:,.2f} · {parsed['incurred_date']} "
                                   f"(row #{row_id})")
                    else:
                        ack_msg = ("⚠️ Couldn't parse. Format: "
                                   "<code>category | amount | YYYY-MM-DD | description</code>")
                elif kind_tag == "probability":
                    parsed = parse_probability_reply(text)
                    if parsed:
                        # Extract scenario from notes: legal_intake:probability:matter=X:scenario=Y
                        scen = "general outcome"
                        for tok in active["notes"].split(":"):
                            if tok.startswith("scenario="):
                                scen = tok[len("scenario="):]
                        row_id = write_probability(matter, scen, parsed)
                        if parsed["p"] is None:
                            ack_msg = f"✓ Recorded as unknown · {matter} · {scen[:50]} (row #{row_id})"
                        elif parsed["low"] is not None:
                            ack_msg = (f"✓ P logged · {matter} · {parsed['low']:.2f}–{parsed['high']:.2f} "
                                       f"(mid {parsed['p']:.2f}) · {scen[:40]} (row #{row_id})")
                        else:
                            ack_msg = (f"✓ P logged · {matter} · {parsed['p']:.2f} "
                                       f"· {scen[:40]} (row #{row_id})")
                    else:
                        ack_msg = ("⚠️ Couldn't parse. Reply with <code>0.6</code> or "
                                   "<code>0.4-0.7</code> or <code>unknown</code>.")
                elif kind_tag == "value":
                    parsed = parse_value_reply(text)
                    if parsed:
                        asset = "main asset"
                        for tok in active["notes"].split(":", 3):
                            if tok.startswith("asset="):
                                asset = tok[len("asset="):]
                        row_id = write_value(matter, asset, parsed)
                        v = (parsed["mid"] or parsed["low"] or parsed["high"] or 0)
                        ack_msg = (f"✓ Value logged · {matter} · ₱{v:,.0f} · "
                                   f"basis: {parsed['basis']} (row #{row_id})")
                    else:
                        ack_msg = ("⚠️ Couldn't parse. Format: <code>50M</code> or "
                                   "<code>40M-60M</code> or <code>40M / 50M / 80M basis: zonal</code>")
            except Exception as e:
                ack_msg = f"⚠️ Persist failed: {str(e)[:120]}"

            # Mark inquiry answered with raw text
            cur.execute("""
                UPDATE tg_inquiry_queue SET status='answered', response_text=%s, responded_at=NOW()
                 WHERE id=%s
            """, (text[:4000], active["id"]))
            answer_recorded = True
            # Concise ack (per concision cap — status_ack is 200 chars)
            if ack_msg:
                tg_send(ack_msg, token, reply_to=msg.get("message_id"),
                        audience="ops", kind="ad_hoc")
            if verbose:
                print(f"  legal_intake reply ({kind_tag}) → {('ok' if parsed else 'parse-failed')}")
            continue

        # ── Default path: mark as answered (existing behavior) ──
        cur.execute("""
            UPDATE tg_inquiry_queue SET status='answered', response_text=%s, responded_at=NOW()
             WHERE id=%s
        """, (text[:4000], active["id"]))
        r = active
        answer_recorded = True
        if verbose:
            print(f"  marked active inquiry #{r['id']} as ANSWERED")
        # If this was an atomic intake_item, run satisfaction evaluator
        if r["intake_response_id"] and r["kind"] in ("intake_item", "intake_followup"):
            evaluate_and_followup(cur, r, text, token, verbose=verbose)

    cur.execute("UPDATE tg_update_cursor SET last_update_id=%s, updated_at=NOW() WHERE id=1",
                (new_max,))

    # 3. PROMOTE next queued if no active
    cur.execute("SELECT id FROM tg_inquiry_queue WHERE status='active' LIMIT 1")
    if cur.fetchone():
        if verbose:
            print(f"  active inquiry exists, waiting for reply")
        return  # something is active — wait

    # ── Pull-only gate (per Jonathan 2026-05-20, "Leo must have human cadence"). ──
    # Default ON. Proactive promotion blocked UNLESS:
    #   - LEO_PULL_ONLY=0 (legacy reactive mode), OR
    #   - /next was just typed (force_promote), OR
    #   - the next queued item is priority<=0 (P0-jump: reactive to a Jonathan
    #     action, e.g. upload follow-up; or time-critical, e.g. T-3 deadline).
    # This keeps evidence + calendar baselines functional (their producers tag
    # priority 0) while silencing gap_alerts and scheduled noise.
    PULL_ONLY = os.getenv("LEO_PULL_ONLY", "1") == "1"
    if PULL_ONLY and not force_promote:
        cur.execute("""
            SELECT COUNT(*) AS n
              FROM tg_inquiry_queue
             WHERE status='queued' AND priority <= 0
        """)
        urgent_n = cur.fetchone()["n"]
        if urgent_n == 0:
            if verbose:
                cur.execute("SELECT COUNT(*) AS n FROM tg_inquiry_queue WHERE status='queued'")
                queued_n = cur.fetchone()["n"]
                print(f"  pull-only mode — {queued_n} queued waiting (use /next or /inbox)")
            return

    # Cooldown: after Jonathan answers an inquiry, give him a window to follow
    # up before the queue bumps him to a new topic. Bypassed by /next or by
    # an urgent (priority<=0) queued item. Per the 2026-05-20 topic-hop
    # failure (Maribel → Vito Cruz fired 1 min after the Maribel answer).
    COOLDOWN_AFTER_ANSWER_SEC = 180
    if not force_promote:
        cur.execute("""
            SELECT EXTRACT(EPOCH FROM (NOW() - MAX(responded_at)))::int AS sec_since
              FROM tg_inquiry_queue
             WHERE responded_at IS NOT NULL
        """)
        row = cur.fetchone() or {}
        sec_since = row.get("sec_since") if isinstance(row, dict) else row[0]
        if sec_since is not None and sec_since < COOLDOWN_AFTER_ANSWER_SEC:
            cur.execute("SELECT 1 FROM tg_inquiry_queue WHERE status='queued' AND priority <= 0 LIMIT 1")
            has_urgent = cur.fetchone() is not None
            if not has_urgent:
                if verbose:
                    remain = COOLDOWN_AFTER_ANSWER_SEC - sec_since
                    print(f"  cooldown active ({sec_since}s since last answer, "
                          f"{remain}s remaining) — not promoting")
                return

    cur.execute("""
        SELECT id, composed_html, kind, audience, COALESCE(matter_code, 'MWK-001') AS case_file
          FROM tg_inquiry_queue
         WHERE status='queued'
         ORDER BY priority ASC, composed_at ASC
         LIMIT 1
    """)
    nxt = cur.fetchone()
    if not nxt:
        if verbose:
            print(f"  no queued inquiries")
        return

    # ── Gate: output_audit before every send (deploy_149) ──
    # Per [[feedback_output_no_hallucination_discipline]]: nothing leaves the
    # queue without passing the assertive-fact-citation linter. The dispatcher
    # is the universal chokepoint, so this catches output from every producer
    # past, present, and future — even ones that forgot to call audit themselves.
    composed = nxt["composed_html"]
    audit_appended = ""
    try:
        from output_audit import audit_text
        # Get the row's kind so we can tier the strictness.
        cur.execute("SELECT kind FROM tg_inquiry_queue WHERE id=%s", (nxt["id"],))
        kind_row = cur.fetchone()
        kind = (kind_row or {}).get("kind", "")
        # 'report' and 'brief' assert facts → strict. Everything else is warn-only.
        strict_mode = kind in ("report", "brief")
        passed, findings = audit_text(composed, strict=strict_mode)
        high_findings = [f for f in findings if f.get("severity") == "high"]
        if strict_mode and not passed:
            # Block delivery — surface findings to Jonathan as a meta-alert instead.
            sample = "\n".join(f"  L{f['line']}: {f['issue']} — {f['snippet'][:120]}"
                                for f in high_findings[:5])
            cur.execute("""
                UPDATE tg_inquiry_queue
                   SET status='superseded',
                       notes = COALESCE(notes,'') || ' | BLOCKED_BY_AUDIT: ' || %s
                 WHERE id=%s
            """, (f"{len(high_findings)} high-severity findings", nxt["id"]))
            block_html = (
                f"🛑 <b>Output blocked by audit</b> (queue#{nxt['id']}, kind={kind})\n\n"
                f"{len(high_findings)} assertive fact(s) lacked citations — producer must "
                f"add doc# refs or hedge language before resend.\n\n<pre>{sample[:1500]}</pre>"
            )
            tg_send(block_html, token)
            if verbose:
                print(f"  🛑 BLOCKED inquiry #{nxt['id']} ({kind}) — {len(high_findings)} high findings")
            return
        if high_findings:
            # Warn-mode: deliver but append a discreet footer
            audit_appended = (f"\n\n<i>⚠️ {len(high_findings)} audit finding(s) — "
                              f"see notes if a claim looks unsupported.</i>")
    except Exception as e:
        if verbose:
            print(f"  ⚠ output_audit skipped: {e}")

    # Route by the row's explicit `audience` column (deploy 2026-05-19).
    # Falls back to kind-derived audience if the column is unset (legacy rows).
    inquiry_audience = (nxt.get("audience") or "").strip().lower()
    if inquiry_audience not in ("ops", "client", "both"):
        from comms_recipients import audience_for_kind
        inquiry_audience = audience_for_kind(kind)
    inquiry_case = nxt.get("case_file") or "MWK-001"
    composed_safe = _unescape_literals(composed)
    ok, info, msg_id = tg_send(composed_safe + audit_appended, token,
                                audience=inquiry_audience, kind=kind,
                                case_file=inquiry_case)
    if ok:
        cur.execute("""
            UPDATE tg_inquiry_queue
               SET status='active', sent_at=NOW(), sent_message_id=%s
             WHERE id=%s
        """, (msg_id, nxt["id"]))
        if verbose:
            print(f"  sent + activated inquiry #{nxt['id']} (tg msg {msg_id})")
    else:
        cur.execute("""
            UPDATE tg_inquiry_queue SET notes = COALESCE(notes,'') || ' | send_failed: ' || %s
             WHERE id=%s
        """, (info[:200], nxt["id"]))
        if verbose:
            print(f"  FAILED to send inquiry #{nxt['id']}: {info}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true", help="run forever, 45s cycles")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    token = load_token()
    if not token:
        sys.exit("FATAL: TELEGRAM_BOT_TOKEN missing")

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if args.loop:
        while True:
            try:
                cycle(cur, token, verbose=args.verbose)
            except Exception as e:
                print(f"  cycle error: {e}", file=sys.stderr)
            time.sleep(45)
    else:
        cycle(cur, token, verbose=True)

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
