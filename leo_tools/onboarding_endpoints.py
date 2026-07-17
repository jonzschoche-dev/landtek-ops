"""Onboarding state machine for unknown senders (deploy_116 + re-entry/A85-adjacent).

Endpoints:
  POST /api/onboard          — process inbound message in onboarding flow
  POST /api/approve_user     — Jonathan approves an awaiting user
  POST /api/deny_user        — Jonathan denies an awaiting user
  POST /api/reopen_user      — reset declined/blocked/misregistered user for a clean re-entry
  POST /api/correct_user     — fix display_name / role / case on an existing row (no full reset)
  GET  /api/pending_approvals — list awaiting_jonathan_approval users

When the n8n workflow detects a non-approved sender, it POSTs to /api/onboard
with {channel='telegram', channel_user_id=..., message=...}. The endpoint
runs the state machine and returns {reply: <text to send>, state_after, escalate}.

Re-entry (common failure): someone misregisters, is denied, or is deleted and comes
back on the SAME channel_user_id. We never invent a second row (UNIQUE per channel);
we archive prior state into metadata.reentry_history and restart cleanly — except
locked identities (approved operator/owner) which only move via /api/reopen_user.
"""
import os
import sys
import json
import re
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor

PG_DSN = os.getenv("LEO_TOOLS_PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN_TG_ID = "6513067717"

bp = Blueprint("onboarding_endpoints", __name__)

# Explicit re-entry / misregister phrases (EN + common Tagalog cues). Not silent.
REENTRY_PHRASES = (
    "start over", "start again", "start anew",
    "re-register", "reregister", "re register", "re-apply", "reapply", "re apply",
    "wrong name", "wrong identity", "wrong person", "not me", "that's not me",
    "i misregistered", "misregister", "mis-registered", "registered wrong",
    "new registration", "bagong register", "mag-register ulit", "register ulit",
    "please reopen", "reopen my", "try again please", "ulit po ang registration",
)


def _db():
    return psycopg2.connect(PG_DSN)


def _wants_reentry(message: str) -> bool:
    m = (message or "").lower()
    return any(p in m for p in REENTRY_PHRASES)


def _identity_locked(user: dict) -> bool:
    """Approved operator/owner (and any authorized approved principal) cannot be
    name-clobbered or auto-reset from chat — only operator API may reopen."""
    role = (user.get("approved_role") or user.get("role") or "").lower()
    if role in ("operator", "owner"):
        return True
    if user.get("onboarding_state") == "approved" and user.get("authorized"):
        # clients/counsel: locked against self-serve wipe; operator uses /reopen
        return True
    return False


def _as_dict(val):
    if val is None:
        return {}
    if isinstance(val, dict):
        return dict(val)
    if isinstance(val, str):
        try:
            return json.loads(val) or {}
        except Exception:
            return {}
    return {}


# Staff / internal roles that must leave a reachable phone + email after approval.
STAFF_CONTACT_ROLES = frozenset({
    "filing_assistant", "partner", "counsel", "operator", "owner",
})

STAFF_CONTACT_ASK = (
    "Welcome — your access is approved.\n\n"
    "One quick step for the team directory: please send your "
    "<b>mobile number</b> and <b>email address</b> in one message "
    "(example: 0917 123 4567 / kristyle@example.com)."
)

STAFF_CONTACT_NEED_PHONE = (
    "Got your email. Please also send your <b>mobile number</b> "
    "(example: 0917 123 4567)."
)

STAFF_CONTACT_NEED_EMAIL = (
    "Got your number. Please also send your <b>email address</b>."
)

STAFF_CONTACT_DONE = (
    "Thank you — phone and email are on file. "
    "You can message me freely for vault filing and case coordination."
)

STAFF_CONTACT_RETRY = (
    "I still need both a mobile number and an email. "
    "Please reply in one message, e.g. 0917 123 4567 / you@example.com"
)


def _extract_email(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", text)
    return m.group(0).strip() if m else None


def _extract_phone(text: str) -> str | None:
    """Best-effort PH / international mobile; keep digits with leading + if present."""
    if not text:
        return None
    # Prefer explicit +63 / 09 patterns before generic digit runs.
    patterns = (
        r"\+63[\s\-]?\d{3}[\s\-]?\d{3}[\s\-]?\d{4}",
        r"\b09\d{2}[\s\-]?\d{3}[\s\-]?\d{4}\b",
        r"\b63\d{10}\b",
        r"\+\d{10,15}\b",
    )
    for p in patterns:
        m = re.search(p, text)
        if m:
            raw = m.group(0)
            digits = re.sub(r"[^\d+]", "", raw)
            if digits.startswith("+"):
                return "+" + re.sub(r"\D", "", digits[1:])
            only = re.sub(r"\D", "", digits)
            if only.startswith("09") and len(only) == 11:
                return only
            if only.startswith("63") and len(only) == 12:
                return "+" + only
            if len(only) >= 10:
                return only
    return None


def _client_id_for_user(user: dict) -> int | None:
    meta = _as_dict(user.get("metadata"))
    cid = meta.get("linked_client_id")
    if cid is not None:
        try:
            return int(cid)
        except (TypeError, ValueError):
            pass
    return None


def _staff_needs_contact(cur, user: dict) -> bool:
    role = (user.get("approved_role") or user.get("role") or "").lower()
    if role not in STAFF_CONTACT_ROLES:
        return False
    if role in ("operator", "owner"):
        return False  # principals already known; never nag Jonathan
    responses = _as_dict(user.get("onboarding_responses"))
    if (responses.get("phone") or "").strip() and (responses.get("email") or "").strip():
        return False
    client_id = _client_id_for_user(user)
    if client_id:
        cur.execute("SELECT email, phone FROM clients WHERE id = %s", (client_id,))
        row = cur.fetchone()
        if row:
            email = (row.get("email") if isinstance(row, dict) else row[0]) or ""
            phone = (row.get("phone") if isinstance(row, dict) else row[1]) or ""
            if str(email).strip() and str(phone).strip():
                return False
    # Also check telegram_id match on clients
    cuid = str(user.get("channel_user_id") or "")
    if cuid:
        cur.execute(
            "SELECT email, phone FROM clients WHERE telegram_id = %s LIMIT 1",
            (cuid,),
        )
        row = cur.fetchone()
        if row:
            email = (row.get("email") if isinstance(row, dict) else row[0]) or ""
            phone = (row.get("phone") if isinstance(row, dict) else row[1]) or ""
            if str(email).strip() and str(phone).strip():
                return False
    return True


def _save_staff_contact(cur, user: dict, email: str | None, phone: str | None) -> dict:
    """Persist partial/full contact onto channel_users + clients. Returns updated responses."""
    responses = _as_dict(user.get("onboarding_responses"))
    meta = _as_dict(user.get("metadata"))
    if email:
        responses["email"] = email
        meta["email"] = email
    if phone:
        responses["phone"] = phone
        meta["phone"] = phone
    cur.execute(
        """UPDATE channel_users
              SET onboarding_responses = %s::jsonb,
                  metadata = %s::jsonb,
                  last_seen_at = now()
            WHERE id = %s""",
        (json.dumps(responses), json.dumps(meta), user["id"]),
    )
    client_id = _client_id_for_user(user)
    sets, args = [], []
    if email:
        sets.append("email = COALESCE(NULLIF(email, ''), %s)")
        args.append(email)
    if phone:
        sets.append("phone = COALESCE(NULLIF(phone, ''), %s)")
        args.append(phone)
    if sets and client_id:
        args.append(client_id)
        cur.execute(
            f"UPDATE clients SET {', '.join(sets)}, updated_at = now() WHERE id = %s",
            args,
        )
    elif sets:
        # Fall back: match by telegram_id if this is a TG identity
        cuid = str(user.get("channel_user_id") or "")
        if cuid.isdigit() or cuid:
            args2 = list(args) + [cuid]
            cur.execute(
                f"UPDATE clients SET {', '.join(sets)}, updated_at = now() "
                f"WHERE telegram_id = %s",
                args2,
            )
    return responses


def _handle_staff_contact(cur, user: dict, message: str) -> tuple[str, str, dict]:
    """Process a message while collecting staff phone+email.

    Returns (reply, next_state, responses).
    """
    responses = _as_dict(user.get("onboarding_responses"))
    email = _extract_email(message) or (responses.get("email") or "").strip() or None
    phone = _extract_phone(message) or (responses.get("phone") or "").strip() or None
    if email or phone:
        responses = _save_staff_contact(cur, user, email, phone)
        email = (responses.get("email") or "").strip() or None
        phone = (responses.get("phone") or "").strip() or None

    if email and phone:
        responses["staff_contact_completed_at"] = datetime.now(timezone.utc).isoformat()
        return STAFF_CONTACT_DONE, "approved", responses
    if email and not phone:
        return STAFF_CONTACT_NEED_PHONE, "awaiting_staff_contact", responses
    if phone and not email:
        return STAFF_CONTACT_NEED_EMAIL, "awaiting_staff_contact", responses
    # First ask or unparseable
    if not (message or "").strip() or message.strip().lower() in (
        "ok", "okay", "yes", "sure", "sige", "go",
    ):
        return STAFF_CONTACT_ASK, "awaiting_staff_contact", responses
    return STAFF_CONTACT_RETRY, "awaiting_staff_contact", responses


def _archive_and_reset(cur, user: dict, reason: str, *, keep_authorized: bool = False) -> dict:
    """Same channel_user_id, clean onboarding slate. Prior attempt → metadata.reentry_history."""
    responses = _as_dict(user.get("onboarding_responses"))
    meta = _as_dict(user.get("metadata"))
    hist = list(meta.get("reentry_history") or [])
    hist.append({
        "at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "from_state": user.get("onboarding_state"),
        "prior_display_name": user.get("display_name"),
        "prior_role": user.get("role"),
        "prior_approved_role": user.get("approved_role"),
        "prior_mapped_client_code": user.get("mapped_client_code"),
        "prior_responses": responses,
    })
    meta["reentry_history"] = hist[-20:]
    meta["last_reentry_at"] = datetime.now(timezone.utc).isoformat()
    meta["last_reentry_reason"] = reason

    locked_role = (user.get("approved_role") or user.get("role") or "").lower() in (
        "operator", "owner",
    )
    if locked_role or keep_authorized:
        # should rarely reset operators; if forced via API, keep principal flags
        cur.execute("""
            UPDATE channel_users
               SET onboarding_state = 'awaiting_intro',
                   onboarding_responses = '{}'::jsonb,
                   onboarding_started_at = now(),
                   onboarding_completed_at = NULL,
                   pending_approval_msg_id = NULL,
                   metadata = %s::jsonb,
                   last_seen_at = now()
             WHERE id = %s
         RETURNING *""", (json.dumps(meta), user["id"]))
    else:
        cur.execute("""
            UPDATE channel_users
               SET onboarding_state = 'awaiting_intro',
                   onboarding_responses = '{}'::jsonb,
                   onboarding_started_at = now(),
                   onboarding_completed_at = NULL,
                   role = 'unknown',
                   approved_role = NULL,
                   approved_by = NULL,
                   approved_scope_case = NULL,
                   authorized = false,
                   authorized_at = NULL,
                   authorized_by = NULL,
                   mapped_client_code = NULL,
                   pending_approval_msg_id = NULL,
                   metadata = %s::jsonb,
                   last_seen_at = now()
             WHERE id = %s
         RETURNING *""", (json.dumps(meta), user["id"]))
    row = cur.fetchone()
    return dict(row) if row else user


def _get_or_create_user(cur, channel_name, channel_user_id, display_name=None, username=None):
    cur.execute("""
        SELECT cu.* FROM channel_users cu
          JOIN channels c ON c.id = cu.channel_id
         WHERE c.name = %s AND cu.channel_user_id = %s
    """, (channel_name, str(channel_user_id)))
    row = cur.fetchone()
    if row:
        user = dict(row)
        # Soft-refresh username in metadata only — NEVER clobber locked display_name
        # (Telegram first_name is user-editable and caused "Jj Moreno" on operator id).
        if username and not _identity_locked(user):
            meta = _as_dict(user.get("metadata"))
            if meta.get("username") != username:
                meta["username"] = username
                cur.execute(
                    "UPDATE channel_users SET metadata=%s::jsonb, last_seen_at=now() WHERE id=%s",
                    (json.dumps(meta), user["id"]))
        elif not _identity_locked(user):
            cur.execute("UPDATE channel_users SET last_seen_at=now() WHERE id=%s", (user["id"],))
        else:
            cur.execute("UPDATE channel_users SET last_seen_at=now() WHERE id=%s", (user["id"],))
        return user, False
    cur.execute("""
        INSERT INTO channel_users (channel_id, channel_user_id, display_name,
                                     role, authorized, onboarding_state,
                                     onboarding_started_at, first_seen_at,
                                     last_seen_at, metadata)
        SELECT id, %s, %s, 'unknown', false, 'awaiting_intro',
               now(), now(), now(), %s::jsonb
          FROM channels WHERE name = %s
        RETURNING *
    """, (str(channel_user_id), display_name or username or f"tg:{channel_user_id}",
          json.dumps({"username": username}), channel_name))
    return dict(cur.fetchone()), True


def _send_tg(text, chat_id=None):
    """Helper to DM Jonathan or a target chat."""
    sys.path.insert(0, "/root/landtek")
    from build_digest import tg_send
    if chat_id and str(chat_id) != JONATHAN_TG_ID:
        # build_digest.tg_send only hits Jonathan; for other recipients use direct API
        import requests
        env = {}
        with open("/root/landtek/.env") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.strip().partition("="); env[k.strip()] = v.strip()
        requests.post(
            f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True}, timeout=15)
    else:
        tg_send(text)


# ── State machine ─────────────────────────────────────────────────────────

INTRO_REPLY = (
    "Magandang araw! I'm <b>Leo</b>, the assistant for <b>LandTek</b>, a Philippine "
    "land and property services company based in Camarines Norte.\n\n"
    "I don't recognize you yet. To help you properly, could you tell me:\n"
    "• Your full name\n"
    "• Are you (a) an existing LandTek client, (b) counsel or a party in a matter we support, "
    "(c) seeking assistance with a property matter, or (d) something else?"
)

CLASSIFY_REPLY = (
    "Salamat, {name}. One more thing — what's this regarding?\n"
    "• A specific case (please share docket number / TCT / property location)\n"
    "• A general inquiry\n"
    "• A new matter you'd like Landtek to handle"
)

ESCALATE_REPLY = (
    "Thanks, {name}. I've forwarded your message to our team "
    "for review. They'll reach out shortly to confirm next steps.\n\n"
    "In the meantime, feel free to send any documents or context you'd like us to see — "
    "I'll capture them but won't act on them until engagement is approved."
)

DECLINED_REPLY = (
    "Thank you for reaching out. After review, "
    "LandTek is unable to assist at this time. If circumstances change, please contact us through "
    "our office directly."
)

LIMITED_REPLY_PROSPECT = (
    "While we await confirmation, here's what I can share:\n"
    "• <b>LandTek</b> is a Philippine land and property services company — title verification, "
    "property records and documentation, estate/property support.\n"
    "• LandTek is not a law firm; litigation is handled by engaged counsel — "
    "Atty. Bonifacio T. Barandon Jr. (Daet, Camarines Norte) leads litigation matters we support.\n"
    "• Our team handles intake and will be in touch within 1-2 business days.\n\n"
    "If you'd like, send any property documents (TCT, tax dec, deed) — I'll log them safely "
    "for review."
)


@bp.route("/api/onboard", methods=["POST"])
def api_onboard():
    """Process an inbound message for a non-approved sender."""
    payload = request.get_json(silent=True) or {}
    channel = (payload.get("channel") or "telegram").strip()
    channel_user_id = str(payload.get("channel_user_id") or "")
    display_name = payload.get("display_name")
    username = payload.get("username")
    message = (payload.get("message") or "").strip()
    # adapter_logged: the channel adapter already wrote the inbound row (_log_inbound with raw
    # payload) and will send + log the reply inline itself. Skip this endpoint's ledger writes to
    # avoid double rows. Telegram/n8n posts WITHOUT this flag and keeps them (its only ledger).
    adapter_logged = bool(payload.get("adapter_logged"))
    if not channel_user_id:
        return jsonify({"error": "channel_user_id required"}), 400

    conn = _db(); conn.autocommit = True
    cur = conn.cursor(cursor_factory=RealDictCursor)
    user, created = _get_or_create_user(cur, channel, channel_user_id, display_name, username)
    # Re-fetch after last_seen touch
    cur.execute("SELECT * FROM channel_users WHERE id=%s", (user["id"],))
    user = dict(cur.fetchone())
    state = user["onboarding_state"]
    responses = _as_dict(user.get("onboarding_responses"))

    if not adapter_logged:
        cur.execute("""
            INSERT INTO channel_messages
              (channel_id, channel_user_id, direction, text_content, sent_at, status, metadata)
            VALUES ((SELECT id FROM channels WHERE name=%s), %s, 'inbound', %s, now(), 'received',
                    jsonb_build_object('onboarding_state_at_receipt', %s))
        """, (channel, channel_user_id, message, state))

    reply = None
    next_state = state
    escalate = False
    reentered = False

    # ── Clean re-entry / misregister (same channel_user_id — never a second row) ──
    # Allowed from in-progress or declined. Not from blocked (operator must /reopen).
    # Not from locked approved identities (prevents adversarial wipe).
    if (not created and not _identity_locked(user)
            and state in ("awaiting_intro", "awaiting_classification",
                          "awaiting_jonathan_approval", "declined")
            and _wants_reentry(message)):
        user = _archive_and_reset(cur, user, reason=f"user_requested:{message[:120]}")
        state = "awaiting_intro"
        responses = {}
        reentered = True
        reply = (
            "Understood — we'll start your registration over cleanly. "
            "Your earlier answers were saved for our team, not lost.\n\n" + INTRO_REPLY
        )
        next_state = "awaiting_intro"

    elif state == "awaiting_staff_contact":
        # Authorized staff — still need phone + email for the directory before free chat.
        reply, next_state, responses = _handle_staff_contact(cur, user, message)

    elif state == "approved":
        # Staff missing directory contact stay gated; everyone else → AI agent / headless.
        if _staff_needs_contact(cur, user):
            reply, next_state, responses = _handle_staff_contact(cur, user, message)
            if next_state == "awaiting_staff_contact" and not (message or "").strip():
                reply = STAFF_CONTACT_ASK
        else:
            cur.close(); conn.close()
            return jsonify({"reply": None, "state_after": "approved", "escalate": False,
                            "passthrough": True, "role": user.get("approved_role")})

    elif state == "declined":
        # Absorbing until they ask to re-apply (handled above) or operator reopens
        reply = (
            DECLINED_REPLY
            + "\n\nIf you'd like us to reconsider, reply with: <b>re-apply</b>"
        )
        next_state = "declined"

    elif state == "blocked":
        # Silent block — operator uses POST /api/reopen_user to clear
        cur.close(); conn.close()
        return jsonify({"reply": None, "state_after": "blocked", "passthrough": False})

    elif state == "awaiting_intro":
        if created or reentered:
            # First-ever message OR clean re-entry: INTRO and stay in awaiting_intro
            # (reentered already set reply above)
            if not reentered:
                reply = INTRO_REPLY
                next_state = "awaiting_intro"
                responses["first_message"] = message
            else:
                responses["first_message"] = message
                # already replied INTRO
        else:
            # User replied with their intro
            responses["intro_text"] = message
            m = re.search(
                r"(?:I['’]?m|my name is|ako (?:po )?si|ako ay|si)\s+"
                r"([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){0,3})",
                message, re.IGNORECASE)
            inferred_name = m.group(1).strip() if m else (display_name or "")
            if inferred_name and inferred_name.lower() != "leo":
                responses["inferred_name"] = inferred_name
                # Never overwrite locked principal names
                if not _identity_locked(user):
                    cur.execute(
                        "UPDATE channel_users SET display_name = %s WHERE id = %s",
                        (inferred_name, user["id"]))
            mlow = message.lower()
            intent = None
            if any(k in mlow for k in ("client of landtek", "i'm a client", "existing client", "your client")):
                intent = "existing_client"
            elif any(k in mlow for k in ("opposing", "defendant", "respondent", "counterparty", "para sa kabilang panig", "kalaban")):
                intent = "counterparty"
            elif any(k in mlow for k in ("counsel for", "atty. ", "my counsel", "abogado", "representing")):
                intent = "counsel"
            elif any(k in mlow for k in ("hire", "engage", "represent me", "kumuha ng abogado", "magpa-hire", "seeking representation", "looking for a lawyer", "tulong sa", "land case", "property case")):
                intent = "prospect_client"
            if intent:
                responses["self_classified_intent"] = intent
            reply = CLASSIFY_REPLY.format(name=inferred_name or "po")
            next_state = "awaiting_classification"

    elif state == "awaiting_classification":
        responses["matter_description"] = message
        m_docket = re.search(r"(civil\s+case\s+no\.?\s*|cv[\-\s]?)([\dA-Z\-]+)", message, re.IGNORECASE)
        m_tct = re.search(r"\b(T(?:CT)?[\-\s]?\d{3,7}(?:[\-\s]\d{3,7})?)\b", message, re.IGNORECASE)
        m_arp = re.search(r"(GR-\d{4}-[A-Z]{2}-\d{2}-\d{3}-\d{5}|ARP-?\d+)", message, re.IGNORECASE)
        if m_docket: responses["docket"] = m_docket.group(0)
        if m_tct: responses["tct"] = m_tct.group(0)
        if m_arp: responses["arp"] = m_arp.group(0)

        next_state = "awaiting_jonathan_approval"
        reply = ESCALATE_REPLY.format(name=responses.get("inferred_name") or "po")
        escalate = True

    elif state == "awaiting_jonathan_approval":
        # User keeps sending while waiting — capture but keep them in queue
        prior = responses.get("messages_while_waiting", [])
        prior.append({"text": message[:1000], "at": datetime.now(timezone.utc).isoformat()})
        responses["messages_while_waiting"] = prior[-10:]  # cap
        if (responses.get("self_classified_intent") or "").startswith("prospect"):
            reply = LIMITED_REPLY_PROSPECT
        else:
            reply = (
                "Our team is still reviewing — I'll relay any documents you send. "
                "They'll respond directly.\n\n"
                "If you registered under the wrong name or details, reply: <b>start over</b>"
            )

    # Persist state + responses
    cur.execute("""
        UPDATE channel_users
           SET onboarding_state = %s,
               onboarding_responses = %s::jsonb,
               last_seen_at = now()
         WHERE id = %s
    """, (next_state, json.dumps(responses), user["id"]))

    # Log outbound reply (skip when the adapter sends inline and writes its own 'sent' row)
    if reply and not adapter_logged:
        cur.execute("""
            INSERT INTO channel_messages
              (channel_id, channel_user_id, direction, text_content, sent_at, status)
            VALUES ((SELECT id FROM channels WHERE name=%s), %s, 'outbound', %s, now(), 'queued')
        """, (channel, channel_user_id, reply))

    # Escalate to Jonathan
    if escalate:
        sender_name = responses.get("inferred_name") or display_name or username or f"tg:{channel_user_id}"
        intent = responses.get("self_classified_intent") or "unknown"
        detail = []
        if responses.get("docket"): detail.append(f"docket={responses['docket']}")
        if responses.get("tct"): detail.append(f"TCT={responses['tct']}")
        if responses.get("arp"): detail.append(f"ARP={responses['arp']}")
        if responses.get("matter_description"):
            detail.append(f"matter='{responses['matter_description'][:200]}'")
        notify = (
            "🆕 <b>New inbound — onboarding pending</b>\n"
            f"Name: <b>{sender_name}</b>\n"
            f"Telegram: tg_id=<code>{channel_user_id}</code>"
            f" · @{username or '—'}\n"
            f"Intent: <b>{intent}</b>\n"
            + ("Details: " + " · ".join(detail) + "\n" if detail else "")
            + f"Intro: <i>{(responses.get('intro_text') or '')[:300]}</i>\n\n"
            "<b>Actions:</b>\n"
            f"  <code>/approve {channel_user_id} client</code>      — grant scoped client access\n"
            f"  <code>/approve {channel_user_id} prospect</code>    — limited prospect access\n"
            f"  <code>/approve {channel_user_id} counsel</code>     — fellow counsel access\n"
            f"  <code>/approve {channel_user_id} partner</code>     — affiliate/partner access\n"
            f"  <code>/deny {channel_user_id} <reason></code>       — decline politely\n"
            f"  <code>/block {channel_user_id} <reason></code>      — silent block"
        )
        _send_tg(notify, chat_id=JONATHAN_TG_ID)

    cur.close(); conn.close()
    return jsonify({
        "reply": reply,
        "state_after": next_state,
        "escalate": escalate,
        "passthrough": False,
        "created": created,
        "reentered": reentered,
        "user_id": user["id"],
    })


@bp.route("/api/reopen_user", methods=["POST", "GET"])
def api_reopen_user():
    """Operator: reset a user for clean re-entry (declined / blocked / misapproved).

    Args: id (channel_user_id), reason (optional), channel (optional filter).
    Archives prior state to metadata.reentry_history — does NOT delete the row.
    """
    if request.method == "POST":
        p = request.get_json(silent=True) or {}
        cid = str(p.get("id") or "")
        reason = (p.get("reason") or "operator_reopen").strip()
        channel = (p.get("channel") or "").strip() or None
    else:
        cid = (request.args.get("id") or "").strip()
        reason = (request.args.get("reason") or "operator_reopen").strip()
        channel = (request.args.get("channel") or "").strip() or None
    if not cid:
        return jsonify({"error": "id required"}), 400

    conn = _db(); conn.autocommit = True
    cur = conn.cursor(cursor_factory=RealDictCursor)
    if channel:
        cur.execute("""
            SELECT cu.* FROM channel_users cu
              JOIN channels c ON c.id = cu.channel_id
             WHERE cu.channel_user_id = %s AND c.name = %s
        """, (cid, channel))
    else:
        cur.execute("SELECT * FROM channel_users WHERE channel_user_id = %s ORDER BY id DESC LIMIT 1",
                    (cid,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return jsonify({"error": f"no user with channel_user_id={cid}"}), 404
    user = dict(row)
    if (user.get("approved_role") or user.get("role") or "").lower() in ("operator", "owner"):
        cur.close(); conn.close()
        return jsonify({"error": "refuse: cannot reopen operator/owner identity via this API"}), 403

    fresh = _archive_and_reset(cur, user, reason=f"operator:{reason}")
    _send_tg(
        f"✓ Reopened <b>{fresh.get('display_name') or cid}</b> "
        f"(id=<code>{cid}</code>) for clean re-entry — reason: {reason}"
    )
    # Notify user if telegram-like numeric id
    if cid.isdigit():
        _send_tg(
            "Your LandTek access was reset so you can register again cleanly. "
            "Please send any message to begin.",
            chat_id=cid,
        )
    cur.close(); conn.close()
    return jsonify({"ok": True, "user_id": fresh.get("id"), "state": "awaiting_intro",
                    "reentry_history_n": len(_as_dict(fresh.get("metadata")).get("reentry_history") or [])})


@bp.route("/api/correct_user", methods=["POST", "GET"])
def api_correct_user():
    """Operator: fix misregistration without wiping history.

    Args: id, name? (display_name), role?, case? (mapped_client_code / scope).
    """
    if request.method == "POST":
        p = request.get_json(silent=True) or {}
    else:
        p = request.args
    cid = str(p.get("id") or "").strip()
    name = (p.get("name") or p.get("display_name") or "").strip() or None
    role = (p.get("role") or "").strip() or None
    scope_case = (p.get("case") or "").strip() or None
    if not cid:
        return jsonify({"error": "id required"}), 400
    if role and role not in ("client", "prospect", "counsel", "counterparty", "partner",
                             "operator", "owner", "unknown"):
        return jsonify({"error": f"invalid role: {role}"}), 400

    conn = _db(); conn.autocommit = True
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM channel_users WHERE channel_user_id = %s ORDER BY id DESC LIMIT 1",
                (cid,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return jsonify({"error": f"no user with channel_user_id={cid}"}), 404
    user = dict(row)
    meta = _as_dict(user.get("metadata"))
    hist = list(meta.get("correction_history") or [])
    hist.append({
        "at": datetime.now(timezone.utc).isoformat(),
        "before": {"display_name": user.get("display_name"), "role": user.get("role"),
                   "approved_role": user.get("approved_role"),
                   "mapped_client_code": user.get("mapped_client_code")},
        "patch": {"name": name, "role": role, "case": scope_case},
    })
    meta["correction_history"] = hist[-30:]

    sets = ["metadata = %s::jsonb", "last_seen_at = now()"]
    args = [json.dumps(meta)]
    if name:
        sets.append("display_name = %s")
        args.append(name)
    if role:
        sets.append("role = %s")
        args.append(role)
        if role != "unknown":
            sets.append("approved_role = %s")
            args.append(role)
    if scope_case is not None:
        sets.append("approved_scope_case = %s")
        args.append(scope_case or None)
        sets.append("mapped_client_code = %s")
        args.append(scope_case or None)
    args.append(user["id"])
    cur.execute(f"UPDATE channel_users SET {', '.join(sets)} WHERE id = %s RETURNING *", args)
    fresh = dict(cur.fetchone())
    _send_tg(
        f"✓ Corrected <b>{fresh.get('display_name')}</b> (<code>{cid}</code>) "
        f"role={fresh.get('role')} case={fresh.get('mapped_client_code') or '—'}"
    )
    cur.close(); conn.close()
    return jsonify({"ok": True, "user": {
        "id": fresh["id"], "display_name": fresh.get("display_name"),
        "role": fresh.get("role"), "mapped_client_code": fresh.get("mapped_client_code"),
        "onboarding_state": fresh.get("onboarding_state"),
    }})


@bp.route("/api/approve_user", methods=["POST", "GET"])
def api_approve_user():
    """Approve a pending user. Args: id (channel_user_id), role, case (optional).

    Also works as a re-approve after misregistration correction (same id).
    """
    if request.method == "POST":
        p = request.get_json(silent=True) or {}
        cid = str(p.get("id") or "")
        role = (p.get("role") or "prospect").strip()
        scope_case = (p.get("case") or "").strip() or None
        name = (p.get("name") or "").strip() or None
    else:
        cid = (request.args.get("id") or "").strip()
        role = (request.args.get("role") or "prospect").strip()
        scope_case = (request.args.get("case") or "").strip() or None
        name = (request.args.get("name") or "").strip() or None
    if not cid:
        return jsonify({"error": "id required"}), 400
    if role not in ("client", "prospect", "counsel", "counterparty", "partner"):
        return jsonify({"error": f"invalid role: {role}"}), 400

    conn = _db(); conn.autocommit = True
    cur = conn.cursor(cursor_factory=RealDictCursor)
    # Refuse overwriting operator/owner via approve
    cur.execute("""
        SELECT approved_role, role FROM channel_users WHERE channel_user_id = %s
         ORDER BY id DESC LIMIT 1
    """, (cid,))
    pre = cur.fetchone()
    if pre and (pre.get("approved_role") or pre.get("role") or "").lower() in ("operator", "owner"):
        cur.close(); conn.close()
        return jsonify({"error": "refuse: cannot re-approve operator/owner via this path"}), 403

    cur.execute("""
        UPDATE channel_users
           SET onboarding_state = 'approved',
               onboarding_completed_at = now(),
               role = %s,
               approved_role = %s,
               approved_by = 'jonathan',
               approved_scope_case = %s,
               authorized = true,
               authorized_at = now(),
               authorized_by = 'jonathan',
               mapped_client_code = COALESCE(%s, mapped_client_code),
               display_name = COALESCE(%s, display_name)
         WHERE channel_user_id = %s
         RETURNING *
    """, (role, role, scope_case, scope_case, name, cid))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return jsonify({"error": f"no user with channel_user_id={cid}"}), 404

    # Notify both Jonathan and the user
    user_msg = (
        f"✅ Your access has been approved as <b>{role}</b>"
        + (f" (scoped to case {scope_case})" if scope_case else "") + ".\n\n"
        "You can now message me freely. I'll cite source documents on every "
        "substantive claim and surface anything needing our team's attention."
    )
    _send_tg(user_msg, chat_id=cid)
    _send_tg(f"✓ Approved <b>{row['display_name']}</b> (id=<code>{cid}</code>) as {role}"
             + (f" / scope={scope_case}" if scope_case else ""))
    cur.close(); conn.close()
    return jsonify({"ok": True, "user_id": row["id"], "role": role, "scope": scope_case})


@bp.route("/api/deny_user", methods=["POST", "GET"])
def api_deny_user():
    if request.method == "POST":
        p = request.get_json(silent=True) or {}
        cid = str(p.get("id") or "")
        reason = (p.get("reason") or "").strip()
    else:
        cid = (request.args.get("id") or "").strip()
        reason = (request.args.get("reason") or "").strip()
    if not cid:
        return jsonify({"error": "id required"}), 400

    conn = _db(); conn.autocommit = True
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        UPDATE channel_users
           SET onboarding_state = 'declined',
               onboarding_completed_at = now(),
               approved_by = 'jonathan',
               metadata = jsonb_set(COALESCE(metadata,'{}'::jsonb), '{decline_reason}', to_jsonb(%s))
         WHERE channel_user_id = %s
         RETURNING *
    """, (reason or "no reason given", cid))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return jsonify({"error": f"no user with channel_user_id={cid}"}), 404

    _send_tg(DECLINED_REPLY, chat_id=cid)
    _send_tg(f"✓ Denied <b>{row['display_name']}</b> (id=<code>{cid}</code>) — {reason}")
    cur.close(); conn.close()
    return jsonify({"ok": True, "user_id": row["id"]})


@bp.route("/api/block_user", methods=["POST", "GET"])
def api_block_user():
    cid = str((request.args.get("id") or (request.get_json(silent=True) or {}).get("id") or "")).strip()
    reason = (request.args.get("reason") or (request.get_json(silent=True) or {}).get("reason") or "").strip()
    if not cid:
        return jsonify({"error": "id required"}), 400
    conn = _db(); conn.autocommit = True
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        UPDATE channel_users
           SET onboarding_state = 'blocked',
               onboarding_completed_at = now(),
               authorized = false,
               metadata = jsonb_set(COALESCE(metadata,'{}'::jsonb), '{block_reason}', to_jsonb(%s))
         WHERE channel_user_id = %s
         RETURNING *
    """, (reason or "blocked", cid))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        return jsonify({"error": f"no user with channel_user_id={cid}"}), 404
    _send_tg(f"✓ Blocked <b>{row['display_name']}</b> (id=<code>{cid}</code>) — silent block, no further responses")
    return jsonify({"ok": True})


@bp.route("/api/pending_approvals", methods=["GET", "POST"])
def api_pending_approvals():
    send = request.args.get("send", "1") != "0"
    conn = _db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT cu.id, cu.channel_user_id, cu.display_name, cu.onboarding_state,
               cu.onboarding_responses, cu.first_seen_at, cu.last_seen_at
          FROM channel_users cu
          JOIN channels c ON c.id = cu.channel_id
         WHERE cu.onboarding_state = 'awaiting_jonathan_approval'
         ORDER BY cu.first_seen_at ASC
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    if not rows:
        text = "📭 <b>No pending approvals</b>"
    else:
        lines = [f"📥 <b>{len(rows)} pending approval(s)</b>", ""]
        for r in rows:
            resp = r["onboarding_responses"] or {}
            lines.append(f"<b>{r['display_name']}</b> (<code>{r['channel_user_id']}</code>)")
            lines.append(f"  intent: {resp.get('self_classified_intent', '?')}")
            if resp.get("matter_description"):
                lines.append(f"  matter: {resp['matter_description'][:200]}")
            if resp.get("docket"): lines.append(f"  docket: {resp['docket']}")
            if resp.get("tct"): lines.append(f"  TCT: {resp['tct']}")
            lines.append(f"  /approve {r['channel_user_id']} <role>  |  /deny {r['channel_user_id']} <reason>")
            lines.append("")
        text = "\n".join(lines)
    if send: _send_tg(text)
    return jsonify({"text": text, "count": len(rows)})
