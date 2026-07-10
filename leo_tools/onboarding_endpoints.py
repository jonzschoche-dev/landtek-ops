"""Onboarding state machine for unknown senders (deploy_116).

Endpoints:
  POST /api/onboard          — process inbound message in onboarding flow
  POST /api/approve_user     — Jonathan approves an awaiting user
  POST /api/deny_user        — Jonathan denies an awaiting user
  GET  /api/pending_approvals — list awaiting_jonathan_approval users

When the n8n workflow detects a non-approved sender, it POSTs to /api/onboard
with {channel='telegram', channel_user_id=..., message=...}. The endpoint
runs the state machine and returns {reply: <text to send>, state_after, escalate}.
"""
import os
import sys
import json
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor

PG_DSN = os.getenv("LEO_TOOLS_PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN_TG_ID = "6513067717"

bp = Blueprint("onboarding_endpoints", __name__)


def _db():
    return psycopg2.connect(PG_DSN)


def _get_or_create_user(cur, channel_name, channel_user_id, display_name=None, username=None):
    cur.execute("""
        SELECT cu.* FROM channel_users cu
          JOIN channels c ON c.id = cu.channel_id
         WHERE c.name = %s AND cu.channel_user_id = %s
    """, (channel_name, str(channel_user_id)))
    row = cur.fetchone()
    if row:
        return dict(row), False
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
    "Thanks, {name}. I've forwarded your message to <b>Jonathan Zschoche</b> "
    "for review. He'll reach out shortly to confirm next steps.\n\n"
    "In the meantime, feel free to send any documents or context you'd like him to see — "
    "I'll capture them but won't act on them until he approves engagement."
)

DECLINED_REPLY = (
    "Thank you for reaching out. Jonathan has reviewed your message and determined "
    "LandTek is unable to assist at this time. If circumstances change, please contact us through "
    "our office directly."
)

LIMITED_REPLY_PROSPECT = (
    "While we await Jonathan's confirmation, here's what I can share:\n"
    "• <b>LandTek</b> is a Philippine land and property services company — title verification, "
    "property records and documentation, estate/property support.\n"
    "• LandTek is not a law firm; litigation is handled by engaged counsel — "
    "Atty. Bonifacio T. Barandon Jr. (Daet, Camarines Norte) leads litigation matters we support.\n"
    "• Jonathan Zschoche handles intake. He'll be in touch within 1-2 business days.\n\n"
    "If you'd like, send any property documents (TCT, tax dec, deed) — I'll log them safely "
    "for his review."
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
    if not channel_user_id:
        return jsonify({"error": "channel_user_id required"}), 400

    conn = _db(); conn.autocommit = True
    cur = conn.cursor(cursor_factory=RealDictCursor)
    user, created = _get_or_create_user(cur, channel, channel_user_id, display_name, username)
    state = user["onboarding_state"]
    responses = user["onboarding_responses"] or {}

    cur.execute("""
        INSERT INTO channel_messages
          (channel_id, channel_user_id, direction, text_content, sent_at, status, metadata)
        VALUES ((SELECT id FROM channels WHERE name=%s), %s, 'inbound', %s, now(), 'received',
                jsonb_build_object('onboarding_state_at_receipt', %s))
    """, (channel, channel_user_id, message, state))

    reply = None
    next_state = state
    escalate = False

    if state == "approved":
        # Shouldn't reach here, but bail to AI Agent
        cur.close(); conn.close()
        return jsonify({"reply": None, "state_after": "approved", "escalate": False,
                        "passthrough": True, "role": user.get("approved_role")})

    elif state == "declined":
        reply = DECLINED_REPLY
        next_state = "declined"  # absorbing state

    elif state == "blocked":
        # Silent block
        cur.close(); conn.close()
        return jsonify({"reply": None, "state_after": "blocked", "passthrough": False})

    elif state == "awaiting_intro":
        if created:
            # First-ever message; respond with INTRO and stay in awaiting_intro
            reply = INTRO_REPLY
            next_state = "awaiting_intro"
            responses["first_message"] = message
        else:
            # User replied with their intro
            responses["intro_text"] = message
            # Try to detect name from message
            import re
            m = re.search(r"(?:I'?m|my name is|ako (?:po )?si|ako ay|si)\s+([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){0,3})",
                          message, re.IGNORECASE)
            inferred_name = m.group(1).strip() if m else (display_name or "")
            if inferred_name and inferred_name.lower() != "leo":
                responses["inferred_name"] = inferred_name
                cur.execute("UPDATE channel_users SET display_name = %s WHERE id = %s",
                            (inferred_name, user["id"]))
            # Try to detect role intent
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
        # Heuristic: look for docket / TCT / property indicators
        import re
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
        # Concat to responses
        prior = responses.get("messages_while_waiting", [])
        prior.append({"text": message[:1000], "at": datetime.now(timezone.utc).isoformat()})
        responses["messages_while_waiting"] = prior[-10:]  # cap
        if (responses.get("self_classified_intent") or "").startswith("prospect"):
            reply = LIMITED_REPLY_PROSPECT
        else:
            reply = "Atty. Jonathan is still reviewing — I'll relay any documents you send. He'll respond directly."

    # Persist state + responses
    cur.execute("""
        UPDATE channel_users
           SET onboarding_state = %s,
               onboarding_responses = %s::jsonb,
               last_seen_at = now()
         WHERE id = %s
    """, (next_state, json.dumps(responses), user["id"]))

    # Log outbound reply
    if reply:
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
        "user_id": user["id"],
    })


@bp.route("/api/approve_user", methods=["POST", "GET"])
def api_approve_user():
    """Approve a pending user. Args: id (channel_user_id), role, case (optional)."""
    if request.method == "POST":
        p = request.get_json(silent=True) or {}
        cid = str(p.get("id") or "")
        role = (p.get("role") or "prospect").strip()
        scope_case = (p.get("case") or "").strip() or None
    else:
        cid = (request.args.get("id") or "").strip()
        role = (request.args.get("role") or "prospect").strip()
        scope_case = (request.args.get("case") or "").strip() or None
    if not cid:
        return jsonify({"error": "id required"}), 400
    if role not in ("client", "prospect", "counsel", "counterparty", "partner"):
        return jsonify({"error": f"invalid role: {role}"}), 400

    conn = _db(); conn.autocommit = True
    cur = conn.cursor(cursor_factory=RealDictCursor)
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
               mapped_client_code = COALESCE(mapped_client_code, %s)
         WHERE channel_user_id = %s
         RETURNING *
    """, (role, role, scope_case, scope_case, cid))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return jsonify({"error": f"no user with channel_user_id={cid}"}), 404

    # Notify both Jonathan and the user
    user_msg = (
        f"✅ Atty. Jonathan has approved your access as <b>{role}</b>"
        + (f" (scoped to case {scope_case})" if scope_case else "") + ".\n\n"
        "You can now message me freely. I'll cite source documents on every "
        "substantive claim and surface anything needing his attention."
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
