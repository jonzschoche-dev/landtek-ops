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
import os
import sys
import time
from datetime import datetime, timezone
import psycopg2, psycopg2.extras, requests

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
JONATHAN_TG = "6513067717"


def load_token():
    with open("/root/landtek/.env") as f:
        for line in f:
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.strip().split("=", 1)[1]
    return None


def tg_send(text, token, reply_to=None):
    body = {"chat_id": JONATHAN_TG, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": True}
    if reply_to:
        body["reply_to_message_id"] = reply_to
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=body, timeout=15)
    try:
        j = r.json()
    except Exception:
        return False, r.text[:200], None
    if not j.get("ok"):
        return False, j.get("description", "")[:200], None
    return True, "ok", j["result"]["message_id"]


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


def handle_uploaded_image(token, file_id, file_kind, caption, reply_to=None):
    """Pull a Telegram photo/document, OCR via Gemini, ingest into documents +
    bind to the currently-active inquiry if any.

    Per Jonathan 2026-05-17: must scan screenshots and pull text + context.
    """
    import os, requests, hashlib, time, psycopg2
    from datetime import datetime

    # 1. Get the file_path from Telegram
    r = requests.get(f"https://api.telegram.org/bot{token}/getFile",
                     params={"file_id": file_id}, timeout=20)
    j = r.json()
    if not j.get("ok"):
        tg_send(f"⚠️ getFile failed: {j.get('description','?')[:200]}", token, reply_to=reply_to)
        return None
    file_path = j["result"]["file_path"]
    # 2. Download
    bin_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    binr = requests.get(bin_url, timeout=60)
    binr.raise_for_status()
    blob = binr.content
    content_hash = hashlib.sha256(blob).hexdigest()
    # 3. Save locally
    os.makedirs("/root/landtek/uploads/telegram", exist_ok=True)
    ext = ".jpg" if file_kind == "photo" else "." + (file_kind.split("/")[-1] if "/" in file_kind else "bin")
    fname = f"tg_{int(time.time())}_{content_hash[:12]}{ext}"
    local_path = f"/root/landtek/uploads/telegram/{fname}"
    with open(local_path, "wb") as fh:
        fh.write(blob)
    # 4. OCR via Gemini Vision (cost-logged via wrapper)
    extracted_text = ""
    try:
        import sys as _sys; _sys.path.insert(0, "/root/landtek")
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

    # 5. Try to bind to the currently-active inquiry (if any) — append response
    conn = psycopg2.connect(DSN); conn.autocommit = True
    c = conn.cursor()
    c.execute("""
        SELECT id, intake_response_id, item_index, composed_html, kind
          FROM tg_inquiry_queue WHERE status='active' LIMIT 1
    """)
    active = c.fetchone()
    bind_note = ""
    if active:
        active_id = active[0]
        c.execute("""
            UPDATE tg_inquiry_queue
               SET status='answered',
                   response_text = COALESCE(response_text,'') || %s,
                   responded_at = NOW(),
                   notes = COALESCE(notes,'') || %s
             WHERE id = %s
        """, (f"\n[image uploaded: {fname}]\n" + extracted_text[:2000],
              f" | image bound: {fname}", active_id))
        bind_note = f" + bound to active inquiry #{active_id}"
        # If it's an atomic intake_item, evaluate the OCR text as the answer
        if active[1] and active[4] in ("intake_item", "intake_followup"):
            cur_d = psycopg2.connect(DSN); cur_d.autocommit = True
            from psycopg2.extras import RealDictCursor
            cur_dx = cur_d.cursor(cursor_factory=RealDictCursor)
            cur_dx.execute("""
                SELECT id, intake_response_id, item_index, composed_html, kind
                  FROM tg_inquiry_queue WHERE id = %s
            """, (active_id,))
            row = cur_dx.fetchone()
            try:
                evaluate_and_followup(cur_dx, row, extracted_text, token, verbose=False)
            except Exception as e:
                print(f"  satisfaction-on-image-failed: {e}", flush=True)
            cur_dx.close(); cur_d.close()

    # 6. Insert into documents
    c.execute("""
        INSERT INTO documents (case_file, original_filename, smart_filename, mime_type,
                               content_hash, file_path, extracted_text, status,
                               text_length, timestamp, doc_date_norm, doc_date_quality)
        VALUES ('MWK-001', %s, %s, %s, %s, %s, %s, 'ingested_from_telegram',
                %s, NOW(), CURRENT_DATE, 'parsed_by_telegram_upload')
        ON CONFLICT (content_hash) DO UPDATE SET file_path = EXCLUDED.file_path
        RETURNING id
    """, (fname, fname, "image/jpeg" if file_kind == "photo" else file_kind,
          content_hash, local_path, extracted_text, len(extracted_text)))
    doc_id = c.fetchone()[0]
    c.close(); conn.close()

    # 7. Reply with confirmation + text preview
    text_preview = extracted_text[:600] if extracted_text else "(no text extracted)"
    tg_send(
        f"📷 <b>Image ingested as doc#{doc_id}</b>{bind_note}\n\n"
        f"<b>OCR preview:</b>\n<code>{text_preview.replace('<','&lt;').replace('>','&gt;')}</code>",
        token, reply_to=reply_to)
    return doc_id


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
    for u in updates:
        new_max = max(new_max, u["update_id"])
        msg = u.get("message") or {}
        chat = msg.get("chat", {})
        if str(chat.get("id")) != str(JONATHAN_TG):
            continue

        # ─── IMAGE / PHOTO / DOCUMENT handler ─────────────────────────────
        # Per Jonathan 2026-05-17: must "scan a screenshot for text and context".
        # Telegram photos arrive as msg['photo'][] (multiple sizes); generic uploads
        # arrive as msg['document']. Pick the largest representation.
        if msg.get("photo") or (msg.get("document") and (msg["document"].get("mime_type","").startswith("image") or msg["document"].get("mime_type") == "application/pdf")):
            try:
                file_id = None
                caption = msg.get("caption", "")
                if msg.get("photo"):
                    # Take the largest photo (last entry typically)
                    file_id = msg["photo"][-1]["file_id"]
                    file_kind = "photo"
                else:
                    file_id = msg["document"]["file_id"]
                    file_kind = msg["document"].get("mime_type","unknown")
                ingest_id = handle_uploaded_image(token, file_id, file_kind, caption, msg.get("message_id"))
                if verbose:
                    print(f"  handled {file_kind} upload → uploaded_files#{ingest_id}")
            except Exception as e:
                tg_send(f"⚠️ Image handler error: {str(e)[:200]}", token, reply_to=msg.get("message_id"))
                if verbose:
                    print(f"  image error: {e}")
            continue

        text = (msg.get("text") or "").strip()
        if not text:
            continue
        # Slash commands handled separately by future handler; here we treat /skip and /done specially
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
        # Any other text from Jonathan = answer to current active inquiry
        if text.startswith("/"):
            continue  # other slash commands — leave to dedicated handler
        cur.execute("""
            UPDATE tg_inquiry_queue SET status='answered', response_text=%s, responded_at=NOW()
             WHERE status='active'
             RETURNING id, intake_response_id, item_index, composed_html, kind
        """, (text[:4000],))
        r = cur.fetchone()
        if r:
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
    cur.execute("""
        SELECT id, composed_html FROM tg_inquiry_queue
         WHERE status='queued'
         ORDER BY priority ASC, composed_at ASC
         LIMIT 1
    """)
    nxt = cur.fetchone()
    if not nxt:
        if verbose:
            print(f"  no queued inquiries")
        return
    ok, info, msg_id = tg_send(nxt["composed_html"], token)
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
