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

SYSTEM = ("You are Leo, the assistant for LandTek, a Philippine land & property services company in "
          "Camarines Norte. Reply briefly and warmly (Taglish is fine). LandTek is NOT a law firm. "
          "State a specific fact (a date, docket, title number, amount, name) ONLY if it appears in "
          "GROUNDED FACTS below, and when you do, cite it inline as doc:<id>. If you lack grounding, "
          "say you'll check with the team — never invent a fact, document, docket, or legal conclusion.")


def _llm(prompt, temp=0.2):
    """Local Ollama, $0 sovereign. Raises on unreachable (caller degrades)."""
    body = {"model": MODEL, "stream": False, "options": {"temperature": temp}, "prompt": prompt}
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read()).get("response", "").strip()


def _grounded_facts(cur, client_code):
    """A5-safe verified facts for the client FAMILY (never another client), with citable doc source_ids."""
    fam = (client_code or "").split("-")[0]
    if not fam:
        return []
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
    facts = _grounded_facts(cur, client_code)
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
    return (f"{SYSTEM}\n\n{who}\n{eq}{rel}{tend}\nGROUNDED FACTS (cite as doc:ID):\n{fblock}\n"
            f"{prop_block}\n"
            f"OPEN ITEMS FOR THIS CLIENT:\n{items}\n\n"
            f"CONVERSATION SO FAR (most recent last — remember it, don't repeat yourself):\n{convo}\n\n"
            f"CURRENT MESSAGE FROM {label}:\n{message}\n\nLeo's reply:")


def generate_reply(cur, channel, channel_user_id, message, client_code, internal_context=None,
                   relationship_profile=None, inbound_msg_id=None, relationship_tending=None):
    """PURE generation for the orchestrator (comm_agent_max): grounded, memory-, equilibrium-, living-
    relationship- AND anticipation-informed reply TEXT — through the answer-gate — with NO role clamp,
    NO A75 projection, NO send. Returns {text, verdict, remediated} or {text:None, error:...}."""
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
    """Send via the channel's OWN existing sender (reuse the bridges — no forks). Returns bool ok."""
    sys.path.insert(0, "/root/landtek/leo_tools")
    import channel_adapters as ca
    if channel == "messenger":
        return bool(ca._messenger_send(recipient, text))
    if channel == "whatsapp":
        return bool(ca._whatsapp_send(recipient, text))
    if channel == "viber":
        return bool(ca._viber_send(recipient, text))
    if channel == "telegram":
        # sovereign Telegram send via the S14-governed sender (sanitize + pace + no-double-tap). Reached
        # only when leo_channel_mode.telegram='headless' (the metered n8n/Anthropic path retired).
        sys.path.insert(0, "/root/landtek/scripts")
        import tg_send
        # override_pacing: this is a DIRECT conversational reply to the user's message (dedup'd one-per-
        # inbound), not a background alert — the S14 no-double-tap must not block a reply he asked for.
        ok, _info = tg_send.send(chat_id=str(recipient), text=text, source="leo", override_pacing=True)
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

    # ── Deterministic title FETCH (same ability as Telegram — scripts/title_fetch) ──
    # Ollama has no tools; never promise "I'll fetch shortly" without links.
    try:
        import title_fetch as tf
        if tf.wants_title_fetch(message or ""):
            pack, _ferr = tf.fetch_title_pack(cur, client, message or "")
            if pack:
                guard_class = og.classify(channel, str(channel_user_id))
                logkw = {**base, "client": client, "cand": pack, "verdict": "title_fetch",
                         "fails": None, "warns": 0, "remed": False, "human": pack,
                         "guard": guard_class}
                if _channel_mode(cur, channel) != "headless":
                    _log(cur, **{**logkw, "action": "shadow_logged"})
                    return {"action": "shadow_logged", "client": client,
                            "would_send_human": pack, "via": "title_fetch"}
                decision, kind, oid = _send_decision(cur, channel, str(channel_user_id), pack)
                if decision == "hold":
                    _log(cur, **{**logkw, "action": "held_for_approval", "order": oid,
                                 "reason": "outward title pack held (A21)"})
                    return {"action": "held_for_approval", "order": oid, "client": client,
                            "would_send_human": pack}
                try:
                    ok = _deliver(channel, str(channel_user_id), pack)
                except Exception as e:
                    ok, kind = False, f"send_error:{type(e).__name__}"
                if ok:
                    _log(cur, **{**logkw, "action": "sent", "reason": f"title_fetch:{kind}"})
                    return {"action": "sent", "via": "title_fetch", "client": client}
                _log(cur, **{**logkw, "action": "send_error", "reason": kind})
                return {"action": "send_error", "reason": kind, "client": client}
    except Exception as e:
        print(f"[leo_service] title_fetch skip: {type(e).__name__}: {e}", flush=True)

    try:
        prompt = _build_prompt(cur, client, message, channel, channel_user_id, inbound_msg_id)
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
