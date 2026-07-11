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


def _build_prompt(cur, client_code, message):
    facts = _grounded_facts(cur, client_code)
    fblock = "\n".join(f"- (doc:{f['source_id']}) {f['statement']}" for f in facts) or "(none on record yet)"
    c = ctx.recent_context(cur, None, client_code)  # client-level open items; sender thread added by caller
    items = "\n".join(f"- {a['description']} (due {a['due_date'] or 'n/a'})"
                      for a in c["open_action_items"]) or "(none)"
    return (f"{SYSTEM}\n\nGROUNDED FACTS (cite as doc:ID):\n{fblock}\n\n"
            f"OPEN ITEMS FOR THIS CLIENT:\n{items}\n\nCLIENT MESSAGE:\n{message}\n\nLeo's reply:")


def _log(cur, **kw):
    cur.execute("""INSERT INTO leo_shadow_replies
        (inbound_msg_id, channel, channel_user_id, client_code, candidate_internal, verdict, fails,
         warns_n, remediated, would_send_human, guard_class, model, action, reason)
        VALUES (%(msg)s,%(channel)s,%(uid)s,%(client)s,%(cand)s,%(verdict)s,%(fails)s,%(warns)s,
                %(remed)s,%(human)s,%(guard)s,%(model)s,%(action)s,%(reason)s)
        ON CONFLICT (inbound_msg_id) WHERE inbound_msg_id IS NOT NULL DO NOTHING""", kw)


def process(cur, channel, channel_user_id, message, inbound_msg_id=None):
    """Run the full spine for one message. SHADOW: logs, never sends. Returns the ledger dict."""
    base = dict(msg=inbound_msg_id, channel=channel, uid=str(channel_user_id), model=MODEL,
                cand=None, verdict=None, fails=None, warns=0, remed=False, human=None,
                guard=None, reason=None)
    # A25 resolve-or-HOLD: never answer with a guessed client's context
    client = coord.client_of(cur, channel, channel_user_id)
    if not client:
        _log(cur, **{**base, "client": None, "action": "held",
                     "reason": "unresolved_client (A25): identity not bound to a client_code"})
        return {"action": "held", "client": None}
    try:
        prompt = _build_prompt(cur, client, message)
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
        guard_class = og.classify(channel, str(channel_user_id))  # A21 (recorded; nothing sent in shadow)
        _log(cur, **{**base, "client": client, "cand": candidate, "verdict": res["verdict"],
                     "fails": psycopg2.extras.Json(res["fails"]), "warns": res["n_warns"],
                     "remed": remediated, "human": human, "guard": guard_class,
                     "action": "shadow_logged"})
        return {"action": "shadow_logged", "client": client, "verdict": res["verdict"],
                "remediated": remediated, "would_send_human": human, "guard_class": guard_class}
    except Exception as e:
        _log(cur, **{**base, "client": client, "action": "error", "reason": f"{type(e).__name__}: {str(e)[:160]}"})
        return {"action": "error", "reason": str(e)[:160]}


def run_once(cur):
    """Shadow every new inbound from the test surface that hasn't been processed yet."""
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
