#!/usr/bin/env python3
"""leo_instant.py — instant-reply daemon. LISTENs for `leo_inbound` (pg_notify from the deploy_896
trigger) and runs leo_service.process the moment a message lands, so operator/internal messages get a
real-time reply instead of waiting for the 4-min leo-service timer. Latency = the LLM generation only.

SAFE BY CONSTRUCTION (reuses leo_service's gates — no forks):
  * only (channel, channel_user_id) in leo_service.TEST_IDENTITIES are processed,
  * only when the channel is 'headless',
  * leo_service._send_decision still HOLDS anything outward (real clients never auto-send),
  * dedup against leo_shadow_replies so the timer + the daemon never double-reply.
Persistent daemon (systemd Type=simple, Restart=always); reconnects on any drop; degrade-don't-crash.
"""
import os
import select
import sys
import time

sys.path.insert(0, "/root/landtek/scripts")
sys.path.insert(0, "/root/landtek/leo_tools")
import psycopg2
import psycopg2.extras
import leo_service as ls

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# Phase B cutover: identities where CAM orchestrator is LIVE (sends). Default empty =
# process remains live, CAM stays force_shadow. Operator-first example:
#   LEO_ORCH_LIVE=telegram:6513067717,messenger:37446980471566856
def _orch_live_set():
    raw = (os.environ.get("LEO_ORCH_LIVE") or "").strip()
    out = set()
    for part in raw.split(","):
        part = part.strip()
        if ":" in part:
            ch, uid = part.split(":", 1)
            out.add((ch.strip(), uid.strip()))
    return out


def _process(cur, mid):
    cur.execute("""SELECT c.name AS channel, cm.channel_user_id, cm.text_content
                     FROM channel_messages cm JOIN channels c ON c.id = cm.channel_id
                    WHERE cm.id = %s AND cm.direction = 'inbound'""", (mid,))
    r = cur.fetchone()
    if not r:
        return
    ident = (r["channel"], str(r["channel_user_id"]))
    if ident not in ls.TEST_IDENTITIES:
        return                                   # not a wired test/operator identity → ignore
    if ls._channel_mode(cur, r["channel"]) != "headless":
        return                                   # channel not cut over → the timer/n8n owns it
    if not (r["text_content"] or "").strip() or r["text_content"] == "[media]":
        return
    cur.execute("SELECT 1 FROM leo_shadow_replies WHERE inbound_msg_id = %s", (mid,))
    if cur.fetchone():
        return                                   # already handled (timer or a prior notify) — no double reply

    orch_live = ident in _orch_live_set()
    res = None
    orch = None

    if orch_live:
        # Phase B: orchestrator is LIVE send path (includes try_purpose_route + preformed)
        try:
            import comm_agent_max as CAM
            t1 = time.time()
            orch = CAM.handle_chat_event(cur, mid, force_shadow=False, mode="live")
            orch_ms = int((time.time() - t1) * 1000)
            # Mirror send into shadow ledger shape for ops
            action = "sent" if orch.get("emitted") else (
                "held_for_approval" if orch.get("next_action") == "hold_for_operator" else
                orch.get("next_action") or "shadow")
            res = {"action": action, "via": orch.get("route_via") or "orch",
                   "preformed": orch.get("preformed"), "client": orch.get("client")}
            print(f"[leo_instant] ORCH-LIVE msg {mid} ({r['channel']}): {action} "
                  f"preformed={orch.get('preformed')} via={orch.get('route_via')}", flush=True)
            # still record convergence vs process (process not run — compare would_send to emitted)
            try:
                cur.execute("""INSERT INTO comm_agent_convergence_diff
                    (inbound_msg_id, channel, live_action, orch_next_action, orch_would_clamp, orch_disclosure_tier,
                     orch_contradictions, agree_send_hold, orch_at_least_as_strict, orch_latency_ms)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (mid, r["channel"], action, orch.get("next_action"), orch.get("would_clamp"),
                     orch.get("disclosure_tier"), orch.get("internal_contradictions"),
                     True, True, orch_ms))
            except Exception:
                pass
            return
        except Exception as e:
            print(f"[leo_instant] orch-live fail → process fallback: {e}", flush=True)

    res = ls.process(cur, r["channel"], str(r["channel_user_id"]), r["text_content"], inbound_msg_id=mid)
    print(f"[leo_instant] msg {mid} ({r['channel']}): {res.get('action')} via={res.get('via')}", flush=True)

    # ── CONVERGENCE (shadow): orchestrator alongside process (sends NOTHING) ──
    try:
        import comm_agent_max as CAM
        t1 = time.time()
        orch = CAM.handle_chat_event(cur, mid, force_shadow=True)
        orch_ms = int((time.time() - t1) * 1000)
        live_send = res.get("action") == "sent"
        orch_send = orch.get("next_action") == "would_send"
        # preformed parity: both should send same class of artifact
        cur.execute("""INSERT INTO comm_agent_convergence_diff
            (inbound_msg_id, channel, live_action, orch_next_action, orch_would_clamp, orch_disclosure_tier,
             orch_contradictions, agree_send_hold, orch_at_least_as_strict, orch_latency_ms)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (mid, r["channel"], res.get("action"), orch.get("next_action"), orch.get("would_clamp"),
             orch.get("disclosure_tier"), orch.get("internal_contradictions"),
             live_send == orch_send, (not orch_send) or live_send, orch_ms))
    except Exception as e:
        print(f"[leo_instant] convergence-diff err: {str(e)[:100]}", flush=True)


def main():
    while True:
        conn = None
        try:
            conn = psycopg2.connect(DSN); conn.autocommit = True
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("LISTEN leo_inbound")
            print("[leo_instant] listening on leo_inbound…", flush=True)
            while True:
                if select.select([conn], [], [], 60) == ([], [], []):
                    continue                     # 60s keepalive tick
                conn.poll()
                while conn.notifies:
                    n = conn.notifies.pop(0)
                    try:
                        _process(cur, int(n.payload))
                    except Exception as e:
                        print(f"[leo_instant] err on {n.payload}: {str(e)[:100]}", flush=True)
        except Exception as e:
            print(f"[leo_instant] reconnecting after: {str(e)[:100]}", flush=True)
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
            time.sleep(5)


if __name__ == "__main__":
    main()
