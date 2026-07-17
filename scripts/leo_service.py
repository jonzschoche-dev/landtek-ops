#!/usr/bin/env python3
"""leo_service.py — the headless Leo reply loop (COMM-AGENT-MAX). ONE brain, in Python, that Claude
owns and hardens — replacing the split-brain n8n path (Python half + node half). SHADOW-ONLY until
per-channel cutover: it runs the full governed spine and LOGS the candidate reply + gate verdict +
what it WOULD send, but sends NOTHING to a real user.

Governed spine (reuses existing modules — no forks):
  inbound -> platform_coordinator.client_of (A25 resolve-or-HOLD)
          -> get_recent_context (canonical v_comms_interactions spine, A5 sender-scoped)
          -> local Ollama (qwen2.5:14b, $0 sovereign — never a metered API)
          -> leo_answer_gate.gate (block fabricated cites / ungrounded cascades)
                 on fail -> leo_answer_gate.remediate ($0 grounded-only rewrite, no regenerate loop)
          -> recipient_projection.render_human_reply (A32/A34 human form — no doc#/§ leak)
          -> outward_guard.classify (A21)  [shadow: recorded, not sent]
          -> leo_shadow_replies ledger.

Test surface ONLY (operator + JJ), never the live Telegram/Leo path. Degrade-don't-crash:
no Ollama / no client -> logged + skipped, never a hang.

  python3 scripts/leo_service.py --once        # single shadow pass (systemd timer calls this)
  python3 scripts/leo_service.py --probe "<msg>" --as messenger:37446980471566856   # one synthetic msg
"""
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek"); sys.path.insert(0, "/root/landtek/scripts")
sys.path.insert(0, "/root/landtek/leo_tools")
import platform_coordinator as coord          # client_of (A25 resolve-or-hold)
import get_recent_context as ctx              # corrected spine-based context
import leo_answer_gate as gate_mod            # gate() + remediate()
import recipient_projection as proj           # render_human_reply (A32)
import outward_guard as og                    # classify (A21)
try:
    import relationship_profile as _rpro       # the living per-relationship organ (Increment 2)
except Exception:
    _rpro = None

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://100.117.118.47:11434")
MODEL = os.environ.get("LEO_MODEL", "qwen2.5:14b-instruct")

# In-house test surface only (operator + JJ). Everyone else is ignored until per-channel cutover.
TEST_IDENTITIES = {("messenger", "37446980471566856"), ("telegram", "6513067717")}

SYSTEM = ("You are Leo for LandTek (Philippine land/property ops, Camarines Norte). NOT a law firm. "
          "STYLE: plain natural English (or Filipino only if the user wrote in Filipino). "
          "No Taglish filler, no 'Kamusta/salamat' unless they did first, no pipe characters, "
          "no bullet dumps, no HTML, no Chinese or mixed-script noise. "
          "REASONING EQUILIBRIUM — every reply: (1) use only the brief/facts below, "
          "(2) at most 2 short sentences — never dump lists of facts, "
          "(3) calm and direct, no fake cheerfulness, "
          "(4) one point; add a next step only if it is concrete and grounded. "
          "State a date/docket/title/amount/name ONLY if it appears below. "
          "If ungrounded: say so in one sentence — never invent.")


def _llm(prompt, temp=0.2):
    """Local Ollama, $0 sovereign. Raises on unreachable (caller degrades)."""
    body = {"model": MODEL, "stream": False, "options": {"temperature": temp}, "prompt": prompt}
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read()).get("response", "").strip()


def _grounded_facts(cur, client_code, message=""):
    """A5-safe verified facts for the client FAMILY, RELEVANCE-first then recent.

    Old behavior (ORDER BY updated_at LIMIT 12) made Leo 'unaware' of ARTA/OP
    while 4000+ verified facts existed — the window simply never included them.
    """
    fam = (client_code or "").split("-")[0]
    if not fam:
        return []
    import re
    stop = {"the", "a", "an", "to", "from", "of", "and", "or", "how", "many",
            "what", "when", "where", "is", "are", "was", "were", "have", "has",
            "been", "that", "this", "with", "for", "any", "me", "my", "we", "you",
            "pretty", "good", "cases", "casss"}
    toks = [t for t in re.findall(r"[A-Za-z0-9\-]{3,}", (message or "").lower())
            if t not in stop][:8]
    if toks:
        clauses = " OR ".join(["statement ILIKE %s"] * len(toks))
        sql = f"""
            SELECT statement, source_id, provenance_level FROM (
              SELECT statement, source_id, provenance_level, updated_at
                FROM matter_facts
               WHERE matter_code LIKE %s AND provenance_level='verified'
                 AND source_id ~ '^[0-9]+$'
                 AND ({clauses})
               ORDER BY updated_at DESC LIMIT 12
            ) hit
            UNION ALL
            SELECT statement, source_id, provenance_level FROM (
              SELECT statement, source_id, provenance_level, updated_at
                FROM matter_facts
               WHERE matter_code LIKE %s AND provenance_level='verified'
                 AND source_id ~ '^[0-9]+$'
               ORDER BY updated_at DESC LIMIT 8
            ) rec
            LIMIT 16
        """
        cur.execute(sql, [fam + "%"] + [f"%{t}%" for t in toks] + [fam + "%"])
        rows = cur.fetchall()
        seen, out = set(), []
        for r in rows:
            k = (r.get("statement") or "")[:80]
            if k in seen:
                continue
            seen.add(k)
            out.append(r)
        return out[:16]
    cur.execute("""SELECT statement, source_id, provenance_level
                     FROM matter_facts
                    WHERE matter_code LIKE %s AND provenance_level='verified'
                      AND source_id ~ '^[0-9]+$'
                    ORDER BY updated_at DESC LIMIT 12""", (fam + "%",))
    return cur.fetchall()


def _property_context(cur, client_code, message=""):
    """Inject existing readiness + prep + parties (no new stack). Team/operator path only."""
    if not client_code:
        return ""
    blocks = []
    try:
        # Title mention in message?
        import re
        title_hit = None
        m = re.search(r"\b(T-?[0-9][0-9A-Za-z./-]{2,})\b", message or "")
        if m:
            title_hit = m.group(1)
        if title_hit:
            cur.execute("""SELECT a.title_ref, a.asset_code, a.title_status, a.possession,
                                  r.documents, r.status_axis, r.occupants, r.ownership,
                                  r.title_issues, r.mapping, r.readiness_score, r.weakest_axis,
                                  r.next_prep_action
                             FROM property_assets a
                             LEFT JOIN property_readiness r ON r.asset_code=a.asset_code
                            WHERE a.client_code=%s
                              AND (a.title_ref ILIKE %s OR a.asset_code ILIKE %s)
                            LIMIT 3""", (client_code, f"%{title_hit}%", f"%{title_hit}%"))
        else:
            cur.execute("""SELECT a.title_ref, a.asset_code, a.title_status, a.possession,
                                  r.documents, r.status_axis, r.occupants, r.ownership,
                                  r.title_issues, r.mapping, r.readiness_score, r.weakest_axis,
                                  r.next_prep_action
                             FROM property_assets a
                             LEFT JOIN property_readiness r ON r.asset_code=a.asset_code
                            WHERE a.client_code=%s
                            ORDER BY r.readiness_score ASC NULLS LAST
                            LIMIT 5""", (client_code,))
        rows = cur.fetchall()
        if rows:
            lines = []
            for r in rows:
                tr = r.get("title_ref") or r.get("asset_code")
                sc = r.get("readiness_score")
                scs = f"{float(sc)*100:.0f}%" if sc is not None else "?"
                lines.append(
                    f"- {tr} ({r.get('asset_code')}): score={scs} status={r.get('title_status')} "
                    f"occ={r.get('occupants') or r.get('possession')} own={r.get('ownership')} "
                    f"title_issues={r.get('title_issues')} map={r.get('mapping')} "
                    f"weakest={r.get('weakest_axis')} next={r.get('next_prep_action') or '—'}"
                )
            blocks.append("TITLE READINESS (six axes):\n" + "\n".join(lines))
        cur.execute("""SELECT priority, axis, asset_code, action
                         FROM profitability_prep_moves
                        WHERE status='open' AND client_code=%s
                        ORDER BY priority ASC LIMIT 8""", (client_code,))
        moves = cur.fetchall()
        if moves:
            blocks.append("OPEN PREP MOVES:\n" + "\n".join(
                f"- p{m['priority']} [{m.get('axis') or '-'}] {m['asset_code']}: {m['action'][:120]}"
                for m in moves))
        cur.execute("""SELECT party_name, role, matter_code, side
                         FROM matter_parties
                        WHERE matter_code LIKE %s AND coalesce(party_name,'')<>''
                        ORDER BY matter_code, party_name LIMIT 15""",
                    ((client_code.split("-")[0] if client_code else "") + "%",))
        parties = cur.fetchall()
        if parties:
            blocks.append("PARTIES (buyers/possessors/counsel/etc):\n" + "\n".join(
                f"- {p['party_name']} | {p.get('role') or '?'} | {p.get('matter_code')} | {p.get('side') or ''}"
                for p in parties))
    except Exception:
        return ""
    return ("\n\n" + "\n\n".join(blocks) + "\n") if blocks else ""


def _sender_ident(cur, channel, channel_user_id):
    """Who Leo is talking to — name + role + whether it's the operator (internal). Cognizance, not anonymity."""
    cur.execute("""SELECT cu.display_name, cu.role FROM channel_users cu JOIN channels c ON c.id=cu.channel_id
                    WHERE c.name=%s AND cu.channel_user_id=%s""", (channel, str(channel_user_id)))
    r = cur.fetchone()
    name = (r["display_name"] if r and r["display_name"] else "").strip()
    if not name or name == str(channel_user_id):
        name = ""  # PSID/blank is not a name
    role = (r["role"] if r else "unknown")
    is_op = og.classify(channel, str(channel_user_id)) == "internal"
    return name, role, is_op


def _recent_turns(cur, channel, channel_user_id, before_id=None, limit=10):
    """The last N turns of THIS conversation (memory), sender-scoped, oldest-last, current msg excluded."""
    cur.execute("""SELECT cm.direction, cm.text_content FROM channel_messages cm JOIN channels c ON c.id=cm.channel_id
                    WHERE c.name=%s AND cm.channel_user_id=%s AND coalesce(cm.text_content,'')<>''
                      AND cm.text_content <> '[media]' AND (%s::bigint IS NULL OR cm.id < %s)
                    ORDER BY cm.id DESC LIMIT %s""",
                (channel, str(channel_user_id), before_id, before_id, limit))
    rows = list(reversed(cur.fetchall()))
    if not rows:
        return "(this is the first message)"
    return "\n".join(("Leo: " if r["direction"] == "outbound" else "Them: ")
                     + (r["text_content"] or "")[:220].replace("\n", " ") for r in rows)


def _build_prompt(cur, client_code, message, channel=None, channel_user_id=None, inbound_msg_id=None,
                  internal_context=None, relationship_profile=None, relationship_tending=None):
    facts = _grounded_facts(cur, client_code, message=message or "")
    fblock = "\n".join(f"- (doc:{f['source_id']}) {f['statement']}" for f in facts) or "(none on record yet)"
    c = ctx.recent_context(cur, None, client_code)
    items = "\n".join(f"- {a['description']} (due {a['due_date'] or 'n/a'})"
                      for a in c["open_action_items"]) or "(none)"
    # A76 equilibrium state — the internal recompute informs the reply (surface conflict, don't assert past it)
    eq = ""
    if internal_context and (internal_context.get("contradictions") or internal_context.get("cascades")):
        eq = (f"\nEQUILIBRIUM ALERT: this matter carries {internal_context.get('contradictions', 0)} known "
              f"contradiction(s) and touches {internal_context.get('cascades', 0)} keystone cascade(s) in the "
              "record. If your answer would state a fact that could be contradicted, FLAG the uncertainty "
              "('let me confirm — our records may conflict on that') rather than asserting it.\n")
    # MPRB (matter pre-response brief) — multi-angle internal plane when provided
    mprb = ""
    if internal_context and internal_context.get("mprb_render"):
        mprb = ("\nMATTER PRE-RESPONSE BRIEF (prefer this; verified vs provisional are split):\n"
                f"{internal_context['mprb_render']}\n")
    who, convo, label = "WHO YOU'RE TALKING TO: (unidentified).", "(this is the first message)", "them"
    is_op = False
    if channel and channel_user_id:
        name, role, is_op = _sender_ident(cur, channel, channel_user_id)
        if is_op:
            who = ("WHO YOU'RE TALKING TO: Jonathan — the LandTek OPERATOR and principal. He is your own "
                   "boss/teammate, NOT a client. Greet him by name (Jonathan), speak candidly and directly, "
                   "and you may reference internal specifics (title readiness, prep moves, parties).")
            label = "Jonathan"
        else:
            who = f"WHO YOU'RE TALKING TO: {name or 'a contact'} (role: {role}). Address them by name if known."
            label = name or "them"
        convo = _recent_turns(cur, channel, channel_user_id, before_id=inbound_msg_id)
    # Wire existing readiness/prep/parties into operator (and counsel/client) context — no new stack
    prop_block = _property_context(cur, client_code, message) if (is_op or client_code) else ""
    rel = ""
    if relationship_profile and _rpro is not None:
        try:
            block = _rpro.to_prompt(relationship_profile)
            rel = f"\n{block}\n" if block else ""
        except Exception:
            rel = ""
    tend = ""
    if relationship_tending and _rpro is not None:
        try:
            tblock = _rpro.tending_block(relationship_tending)
            tend = f"\n{tblock}\n" if tblock else ""
        except Exception:
            tend = ""
    return (f"{SYSTEM}\n\n{who}\n{eq}{mprb}{rel}{tend}\nGROUNDED FACTS (cite as doc:ID):\n{fblock}\n"
            f"{prop_block}\n"
            f"OPEN ITEMS FOR THIS CLIENT:\n{items}\n\n"
            f"CONVERSATION SO FAR (most recent last — remember it, don't repeat yourself):\n{convo}\n\n"
            f"CURRENT MESSAGE FROM {label}:\n{message}\n\nLeo's reply:")


def generate_reply(cur, channel, channel_user_id, message, client_code, internal_context=None,
                   relationship_profile=None, inbound_msg_id=None, relationship_tending=None):
    """PURE generation for orchestrators — but inquiries MUST hit corpus first.

    For is_inquiry(message): only try_purpose_route (tables + reasoning). Never free LLM.
    For non-inquiry (greetings / vault narrative): grounded LLM still allowed.
    Returns {text, verdict, remediated, via?} or {text:None, error:...}.
    """
    # ── HARD GATE: corpus/reasoning before any freestyle model text ──
    if client_code and is_inquiry(message or ""):
        try:
            route = try_purpose_route(cur, client_code, message or "")
            if route and route.get("text"):
                return {
                    "text": route["text"],
                    "verdict": "stack",
                    "remediated": False,
                    "via": route.get("via") or "purpose_route",
                    "preformed": True,
                }
        except Exception as e:
            print(f"[leo_service] generate_reply stack gate: {e}", flush=True)
        return {
            "text": STACK_CLOSED_TEXT,
            "verdict": "stack_closed",
            "remediated": False,
            "via": "stack_closed",
            "preformed": True,
        }

    prompt = _build_prompt(cur, client_code, message, channel, channel_user_id, inbound_msg_id,
                           internal_context, relationship_profile, relationship_tending)
    try:
        candidate = _llm(prompt)
    except Exception as e:
        return {"text": None, "error": f"ollama_unreachable:{type(e).__name__}"}
    try:
        res = gate_mod.gate(cur, candidate)
        text, remediated = candidate, False
        if res.get("verdict") == "fail":
            text = gate_mod.remediate(cur, candidate, res)   # $0 grounded-only rewrite
            remediated = True
        return {"text": text, "verdict": res.get("verdict"), "remediated": remediated}
    except Exception as e:
        return {"text": candidate, "verdict": "gate_error", "remediated": False, "error": str(e)[:120]}


def _log(cur, **kw):
    kw.setdefault("order", None)
    cur.execute("""INSERT INTO leo_shadow_replies
        (inbound_msg_id, channel, channel_user_id, client_code, candidate_internal, verdict, fails,
         warns_n, remediated, would_send_human, guard_class, model, action, reason, order_id)
        VALUES (%(msg)s,%(channel)s,%(uid)s,%(client)s,%(cand)s,%(verdict)s,%(fails)s,%(warns)s,
                %(remed)s,%(human)s,%(guard)s,%(model)s,%(action)s,%(reason)s,%(order)s)
        ON CONFLICT (inbound_msg_id) WHERE inbound_msg_id IS NOT NULL DO NOTHING""", kw)


def _channel_mode(cur, channel):
    """The per-channel cutover switch: 'headless' (leo_service owns replies) or 'n8n' (shadow only)."""
    cur.execute("SELECT mode FROM leo_channel_mode WHERE channel=%s", (channel,))
    r = cur.fetchone()
    return (r["mode"] if r else "n8n")


def _deliver(channel, recipient, text):
    """Send via the channel's OWN existing sender (reuse the bridges — no forks). Returns bool ok.

    A85 emission parity: operator-facing free text uses one dose (S14 280). Preformed
    packs are already short-by-construction under EMISSION_CAP. Messenger had no S14
    cap before — that was the verbosity parity break.
    """
    sys.path.insert(0, "/root/landtek/scripts")
    sys.path.insert(0, "/root/landtek/leo_tools")
    import channel_adapters as ca
    # One dose authority for internal operator channels
    try:
        if og.classify(channel, str(recipient)) == "internal":
            from distill import strip_fluff, prefer_conclusion, EMISSION_CAP
            text = strip_fluff(text or "")
            if len(text) > EMISSION_CAP:
                text = prefer_conclusion(text, EMISSION_CAP)
    except Exception:
        pass
    if channel == "messenger":
        return bool(ca._messenger_send(recipient, text))
    if channel == "whatsapp":
        return bool(ca._whatsapp_send(recipient, text))
    if channel == "viber":
        return bool(ca._viber_send(recipient, text))
    if channel == "telegram":
        import tg_send
        # override_pacing: direct conversational reply; S14 sanitize still applies for Jonathan
        ok, _info = tg_send.send(
            chat_id=str(recipient), text=text, source="leo",
            override_pacing=True, human_readable=True)
        return bool(ok)
    return False


def _send_decision(cur, channel, recipient, reply):
    """FAIL-CLOSED send gate (independent of the global guard mode). Returns (decision, kind, order_id):
      internal (operator) -> send · outward WITH a consumed human approval -> send ·
      outward WITHOUT approval -> HOLD + enqueue an outward_action for T3 human certification (A21)."""
    target = f"{channel}:{recipient}"
    chash = hashlib.sha256((reply or "").encode("utf-8")).hexdigest()[:16]
    if og.classify(channel, recipient) == "internal":
        return ("send", "internal", None)
    pc = cur.connection.cursor()  # outward_guard helpers use positional row[0] — give them a plain cursor
    try:
        approved = og._find_approval(pc, target, chash)
        if approved:
            pc.execute("UPDATE work_orders SET audit = audit || %s::jsonb WHERE id=%s",
                       (json.dumps([{"note": "consumed", "by": "leo_service"}]), approved))
            return ("send", "outward_approved", approved)
        oid = og._auto_enqueue(pc, target, chash, "leo_service", reply)
        return ("hold", "outward_unapproved", oid)
    finally:
        pc.close()


def deliver_approved(cur):
    """Deliver replies whose outward_action order a human has now certified (status='done', unconsumed).
    This is where a human approval turns into an actual send — the one human action in the loop."""
    cur.execute("""SELECT s.id, s.channel, s.channel_user_id, s.would_send_human, s.order_id
                     FROM leo_shadow_replies s JOIN work_orders w ON w.id = s.order_id
                    WHERE s.action='held_for_approval' AND w.status='done'
                      AND NOT (w.audit::text LIKE %s)""", ('%"consumed"%',))
    done = 0
    for r in cur.fetchall():
        try:
            ok = _deliver(r["channel"], r["channel_user_id"], r["would_send_human"])
        except Exception:
            ok = False
        if ok:
            cur.execute("UPDATE work_orders SET audit = audit || %s::jsonb WHERE id=%s",
                        (json.dumps([{"note": "consumed", "by": "leo_service_deliver"}]), r["order_id"]))
            cur.execute("UPDATE leo_shadow_replies SET action='sent' WHERE id=%s", (r["id"],))
            done += 1
    if done:
        print(f"[leo_service] delivered {done} human-approved reply(ies)")


def is_inquiry(message: str) -> bool:
    """True when free LLM is FORBIDDEN and corpus/reasoning stack is mandatory.

    Social acknowledgements and vault narrative are False (other handlers may run).
    Anything that looks like a property/legal/factual question is True.
    """
    t = (message or "").strip().lower()
    if not t or len(t) < 2:
        return False
    # Pure social / ack — not inquiries
    if re.fullmatch(
        r"(hi|hello|hey|thanks|thank you|salamat|ok|okay|sige|ty|thx|noted|"
        r"good morning|good afternoon|good evening|magandang\s+\w+|"
        r"got it|copy|yes|no|yeah|yep|sure)[\s!.?]*",
        t,
    ):
        return False
    if "?" in (message or ""):
        return True
    starters = (
        "what ", "what's ", "whats ", "when ", "where ", "who ", "why ", "how ",
        "which ", "is ", "are ", "was ", "were ", "do ", "does ", "did ",
        "can ", "could ", "should ", "would ", "tell me", "show me", "list ",
        "find ", "fetch ", "give me", "get me", "pull ", "explain ", "summarize ",
        "status of", "history of", "history ",
    )
    if any(t.startswith(s) for s in starters):
        return True
    markers = (
        "history", "historical", "title chain", "mother title", "parent title",
        "docket", "case no", "case number", "mro", "ctn", "tct", "oct", "e-title",
        "e title", "petition", "appeal", "manifest", "deadline", "originally",
        "came from", "come from", "status of", "who owns", "registered",
        "cancelled", "transfer", "readiness", "op ", " arta", "balane", "title ",
    )
    if any(m in t for m in markers):
        return True
    # Bare title / year / ref tokens ⇒ treat as factual lookup
    if re.search(r"\b(T-?\d{3,7}|\d{5,7}|20\d{2}-\d{3,4}|MRO-\d|\d{6}-MRO-\d+)\b",
                 message or "", re.I):
        return True
    return False


STACK_CLOSED_TEXT = (
    "I do not have a grounded answer from the corpus stack for that yet "
    "(title / fact / brief / law layers returned no safe hit). "
    "I will not invent. Needs human review if this is urgent."
)


# field kinds an asked docket/CTN-style identifier may legitimately match (NEVER date/amount —
# a year like 2026 must not "resolve" against date fields and defeat the gate)
_IDENT_FIELD_KINDS = ("ctn", "docket", "tct", "oct", "e_title", "tax_dec", "arp", "doc_ref", "mro_ref")


def _asked_identifiers(message):
    """Identifiers the user EXPLICITLY asked about — deterministic, keyword-anchored (a bare number
    in prose is not an identifier ask; 'docket 99999' / 'TCT T-99999' / a full CTN is)."""
    t = message or ""
    ids = set()
    for m in re.finditer(r"(?i)\b(?:docket|ctn|case(?:\s*no\.?)?|arp)\s*(?:no\.?|number|#)?\s*[:\-]?\s*"
                         r"((?:[A-Z]{1,4}-)?[0-9][0-9-]{2,18})", t):
        ids.add(("docket", m.group(1).strip("-")))
    for m in re.finditer(r"(?i)\b(?:tct|oct|title)\s*(?:no\.?)?\s*[:\-]?\s*(T-?[0-9][0-9A-Za-z./-]{2,})", t):
        ids.add(("title", m.group(1)))
    for m in re.finditer(r"\b(T-[0-9]{4,6})\b", t):
        ids.add(("title", m.group(1)))
    for m in re.finditer(r"\b(?:SL-)?(\d{4}-\d{4}-\d{4})\b", t):
        ids.add(("docket", m.group(1)))
    return ids


def _identifier_known(cur, kind, val):
    """Does this asked identifier exist ANYWHERE in the typed corpus? Cheap EXISTS probes only."""
    v = (val or "").strip().upper()
    if not v:
        return True                                    # nothing checkable → never block on it
    try:
        if kind == "title":
            tnum = v if v.startswith("T-") else ("T-" + v.lstrip("T").lstrip("-"))
            cur.execute("SELECT 1 FROM titles WHERE upper(tct_number)=%s "
                        "UNION SELECT 1 FROM document_fields WHERE field_kind IN ('tct','oct','e_title') "
                        "AND upper(value_norm) LIKE %s LIMIT 1", (tnum, "%" + tnum.lstrip("T-") + "%"))
            return cur.fetchone() is not None
        cur.execute("SELECT 1 FROM fact_fields WHERE field_kind = ANY(%s) "
                    "AND (upper(value_norm)=%s OR upper(value_norm) LIKE %s) "
                    "UNION SELECT 1 FROM document_fields WHERE field_kind = ANY(%s) "
                    "AND (upper(value_norm)=%s OR upper(value_norm) LIKE %s) "
                    "UNION SELECT 1 FROM matters WHERE upper(matter_code) LIKE %s LIMIT 1",
                    (list(_IDENT_FIELD_KINDS), v, "%" + v, list(_IDENT_FIELD_KINDS), v, "%" + v, "%" + v))
        return cur.fetchone() is not None
    except Exception:
        return True                                    # probe failure must never fabricate "unknown"


def _unknown_identifier_gate(cur, message):
    """FAIL-CLOSED on unmatched identifiers: if the ask names identifier(s) and NONE resolve against
    the typed corpus, say so — never route to the nearest-match answer (the 'docket 99999 answered
    with ARTA 0690' failure, 2026-07-18). Mixed known+unknown passes through (the specific answerers
    handle their own scope)."""
    asked = _asked_identifiers(message)
    if not asked:
        return None
    known, unknown = [], []
    for kind, val in asked:
        (known if _identifier_known(cur, kind, val) else unknown).append(val)
    if unknown and not known:
        vals = ", ".join(sorted(set(unknown)))
        return {"text": f"No record of {vals} in the corpus — that identifier does not match any "
                        "docket, CTN, or title on file. If it's new, send the document and I'll "
                        "ingest it.",
                "via": "unknown_identifier", "preformed": True, "purpose": "unknown_identifier"}
    return None


def try_purpose_route(cur, client_code, message):
    """Corpus + reasoning FIRST. Every inquiry is stack-bound.

    Returns None only for non-inquiries (chitchat / vault narrative).
    For inquiries: always returns a pack — either stack hit or fail-closed.
    Free LLM must never invent property/legal facts (T-52540 PA-T disaster).
    """
    if not client_code or not (message or "").strip():
        return None

    # Identifier fail-closed gate FIRST: an ask about an identifier the corpus doesn't hold gets an
    # honest "no record", not the nearest-match answer from any downstream route.
    gate = _unknown_identifier_gate(cur, message)
    if gate:
        return gate

    inquiry = is_inquiry(message)

    def _emit(text, via, purpose=None):
        if not text:
            return None
        # Short by construction only — strip fluff, do not truncate away the answer.
        # Cap warning if answerer exceeded EMISSION_CAP (280 / S14).
        # Exception: title_history is table-backed chain evidence — never prefer_conclusion
        # a dense fact pack into a useless one-liner (that path caused PA-T invent).
        try:
            from distill import strip_fluff, prefer_conclusion, EMISSION_CAP
            text = strip_fluff(text)
            hist_cap = 900 if purpose in ("title_history", "title_fetch", "inquiry_stack",
                                          "stack_closed", "stack_hit", "pass_to_human") else EMISSION_CAP
            if len(text) > hist_cap:
                print(f"[leo_service] route over dose {len(text)}>{hist_cap} via={via}",
                      flush=True)
                if purpose in ("title_history", "inquiry_stack", "stack_hit", "pass_to_human"):
                    text = text[: hist_cap - 1] + "…"
                else:
                    text = prefer_conclusion(text, hist_cap)
        except Exception:
            pass
        return {"text": text, "via": via, "preformed": True, "purpose": purpose}

    try:
        import title_fetch as tf
        # Title CHAIN / origin first — must never fall through to free LLM invent.
        if tf.wants_title_history(message):
            hist, _herr = tf.fetch_title_history(cur, client_code, message)
            if hist:
                return _emit(hist, "title_history", "title_history")
        if tf.wants_title_fetch(message):
            pack, _ferr = tf.fetch_title_pack(cur, client_code, message)
            if pack:
                return _emit(pack, "title_fetch", "title_fetch")
    except Exception as e:
        print(f"[leo_service] title_fetch route: {type(e).__name__}: {e}", flush=True)

    # TOOL ROUTES (deploy_966): the retired per-channel tool-loop's capabilities, as governed spine
    # routes — vault queries · doc lookup/search — one brain for every communication tool, all
    # channels, deterministic, read-only, ≤280. Writes stay with the explicit vault command handler.
    try:
        import tool_routes as tr
        hit = tr.try_tool_route(cur, client_code, message)
        if hit and hit.get("text"):
            return _emit(hit["text"], hit.get("via") or "tool", hit.get("purpose"))
    except Exception as e:
        print(f"[leo_service] tool route: {type(e).__name__}: {e}", flush=True)

    # PURPOSE-SPECIFIC first (membership semantics): a classified ask (OP docket · ARTA→OP count ·
    # inventory) is answered by its dedicated answerer BEFORE the generic inquiry_stack aggregate —
    # the aggregate counts MENTIONS across a matter's docs; these answer MEMBERSHIP (what the
    # instrument itself carries). Root cause of the 1210 CTN overcount, fixed 2026-07-18.
    try:
        import corpus_answer as ca
        if ca.classify_purpose(message):
            pack, purpose = ca.try_corpus_answer(cur, client_code, message)
            if pack and purpose and not str(purpose).startswith("error"):
                return _emit(pack, f"corpus_answer:{purpose}", purpose)
    except Exception as e:
        print(f"[leo_service] corpus_answer priority route: {type(e).__name__}: {e}", flush=True)

    # Agentic stack: ALWAYS for inquiries; also try on borderline factual text
    try:
        import inquiry_stack as ist
        pack = ist.try_inquiry_stack(
            cur, client_code, message, go=True, force=inquiry,
        )
        if pack and pack.get("text"):
            return _emit(
                pack["text"],
                pack.get("via") or "inquiry_stack",
                pack.get("purpose") or "inquiry_stack",
            )
    except Exception as e:
        print(f"[leo_service] inquiry_stack route: {type(e).__name__}: {e}", flush=True)

    try:
        import corpus_answer as ca
        pack, purpose = ca.try_corpus_answer(cur, client_code, message)
        if pack and purpose and not str(purpose).startswith("error"):
            return _emit(pack, f"corpus_answer:{purpose}", purpose)
    except Exception as e:
        print(f"[leo_service] corpus_answer route: {type(e).__name__}: {e}", flush=True)

    # MPRB structured answer (matter multi-angle) — preformed when SQL concludes
    try:
        import matter_brief as mb
        hit = mb.try_mprb_route(cur, client_code, message)
        if hit and hit.get("text"):
            return _emit(hit["text"], hit.get("via") or "mprb", hit.get("purpose"))
    except Exception as e:
        print(f"[leo_service] mprb route: {type(e).__name__}: {e}", flush=True)

    # HARD GATE: inquiries never fall through to free LLM
    if inquiry:
        print(f"[leo_service] STACK_CLOSED inquiry (no corpus hit): {(message or '')[:80]!r}",
              flush=True)
        return _emit(STACK_CLOSED_TEXT, "stack_closed", "stack_closed")
    return None


def _deliver_preformed(cur, base, channel, channel_user_id, client, pack, via):
    """Send/hold a preformed pack (same gates as process router branch)."""
    guard_class = og.classify(channel, str(channel_user_id))
    logkw = {**base, "client": client, "cand": pack, "verdict": via or "corpus",
             "fails": None, "warns": 0, "remed": False, "human": pack,
             "guard": guard_class}
    if _channel_mode(cur, channel) != "headless":
        _log(cur, **{**logkw, "action": "shadow_logged"})
        return {"action": "shadow_logged", "client": client,
                "would_send_human": pack, "via": via, "preformed": True}
    decision, kind, oid = _send_decision(cur, channel, str(channel_user_id), pack)
    if decision == "hold":
        _log(cur, **{**logkw, "action": "held_for_approval", "order": oid,
                     "reason": f"outward {via} held (A21)"})
        return {"action": "held_for_approval", "order": oid, "client": client,
                "would_send_human": pack, "via": via, "preformed": True}
    try:
        ok = _deliver(channel, str(channel_user_id), pack)
    except Exception as e:
        ok, kind = False, f"send_error:{type(e).__name__}"
    if ok:
        _log(cur, **{**logkw, "action": "sent", "reason": f"{via}:{kind}"})
        return {"action": "sent", "via": via, "client": client, "preformed": True}
    _log(cur, **{**logkw, "action": "send_error", "reason": kind})
    return {"action": "send_error", "reason": kind, "client": client, "via": via,
            "preformed": True}


def process(cur, channel, channel_user_id, message, inbound_msg_id=None):
    """Run the full spine for one message. SHADOW: logs, never sends. Returns the ledger dict."""
    base = dict(msg=inbound_msg_id, channel=channel, uid=str(channel_user_id), model=MODEL,
                cand=None, verdict=None, fails=None, warns=0, remed=False, human=None,
                guard=None, reason=None, order=None)
    # A25 resolve-or-HOLD: never answer with a guessed client's context
    client = coord.client_of(cur, channel, channel_user_id)
    if not client:
        _log(cur, **{**base, "client": None, "action": "held",
                     "reason": "unresolved_client (A25): identity not bound to a client_code"})
        return {"action": "held", "client": None}

    # ── A85 purpose router (shared with CAM / TG) ──
    # Inquiries ALWAYS resolve here (stack hit or STACK_CLOSED). Free LLM never invents facts.
    try:
        route = try_purpose_route(cur, client, message or "")
        if route and route.get("text"):
            return _deliver_preformed(
                cur, base, channel, channel_user_id, client,
                route["text"], route.get("via") or "purpose_route")
    except Exception as e:
        print(f"[leo_service] purpose_route skip: {type(e).__name__}: {e}", flush=True)

    # Second hard gate (belt+suspenders): never free-LLM an inquiry even if route returned None
    if is_inquiry(message or ""):
        return _deliver_preformed(
            cur, base, channel, channel_user_id, client,
            STACK_CLOSED_TEXT, "stack_closed")

    # MPRB prompt block for LLM path (angles selected; not a full dump) — chitchat / narrative only
    mprb_block = ""
    try:
        import matter_brief as mb
        brief = mb.assemble_for_message(cur, client, message or "")
        if brief:
            mprb_block = mb.render(brief) or ""
    except Exception as e:
        print(f"[leo_service] mprb assemble: {type(e).__name__}: {e}", flush=True)

    try:
        prompt = _build_prompt(cur, client, message, channel, channel_user_id, inbound_msg_id)
        if mprb_block:
            prompt = prompt.replace(
                "GROUNDED FACTS (cite as doc:ID):",
                f"MATTER PRE-RESPONSE BRIEF (internal plane — prefer this over thin fact window):\n"
                f"{mprb_block}\n\nGROUNDED FACTS (cite as doc:ID):",
                1,
            )
        candidate = _llm(prompt)
    except Exception as e:
        _log(cur, **{**base, "client": client, "action": "ollama_unreachable",
                     "reason": f"{type(e).__name__}: {str(e)[:160]}"})
        return {"action": "ollama_unreachable", "client": client}
    try:
        res = gate_mod.gate(cur, candidate)
        remediated = False
        to_send = candidate
        if res["verdict"] == "fail":
            to_send = gate_mod.remediate(cur, candidate, res)   # $0 grounded-only rewrite
            remediated = True
        human = proj.render_human_reply(to_send)                # A32 human form (no doc#/§ leak)
        # Do NOT post-truncate LLM prose here (kills conclusions). Brevity is system-prompt
        # + short-by-construction routers. S14 applies on Telegram send for Jonathan.
        try:
            from distill import strip_fluff, prefer_conclusion, EMISSION_CAP
            human = strip_fluff(human)
            if len(human) > EMISSION_CAP:
                human = prefer_conclusion(human, EMISSION_CAP)
        except Exception:
            pass
        guard_class = og.classify(channel, str(channel_user_id))  # A21 classification
        logkw = {**base, "client": client, "cand": candidate, "verdict": res["verdict"],
                 "fails": psycopg2.extras.Json(res["fails"]), "warns": res["n_warns"],
                 "remed": remediated, "human": human, "guard": guard_class}
        # per-channel cutover switch: 'n8n' => shadow (log, no send); 'headless' => leo_service delivers
        if _channel_mode(cur, channel) != "headless":
            _log(cur, **{**logkw, "action": "shadow_logged"})
            return {"action": "shadow_logged", "client": client, "verdict": res["verdict"],
                    "remediated": remediated, "would_send_human": human, "guard_class": guard_class}
        # LIVE channel — fail-closed send gate
        decision, kind, oid = _send_decision(cur, channel, str(channel_user_id), human)
        if decision == "hold":
            _log(cur, **{**logkw, "action": "held_for_approval", "order": oid,
                         "reason": "outward reply held for human certification (A21/T3)"})
            return {"action": "held_for_approval", "order": oid, "client": client,
                    "would_send_human": human}
        try:
            ok = _deliver(channel, str(channel_user_id), human)
        except Exception as e:
            ok, kind = False, f"send_error:{type(e).__name__}"
        if ok:
            _log(cur, **{**logkw, "action": "sent", "reason": kind})
            return {"action": "sent", "via": kind, "client": client}
        # send failed -> degrade: enqueue + hold, never a silent loss
        _pc = cur.connection.cursor()
        try:
            hoid = og._auto_enqueue(_pc, f"{channel}:{channel_user_id}",
                                    hashlib.sha256(human.encode("utf-8")).hexdigest()[:16], "leo_service", human)
        finally:
            _pc.close()
        _log(cur, **{**logkw, "action": "send_error", "order": hoid, "reason": kind})
        return {"action": "send_error", "reason": kind, "order": hoid, "client": client}
    except Exception as e:
        _log(cur, **{**base, "client": client, "action": "error", "reason": f"{type(e).__name__}: {str(e)[:160]}"})
        return {"action": "error", "reason": str(e)[:160]}


def run_once(cur):
    """Deliver any human-approved held replies, then process new test-surface inbound."""
    deliver_approved(cur)   # turn certified outward_action orders into actual sends
    ids = tuple(TEST_IDENTITIES)
    cur.execute("""
        SELECT cm.id, c.name AS channel, cm.channel_user_id, cm.text_content
          FROM channel_messages cm JOIN channels c ON c.id = cm.channel_id
          LEFT JOIN leo_shadow_replies s ON s.inbound_msg_id = cm.id
         WHERE cm.direction='inbound' AND s.id IS NULL
           AND (c.name, cm.channel_user_id) IN %s
           AND coalesce(cm.text_content,'') <> '' AND cm.text_content <> '[media]'
         ORDER BY cm.id ASC LIMIT 50
    """, (ids,))
    rows = cur.fetchall()
    n = 0
    for r in rows:
        process(cur, r["channel"], r["channel_user_id"], r["text_content"], inbound_msg_id=r["id"])
        n += 1
    print(f"[leo_service] shadow pass: processed {n} new inbound from the test surface")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--probe", help="run one synthetic message through the spine (shadow)")
    ap.add_argument("--as", dest="ident", default="messenger:37446980471566856",
                    help="channel:channel_user_id for --probe")
    a = ap.parse_args()
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if a.probe:
            ch, _, uid = a.ident.partition(":")
            print(json.dumps(process(cur, ch, uid, a.probe), indent=2, default=str))
        else:
            run_once(cur)
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
