#!/usr/bin/env python3
"""test_channel_inputs.py — behavioral matrix for the two LIVE inbound channels (telegram + messenger).

'Are the channels performing appropriately?' — proven end-to-end against the REAL pipeline
(platform_coordinator → leo_service.process → answer-gate → outward_guard → send-decision), plus the
living-profile + two-plane convergence layers. Every check runs on an ISOLATED, rolled-back connection,
and the operator auto-send path is exercised with leo_service._deliver MONKEYPATCHED to a capture — so
no message ever reaches a real Telegram chat or Messenger PSID.

Matrix (each runs per channel unless noted):
  1. operator line resolves to its client (A25) AND classifies internal (A21) AND is on the test surface
  2. both channels are 'headless' (the cutover premise these tests assume)
  3. an unknown/unbound sender is HELD, never answered (A25)
  4. an OUTWARD (non-operator) reply HOLDS for human approval + enqueues an outward_action (A21)
  5. the operator's reply AUTO-SENDS (internal) — full live spine, wire monkeypatched, nothing really sent
  6. the generated reply is non-empty, gate-clean, and carries NO fabricated doc: cite (anti-hallucination)
  7. the living profile GROWS from a channel exchange and captures signals
  8. two-plane convergence: on real traffic the orchestrator was NEVER weaker than the live path
  9. sim range (999000*) can NEVER be classified outward (telegram safety floor)
"""
import os
import re
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/root/landtek/scripts")
sys.path.insert(0, "/root/landtek/leo_tools")
sys.path.insert(0, "/root/landtek")
from _harness import run, TruthFailure, DSN
import leo_service as LS
import platform_coordinator as coord
import outward_guard as og
import relationship_profile as RPRO
import comm_agent_max as CAM

CHANNELS = [("telegram", "6513067717"), ("messenger", "37446980471566856")]
EXPECT_CLIENT = "MWK-001"
# genuinely-external ids: not registered, not the operator, not the 999000* sim prefix → classify OUTWARD
EXTERNAL = {"telegram": "70000009", "messenger": "100000000000009"}


def _rb():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


# ── 1. resolution + classification + test-surface membership ──────────────────────────────────────
def operator_lines_resolve_internal_and_on_surface(cur):
    for ch, uid in CHANNELS:
        client = coord.client_of(cur, ch, uid)
        if client != EXPECT_CLIENT:
            raise TruthFailure(f"[{ch}] operator {uid} resolved to {client!r}, expected {EXPECT_CLIENT} (A25).")
        if og.classify(ch, uid) != "internal":
            raise TruthFailure(f"[{ch}] operator {uid} did NOT classify internal — would lose the auto-send lane (A21).")
        if (ch, uid) not in LS.TEST_IDENTITIES:
            raise TruthFailure(f"[{ch}] operator {uid} is not on the test surface — leo_instant would ignore it.")


# ── 2. cutover premise ─────────────────────────────────────────────────────────────────────────────
def both_channels_headless(cur):
    for ch, _ in CHANNELS:
        mode = LS._channel_mode(cur, ch)
        if mode != "headless":
            raise TruthFailure(f"[{ch}] channel mode is {mode!r}, not 'headless' — the sovereign path is not live.")


# ── 3. unknown sender held (A25) ─────────────────────────────────────────────────────────────────────
def unknown_sender_is_held(cur):
    conn, tc = _rb()
    try:
        for ch, _ in CHANNELS:
            fake = "88" + ch[:1] + "0000000001"
            res = LS.process(tc, ch, fake, "hi, who is this?", inbound_msg_id=None)
            if res.get("action") != "held" or res.get("client") is not None:
                raise TruthFailure(f"[{ch}] unbound sender {fake} was not HELD (got {res}) — A25 resolve-or-hold breach.")
    finally:
        conn.rollback(); conn.close()


# ── 4. outward reply holds for approval (A21) ───────────────────────────────────────────────────────
def outward_reply_holds_for_approval(cur):
    conn, tc = _rb()
    try:
        for ch, _ in CHANNELS:
            ext = EXTERNAL[ch]
            if og.classify(ch, ext) != "outward":
                raise TruthFailure(f"[{ch}] external id {ext} did not classify outward — bad test fixture.")
            decision, kind, oid = LS._send_decision(tc, ch, ext, "PROBE-" + os.urandom(6).hex())
            if decision != "hold" or not oid:
                raise TruthFailure(f"[{ch}] outward reply resolved to {decision!r} (order={oid}) — must HOLD (A21).")
            tc.execute("SELECT kind FROM work_orders WHERE id=%s", (oid,))
            w = tc.fetchone()
            if not w or w["kind"] != "outward_action":
                raise TruthFailure(f"[{ch}] held outward reply did not enqueue an outward_action work order.")
    finally:
        conn.rollback(); conn.close()


# ── 5. operator auto-send — full live spine, wire monkeypatched (nothing really sent) ────────────────
def operator_reply_auto_sends_without_touching_the_wire(cur):
    conn, tc = _rb()
    captured = []
    orig_deliver = LS._deliver
    LS._deliver = lambda channel, recipient, text: (captured.append((channel, recipient, text)) or True)
    try:
        for ch, uid in CHANNELS:
            res = LS.process(tc, ch, uid, "Kumusta Leo, may update ba tayo?", inbound_msg_id=None)
            if res.get("action") == "ollama_unreachable":
                print(f"  [skip:{ch}] ollama unreachable — auto-send path not exercised", flush=True)
                continue
            if res.get("action") != "sent":
                raise TruthFailure(f"[{ch}] operator reply did not auto-send (got {res.get('action')!r}) — "
                                   "the internal auto-send lane is broken.")
            # Post-convergence (deploy_962): an operator INQUIRY is legitimately claimed by the
            # purpose router (stack/preformed via) and still auto-sends on the internal lane. What
            # matters is WHO may auto-send (internal only) — the via label may be the stack's.
            via = res.get("via") or ""
            if via != "internal" and not any(
                    via.startswith(p) for p in ("inquiry_stack", "corpus_answer", "title_",
                                                "tool:", "mprb", "stack", "purpose_route",
                                                "unknown_identifier")):
                raise TruthFailure(f"[{ch}] operator send routed via {via!r} — neither the internal "
                                   "lane nor a recognized governed stack route.")
        if captured and any(not (c[2] or "").strip() for c in captured):
            raise TruthFailure(f"[{ch}] auto-sent an EMPTY reply to the operator: {captured}")
    finally:
        LS._deliver = orig_deliver
        conn.rollback(); conn.close()


# ── 6. generated reply is grounded + carries no fabricated cite (anti-hallucination heartbeat) ───────
def generated_reply_is_grounded_and_clean(cur):
    conn, tc = _rb()
    try:
        facts = LS._grounded_facts(tc, EXPECT_CLIENT)
        valid_ids = {str(f["source_id"]) for f in facts}
        for ch, uid in CHANNELS:
            gen = LS.generate_reply(tc, ch, uid, "Ano po ang pinakabagong update sa titulo natin?", EXPECT_CLIENT)
            if gen.get("text") is None:
                print(f"  [skip:{ch}] ollama unreachable — generation not exercised", flush=True)
                continue
            text = gen["text"]
            if not text.strip():
                raise TruthFailure(f"[{ch}] generation returned an empty reply.")
            if gen.get("verdict") == "fail" and not gen.get("remediated"):
                raise TruthFailure(f"[{ch}] a FAIL-verdict reply was returned un-remediated: {text[:120]!r}")
            cited = set(re.findall(r"doc:(\d+)", text))
            bad = cited - valid_ids
            if bad:
                raise TruthFailure(f"[{ch}] reply cites doc(s) {bad} NOT in this client's grounded facts "
                                   f"— fabricated citation (hallucination): {text[:160]!r}")
    finally:
        conn.rollback(); conn.close()


# ── 7. living profile grows from a channel exchange ─────────────────────────────────────────────────
def living_profile_grows_per_channel(cur):
    conn, tc = _rb()
    try:
        for ch, uid in CHANNELS:
            p = RPRO.observe(tc, ch, uid, EXPECT_CLIENT, None, -1,
                             "Salamat po, ano na yung update sa TCT at deadline sa filing?", {})
            if (p.get("_exchanges") or 0) < 1:
                raise TruthFailure(f"[{ch}] living profile did not grow after a verified exchange.")
            if not (p.get("themes") or p.get("lang")):
                raise TruthFailure(f"[{ch}] profile captured no signals from the exchange: {p}")
    finally:
        conn.rollback(); conn.close()


# ── 8. two-plane convergence: the orchestrator was never weaker than the live path on real traffic ──
def convergence_orchestrator_never_weaker(cur):
    cur.execute("""SELECT count(*) AS n, coalesce(sum((orch_at_least_as_strict=false)::int),0) AS bad
                     FROM comm_agent_convergence_diff WHERE created_at > now() - interval '30 days'""")
    r = cur.fetchone()
    if (r["n"] or 0) == 0:
        print("  [note] no convergence-diff rows in 30d — orchestrator strictness unobserved", flush=True)
        return
    if r["bad"]:
        raise TruthFailure(f"{r['bad']}/{r['n']} convergence rows show the shadow orchestrator WEAKER than the "
                           "live path (orch_at_least_as_strict=false) — two-plane safety breach.")


# ── 9. sim range can never be treated as an outward client (telegram safety floor) ──────────────────
def sim_range_never_classified_outward(cur):
    if og.classify("telegram", "999000001") != "internal":
        raise TruthFailure("a 999000* sim sender did NOT classify internal — a sim message could be treated "
                           "as an outward client (S1/S4 floor breach).")


TESTS = [
    ("channels.operator_lines_resolve_internal_on_surface", operator_lines_resolve_internal_and_on_surface),
    ("channels.both_headless", both_channels_headless),
    ("channels.unknown_sender_held_a25", unknown_sender_is_held),
    ("channels.outward_reply_holds_a21", outward_reply_holds_for_approval),
    ("channels.operator_auto_send_no_wire", operator_reply_auto_sends_without_touching_the_wire),
    ("channels.generated_reply_grounded_no_fabricated_cite", generated_reply_is_grounded_and_clean),
    ("channels.living_profile_grows", living_profile_grows_per_channel),
    ("channels.convergence_orchestrator_never_weaker", convergence_orchestrator_never_weaker),
    ("channels.sim_range_never_outward", sim_range_never_classified_outward),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
