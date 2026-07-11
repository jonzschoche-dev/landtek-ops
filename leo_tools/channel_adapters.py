"""Multi-channel adapters (deploy_117-A).

Inbound webhook endpoints (normalize → route through onboarding/AI Agent):
  POST /api/channel/whatsapp        — Meta/360dialog WhatsApp Business webhook
  POST /api/channel/web             — web chat widget message
  POST /api/channel/email           — email-reply webhook
  POST /api/channel/sms             — Twilio SMS webhook

Public REST API (licensable product surface):
  POST /api/v1/leo/chat             — send a message, get Leo's response
  POST /api/v1/leo/verify           — run truth_negotiator on a claim
  GET  /api/v1/leo/status           — system status
  GET  /api/v1/leo/version          — capability + version snapshot

Outbound senders:
  channel_send(channel, recipient_id, text) → unified send across all channels

Each inbound adapter:
  1. Normalize payload to {channel, channel_user_id, display_name, username, message}
  2. Look up channel_users; if state != approved → POST to /api/onboard
  3. If state == approved → push into n8n via Trigger webhook (acts like Telegram)
  4. Log to channel_messages for audit
"""
import os
import sys
import json
import secrets
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor

PG_DSN = os.getenv("LEO_TOOLS_PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN_TG_ID = "6513067717"

bp = Blueprint("channel_adapters", __name__)


def _db():
    return psycopg2.connect(PG_DSN)


def _env(key, default=None):
    try:
        with open("/root/landtek/.env") as f:
            for line in f:
                if line.startswith(f"{key}="):
                    return line.strip().split("=", 1)[1]
    except: pass
    return os.getenv(key, default)


def _plain_text(text):
    """Flatten HTML tags/entities to plain text for channels that do not render
    markup (Messenger, WhatsApp, Viber). Telegram keeps its own HTML via tg_send.
    Leo's onboarding copy is authored with Telegram <b> tags; this strips them so
    a Messenger user sees 'Leo', not '<b>Leo</b>'."""
    if not text:
        return text
    import re, html
    t = re.sub(r'(?i)<br\s*/?>', '\n', text)
    t = re.sub(r'(?i)</p\s*>', '\n\n', t)
    t = re.sub(r'<[^>]+>', '', t)
    return html.unescape(t).strip()


def _headless(channel):
    """True if this channel has been cut over to leo_service (headless); then the adapter must NOT
    send its own reply to an approved user — leo_service owns it (prevents double-reply). Fail-safe: on
    any error, returns False (adapter keeps replying — never a silent gap)."""
    try:
        conn = _db(); conn.autocommit = True; cur = conn.cursor()
        cur.execute("SELECT mode FROM leo_channel_mode WHERE channel=%s", (channel,))
        r = cur.fetchone(); cur.close(); conn.close()
        return bool(r and r[0] == "headless")
    except Exception:
        return False


def _log_inbound(channel, channel_user_id, text, raw_payload=None):
    """Log an inbound message; returns the channel_messages.id (for artifact linking)."""
    conn = _db(); conn.autocommit = True; cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO channel_messages
              (channel_id, channel_user_id, direction, text_content, sent_at, status, metadata)
            VALUES ((SELECT id FROM channels WHERE name=%s), %s, 'inbound', %s, now(), 'received',
                    COALESCE(%s::jsonb, '{}'::jsonb))
            RETURNING id
        """, (channel, str(channel_user_id), text,
              json.dumps(raw_payload) if raw_payload else None))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        cur.close(); conn.close()


def _ingest_channel_media(channel, channel_user_id, channel_message_id, attachments):
    """Fetch each attachment's bytes and hand to the universal sink. Every attachment yields a
    comms_artifacts ledger row (landed/deduped/held/quarantined) — lossless, degrade-don't-crash.
    `attachments`: list of {url, mime, filename, ref}."""
    if not attachments:
        return []
    import requests as _rq
    sys.path.insert(0, "/root/landtek/scripts")
    try:
        from comms_artifact_sink import land_artifact
    except Exception as e:
        return [{"status": "quarantined", "reason": f"sink_import:{type(e).__name__}"}]
    out = []
    for a in attachments:
        data = b""
        try:
            if a.get("url"):
                data = _rq.get(a["url"], timeout=45).content
        except Exception:
            data = b""
        out.append(land_artifact(channel, channel_user_id, channel_message_id,
                                 a.get("filename") or f"{channel}_media", data, a.get("mime"),
                                 media_ref=a.get("url") or a.get("ref")))
    return out


def _messenger_attachments(msg):
    """Meta Messenger message.attachments[] → normalized artifact refs (image/audio/video/file)."""
    mime_of = {"image": "image/jpeg", "audio": "audio/mpeg", "video": "video/mp4",
               "file": "application/octet-stream"}
    out = []
    for a in (msg.get("attachments") or []):
        t = a.get("type"); url = (a.get("payload") or {}).get("url")
        if t in mime_of and url:
            fn = (url.split("?")[0].rsplit("/", 1)[-1]) or f"messenger_{t}"
            out.append({"url": url, "mime": mime_of[t], "filename": fn, "ref": url})
    return out


def _route_to_onboard_or_agent(channel, channel_user_id, display_name, username, message):
    """Returns (reply, state, passthrough). If passthrough=True, the channel
    adapter should forward to the AI Agent pathway (currently the n8n workflow)."""
    import requests
    r = requests.post("http://localhost:8765/api/onboard", json={
        "channel": channel, "channel_user_id": channel_user_id,
        "display_name": display_name, "username": username,
        "message": message,
        # every caller of this helper has already _log_inbound()ed the message and sends the
        # reply inline (writing its own 'sent' row) — suppress the endpoint's duplicate writes
        "adapter_logged": True,
    }, timeout=30)
    if r.status_code != 200:
        return ("⚠ Internal error processing your message. Please try again shortly.", "error", False)
    j = r.json()
    return (j.get("reply"), j.get("state_after"), j.get("passthrough", False))


def _forward_to_agent(channel, channel_user_id, display_name, username, message):
    """POST an approved user's message to the n8n AI Agent webhook
    (env: N8N_CHAT_WEBHOOK_URL). Returns True on 2xx. The n8n side is
    expected to dispatch the response back via the normal outbound sender
    for the channel, so this function does not return a reply body."""
    import requests
    url = _env("N8N_CHAT_WEBHOOK_URL")
    status = "pending_no_agent_webhook"
    if url:
        try:
            r = requests.post(url, json={
                "channel": channel, "channel_user_id": channel_user_id,
                "display_name": display_name, "username": username,
                "message": message,
            }, timeout=30)
            ok = 200 <= r.status_code < 300
            status = "forwarded_to_agent" if ok else f"agent_http_{r.status_code}"
        except Exception as e:
            ok = False
            status = f"agent_error:{type(e).__name__}"
    else:
        ok = False

    conn = _db(); conn.autocommit = True; cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO channel_messages
              (channel_id, channel_user_id, direction, text_content, sent_at, status, metadata)
            VALUES ((SELECT id FROM channels WHERE name=%s), %s, 'inbound', %s, now(), %s,
                    jsonb_build_object('forwarded_to', 'n8n_agent'))
        """, (channel, str(channel_user_id), message, status))
    finally:
        cur.close(); conn.close()
    return ok


# ════════════════════════════════════════════════════════════════
# WhatsApp Business (Meta / 360dialog) — inbound webhook
# ════════════════════════════════════════════════════════════════

@bp.route("/api/channel/whatsapp", methods=["GET", "POST"])
def whatsapp_webhook():
    # Meta verification (GET) — return the challenge
    if request.method == "GET":
        verify_token = _env("WHATSAPP_VERIFY_TOKEN", "")
        if request.args.get("hub.verify_token") == verify_token and verify_token:
            return request.args.get("hub.challenge", ""), 200
        return "verification_failed", 403

    payload = request.get_json(silent=True) or {}
    # Meta payload structure: entry[].changes[].value.messages[]
    try:
        entries = payload.get("entry", [])
        results = []
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                contacts = {c["wa_id"]: c.get("profile", {}).get("name", "")
                            for c in value.get("contacts", [])}
                for msg in value.get("messages", []):
                    wa_id = msg.get("from", "")
                    text = (msg.get("text", {}).get("body") or "").strip()
                    display = contacts.get(wa_id, wa_id)
                    if not text or not wa_id: continue
                    _log_inbound("whatsapp", wa_id, text, raw_payload=msg)
                    reply, state, passthrough = _route_to_onboard_or_agent(
                        "whatsapp", wa_id, display, None, text)
                    forwarded = False
                    if reply:
                        _whatsapp_send(wa_id, reply)
                    elif passthrough:
                        forwarded = _forward_to_agent("whatsapp", wa_id, display, None, text)
                        if not forwarded:
                            _whatsapp_send(wa_id, "Thank you — our team has been notified.")
                    results.append({"wa_id": wa_id, "state": state,
                                    "replied": bool(reply), "forwarded": forwarded})
        return jsonify({"ok": True, "processed": results}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _whatsapp_send(to_wa_id, text):
    """Send a WhatsApp message via 360dialog/Meta Cloud API."""
    import requests
    token = _env("WHATSAPP_API_TOKEN")
    phone_id = _env("WHATSAPP_PHONE_NUMBER_ID")
    if not token or not phone_id:
        # No credentials yet — log to channel_messages as 'pending_send'
        conn = _db(); conn.autocommit = True; cur = conn.cursor()
        cur.execute("""
            INSERT INTO channel_messages
              (channel_id, channel_user_id, direction, text_content, sent_at, status, metadata)
            VALUES ((SELECT id FROM channels WHERE name='whatsapp'), %s, 'outbound', %s, now(),
                    'pending_no_credentials', '{"reason":"WHATSAPP_API_TOKEN not configured"}'::jsonb)
        """, (to_wa_id, text))
        cur.close(); conn.close()
        return False
    try:
        r = requests.post(
            f"https://graph.facebook.com/v18.0/{phone_id}/messages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"messaging_product": "whatsapp", "to": to_wa_id,
                  "type": "text", "text": {"body": text}},
            timeout=15,
        )
        ok = r.status_code in (200, 201)
        conn = _db(); conn.autocommit = True; cur = conn.cursor()
        cur.execute("""
            INSERT INTO channel_messages
              (channel_id, channel_user_id, direction, text_content, sent_at, status, external_msg_id)
            VALUES ((SELECT id FROM channels WHERE name='whatsapp'), %s, 'outbound', %s, now(),
                    %s, %s)
        """, (to_wa_id, text, "sent" if ok else "failed",
              r.json().get("messages", [{}])[0].get("id") if ok else None))
        cur.close(); conn.close()
        return ok
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════
# Viber Public Account / Bot — inbound webhook + outbound send
# (mirrors WhatsApp; auth via X-Viber-Auth-Token. Needs a public HTTPS
#  webhook URL registered once via scripts/viber_set_webhook.py.)
# ════════════════════════════════════════════════════════════════

VIBER_SEND_URL = "https://chatapi.viber.com/pa/send_message"


@bp.route("/api/channel/viber", methods=["POST"])
def viber_webhook():
    """Viber Bot callback. Events: webhook(verify), conversation_started, message, delivered/seen/failed.
    Viber requires a 200 to every callback; for conversation_started the response body becomes the greeting."""
    payload = request.get_json(silent=True) or {}
    event = payload.get("event")
    if event == "webhook":
        return jsonify({"status": 0}), 200                       # set_webhook verification ping
    if event == "conversation_started":
        return jsonify({"sender": {"name": _env("VIBER_SENDER_NAME", "Leo · LandTek")},
                        "type": "text",
                        "text": "Hello — this is Leo, the assistant for LandTek. How can I help?"}), 200
    if event != "message":
        return jsonify({"status": 0}), 200                       # delivered/seen/subscribed/unsubscribed/failed — ack
    try:
        sender = payload.get("sender", {}) or {}
        uid = str(sender.get("id") or "")
        name = sender.get("name") or uid
        msg = payload.get("message", {}) or {}
        text = (msg.get("text") or "").strip() if msg.get("type") == "text" else ""
        if not uid or not text:
            return jsonify({"status": 0}), 200                   # non-text (image/file/location) — ack, no route
        _log_inbound("viber", uid, text, raw_payload=payload)
        reply, state, passthrough = _route_to_onboard_or_agent("viber", uid, name, None, text)
        if reply:
            _viber_send(uid, reply)
        elif passthrough:
            if not _forward_to_agent("viber", uid, name, None, text):
                _viber_send(uid, "Thank you — our team has been notified.")
        return jsonify({"status": 0}), 200
    except Exception as e:
        return jsonify({"status": 3, "status_message": str(e)}), 200


def _viber_send(receiver_id, text):
    """Send a Viber message via the Public Account API; queue as pending_viber_send if no token yet."""
    import requests
    token = _env("VIBER_AUTH_TOKEN")
    name = _env("VIBER_SENDER_NAME", "Leo · LandTek")
    if not token:
        conn = _db(); conn.autocommit = True; cur = conn.cursor()
        cur.execute("""
            INSERT INTO channel_messages
              (channel_id, channel_user_id, direction, text_content, sent_at, status, metadata)
            VALUES ((SELECT id FROM channels WHERE name='viber'), %s, 'outbound', %s, now(),
                    'pending_viber_send', '{"reason":"VIBER_AUTH_TOKEN not configured"}'::jsonb)
        """, (receiver_id, text))
        cur.close(); conn.close()
        return False
    try:
        r = requests.post(VIBER_SEND_URL,
                          headers={"X-Viber-Auth-Token": token, "Content-Type": "application/json"},
                          json={"receiver": receiver_id, "type": "text", "text": text,
                                "sender": {"name": name}}, timeout=15)
        j = r.json() if r.content else {}
        ok = r.status_code == 200 and j.get("status") == 0
        conn = _db(); conn.autocommit = True; cur = conn.cursor()
        cur.execute("""
            INSERT INTO channel_messages
              (channel_id, channel_user_id, direction, text_content, sent_at, status, external_msg_id)
            VALUES ((SELECT id FROM channels WHERE name='viber'), %s, 'outbound', %s, now(), %s, %s)
        """, (receiver_id, text, "sent" if ok else "failed",
              str(j.get("message_token")) if ok else None))
        cur.close(); conn.close()
        return ok
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════
# Facebook Messenger — inbound webhook + outbound send
# (clones the WhatsApp pattern: same Meta platform, same GET verify-
#  challenge, graph.facebook.com send. ARMED TOKENLESS by design —
#  provisioning MESSENGER_PAGE_TOKEN is the external switch, A26.)
# ════════════════════════════════════════════════════════════════

@bp.route("/api/channel/messenger", methods=["GET", "POST"])
def messenger_webhook():
    # Meta verification (GET) — return the challenge (same handshake as WhatsApp)
    if request.method == "GET":
        verify_token = _env("MESSENGER_VERIFY_TOKEN", "")
        if request.args.get("hub.verify_token") == verify_token and verify_token:
            return request.args.get("hub.challenge", ""), 200
        return "verification_failed", 403

    payload = request.get_json(silent=True) or {}
    # Meta payload structure: entry[].messaging[] with sender.id (PSID) + message.text
    try:
        results = []
        for entry in payload.get("entry", []):
            for ev in entry.get("messaging", []):
                msg = ev.get("message") or {}
                if msg.get("is_echo"):
                    continue  # our own sends echoed back — never route
                psid = (ev.get("sender") or {}).get("id", "")
                text = (msg.get("text") or "").strip()
                atts = _messenger_attachments(msg)
                if (not text and not atts) or not psid:
                    continue
                cmid = _log_inbound("messenger", psid, text or "[media]", raw_payload=ev)
                # media-lossless: fetch every attachment into the universal sink (never dropped)
                media = _ingest_channel_media("messenger", psid, cmid, atts)
                reply = state = None; passthrough = forwarded = False
                if text:
                    reply, state, passthrough = _route_to_onboard_or_agent(
                        "messenger", psid, psid, None, text)
                    if reply:
                        _messenger_send(psid, reply)               # onboarding reply — always the adapter's
                    elif passthrough and _headless("messenger"):
                        pass  # cut over: leo_service (headless) drafts + holds this approved user's reply
                    elif passthrough:
                        forwarded = _forward_to_agent("messenger", psid, psid, None, text)
                        if not forwarded:
                            _messenger_send(psid, "Thank you — our team has been notified.")
                elif media and any(m.get("status") in ("landed", "deduped") for m in media):
                    _messenger_send(psid, "Got it — I've saved your file for our team. Thank you.")
                results.append({"psid": psid, "state": state, "replied": bool(reply),
                                "forwarded": forwarded, "media": [m.get("status") for m in media]})
        return jsonify({"ok": True, "processed": results}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _messenger_send(psid, text):
    """Send a Messenger message via the Meta Graph Send API; queue as pending_no_credentials if no token."""
    import requests
    text = _plain_text(text)  # Messenger renders raw text — strip Telegram-style HTML
    token = _env("MESSENGER_PAGE_TOKEN")
    if not token:
        conn = _db(); conn.autocommit = True; cur = conn.cursor()
        cur.execute("""
            INSERT INTO channel_messages
              (channel_id, channel_user_id, direction, text_content, sent_at, status, metadata)
            VALUES ((SELECT id FROM channels WHERE name='messenger'), %s, 'outbound', %s, now(),
                    'pending_no_credentials', '{"reason":"MESSENGER_PAGE_TOKEN not configured"}'::jsonb)
        """, (psid, text))
        cur.close(); conn.close()
        return False
    try:
        r = requests.post(
            "https://graph.facebook.com/v18.0/me/messages",
            params={"access_token": token},
            json={"recipient": {"id": psid}, "messaging_type": "RESPONSE",
                  "message": {"text": text}},
            timeout=15,
        )
        ok = r.status_code in (200, 201)
        conn = _db(); conn.autocommit = True; cur = conn.cursor()
        cur.execute("""
            INSERT INTO channel_messages
              (channel_id, channel_user_id, direction, text_content, sent_at, status, external_msg_id)
            VALUES ((SELECT id FROM channels WHERE name='messenger'), %s, 'outbound', %s, now(), %s, %s)
        """, (psid, text, "sent" if ok else "failed",
              (r.json().get("message_id") if ok else None)))
        cur.close(); conn.close()
        return ok
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════
# Web chat widget — inbound + outbound (HTTP polling or SSE)
# ════════════════════════════════════════════════════════════════

@bp.route("/api/channel/web", methods=["POST"])
def web_widget_inbound():
    payload = request.get_json(silent=True) or {}
    session_id = (payload.get("session_id") or "").strip()
    display = (payload.get("name") or "").strip() or None
    email = (payload.get("email") or "").strip() or None
    text = (payload.get("message") or "").strip()
    if not session_id or not text:
        return jsonify({"error": "session_id and message required"}), 400

    chuid = f"web:{session_id}"
    _log_inbound("web", chuid, text, raw_payload={"name": display, "email": email})
    reply, state, passthrough = _route_to_onboard_or_agent("web", chuid, display, email, text)
    return jsonify({"reply": reply or "Thank you — our team has been notified.",
                    "state": state, "session_id": session_id})


# ════════════════════════════════════════════════════════════════
# Email reply bot — receives webhook from Gmail watcher
# ════════════════════════════════════════════════════════════════

@bp.route("/api/channel/email", methods=["POST"])
def email_webhook():
    payload = request.get_json(silent=True) or {}
    from_addr = (payload.get("from") or "").strip()
    subject = (payload.get("subject") or "").strip()
    body = (payload.get("body") or "").strip()
    msg_id = (payload.get("message_id") or "").strip()
    if not from_addr or not body:
        return jsonify({"error": "from + body required"}), 400

    text = f"Subject: {subject}\n\n{body}"
    _log_inbound("email", from_addr, text, raw_payload={"subject": subject, "message_id": msg_id})
    reply, state, passthrough = _route_to_onboard_or_agent(
        "email", from_addr, None, from_addr, text)
    # Email replies are sent via Gmail integration (out of scope here);
    # log as pending until Gmail send adapter wired.
    if reply:
        conn = _db(); conn.autocommit = True; cur = conn.cursor()
        cur.execute("""
            INSERT INTO channel_messages
              (channel_id, channel_user_id, direction, text_content, sent_at, status, metadata)
            VALUES ((SELECT id FROM channels WHERE name='email'), %s, 'outbound', %s, now(),
                    'pending_gmail_send', %s::jsonb)
        """, (from_addr, reply, json.dumps({"in_reply_to": msg_id, "subject": f"Re: {subject}"})))
        cur.close(); conn.close()
    return jsonify({"ok": True, "state": state, "queued_reply": bool(reply)})


# ════════════════════════════════════════════════════════════════
# SMS (Twilio) — inbound webhook
# ════════════════════════════════════════════════════════════════

@bp.route("/api/channel/sms", methods=["POST"])
def sms_webhook():
    # Twilio sends application/x-www-form-urlencoded
    from_num = request.form.get("From") or request.values.get("From")
    body = request.form.get("Body") or request.values.get("Body")
    if not from_num or not body:
        return jsonify({"error": "missing From or Body"}), 400
    _log_inbound("sms", from_num, body)
    reply, state, passthrough = _route_to_onboard_or_agent("sms", from_num, None, from_num, body)
    if reply:
        # Twilio expects TwiML
        from flask import Response
        twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{reply}</Message></Response>'
        return Response(twiml, mimetype="text/xml")
    return jsonify({"ok": True, "state": state})


# ════════════════════════════════════════════════════════════════
# Public REST API (the licensable product surface)
# ════════════════════════════════════════════════════════════════

def _check_api_key():
    """Validate the X-API-Key header against api_keys table (if it exists)."""
    api_key = request.headers.get("X-API-Key") or request.args.get("api_key")
    if not api_key:
        return None, ("missing X-API-Key header", 401)
    conn = _db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, name, scope, rate_limit_per_min, active
          FROM api_keys WHERE key_hash = encode(digest(%s, 'sha256'), 'hex') AND active
        LIMIT 1
    """, (api_key,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        return None, ("invalid api key", 403)
    return row, None


@bp.route("/api/v1/leo/chat", methods=["POST"])
def v1_chat():
    auth, err = _check_api_key()
    if err: return jsonify({"error": err[0]}), err[1]
    payload = request.get_json(silent=True) or {}
    session_id = (payload.get("session_id") or "").strip() or secrets.token_hex(8)
    message = (payload.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message required"}), 400
    chuid = f"api:{auth['name']}:{session_id}"
    _log_inbound("api", chuid, message, raw_payload={"api_consumer": auth["name"]})
    reply, state, passthrough = _route_to_onboard_or_agent(
        "api", chuid, payload.get("user_name"), auth["name"], message)
    return jsonify({"reply": reply, "state": state, "session_id": session_id,
                    "consumer": auth["name"]})


@bp.route("/api/v1/leo/verify", methods=["POST"])
def v1_verify():
    auth, err = _check_api_key()
    if err: return jsonify({"error": err[0]}), err[1]
    payload = request.get_json(silent=True) or {}
    claim = (payload.get("claim") or "").strip()
    case = (payload.get("case") or "").strip() or None
    if not claim:
        return jsonify({"error": "claim required"}), 400
    sys.path.insert(0, "/root/landtek")
    from truth_negotiator import negotiate
    r = negotiate(claim, case_file=case, asked_by=f"api:{auth['name']}")
    return jsonify({
        "verdict": r["verdict"], "citation_tag": r["citation_tag"],
        "evidence_count": r["evidence_count"],
        "fact_backers": r["fact_backers"][:10],
        "challenger_disagrees": r["challenger_disagrees"],
        "challenger_reason": r["challenger_reason"],
        "negotiation_id": r["id"],
    })


@bp.route("/api/v1/leo/status", methods=["GET"])
def v1_status():
    auth, err = _check_api_key()
    if err: return jsonify({"error": err[0]}), err[1]
    conn = _db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT (SELECT count(*) FROM documents) AS docs,
               (SELECT count(*) FROM truth_negotiations) AS verifications,
               (SELECT count(*) FROM channel_users WHERE onboarding_state='approved') AS users,
               (SELECT count(*) FROM matters WHERE status='active') AS active_matters
    """)
    s = cur.fetchone()
    cur.close(); conn.close()
    return jsonify({
        "service": "leo-platform", "version": "0.116",
        "consumer": auth["name"],
        **{k: int(v) for k, v in s.items()}
    })


@bp.route("/api/v1/leo/version", methods=["GET"])
def v1_version():
    return jsonify({
        "name": "Leo Platform",
        "version": "0.116",
        "capabilities": [
            "truth-graded retrieval (bilingual EN+TL)",
            "case-stage classification (PH civil procedure)",
            "execution-status classification (notarized/filed/email/draft/gov-issued)",
            "asset valuation + risk profile + intrinsic value",
            "agency loop (deadline sentinel + goal accelerator)",
            "multi-channel adapters (telegram, whatsapp*, web*, email*, sms*, api)",
            "onboarding state machine for unknown senders",
        ],
        "note": "* indicates adapter present, awaiting provider credentials",
    })


# ════════════════════════════════════════════════════════════════
# Unified outbound send
# ════════════════════════════════════════════════════════════════

@bp.route("/api/channel/send", methods=["POST"])
def channel_send():
    """Send a message via any channel. Auth: operator-only (Jonathan check via param)."""
    payload = request.get_json(silent=True) or {}
    channel = payload.get("channel")
    recipient = str(payload.get("recipient_id") or "")
    text = (payload.get("text") or "").strip()
    operator = str(payload.get("operator_id") or "")
    if operator != JONATHAN_TG_ID:
        return jsonify({"error": "operator-only"}), 403
    if not channel or not recipient or not text:
        return jsonify({"error": "channel, recipient_id, text required"}), 400

    if channel == "telegram":
        import requests
        token = _env("TELEGRAM_BOT_TOKEN")
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": recipient, "text": text, "parse_mode": "HTML"})
        ok = r.status_code == 200
    elif channel == "whatsapp":
        ok = _whatsapp_send(recipient, text)
    elif channel == "viber":
        ok = _viber_send(recipient, text)
    else:
        # Web/Email/SMS handled by polling consumers
        ok = True

    conn = _db(); conn.autocommit = True; cur = conn.cursor()
    cur.execute("""
        INSERT INTO channel_messages
          (channel_id, channel_user_id, direction, text_content, sent_at, status, metadata)
        VALUES ((SELECT id FROM channels WHERE name=%s), %s, 'outbound', %s, now(), %s,
                jsonb_build_object('initiated_by', 'jonathan'))
    """, (channel, recipient, text, "sent" if ok else "failed"))
    cur.close(); conn.close()
    return jsonify({"ok": ok, "channel": channel, "recipient": recipient})
