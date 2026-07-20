#!/usr/bin/env python3
"""test_emission_failclose.py — R5 emission-plane truth floor (deploy_989).

The three invariants an A79 enforce-flip / n8n activation would rely on, each negative-tested so a
regression bites:

  (1) CURSOR-PARITY (T2): apply_comms_role_clamp records the SAME would_clamp for a plain cursor and a
      RealDictCursor on the same row. Bites on the dict(zip(keys, dict_row)) garbage that made would_clamp
      always-False for every RealDictCursor caller (leo_instant / comm_agent_soak / comm_agent_max) —
      i.e. the shadow audit lying for exactly the counterparty rows an enforce-flip cares about.

  (2) FAIL-CLOSED (T1): in enforce (block) mode a guard/gate error on an OUTWARD send yields HOLD, never
      a raw send (A21/A43). Two-sided: the SAME forced error in SHADOW mode must still ALLOW (shadow is
      structurally non-blocking) and an INTERNAL recipient must still ALLOW on error (offline-sovereignty).

  (3) SIM-GUARD + OUTWARD FLOOR: every Telegram send node in the live "Leos Workflow" carries the
      999→'0' sim-guard, and the code emission plane still routes through outward_guard + the fail-closed
      _send_decision (they cannot be silently unwired).
"""
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "leo_tools"))
from _harness import run, TruthFailure
import outward_guard as OG

_WF_ID = "vSDQv1vfn6627bnA"
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── (1) cursor-parity ────────────────────────────────────────────────────────────────────────────────
def cursor_parity_would_clamp(cur):
    """apply_comms_role_clamp must record identical would_clamp for a RealDictCursor (harness cur) and a
    plain cursor on the SAME counterparty row. On the T2 bug the RealDict caller logs 'clear' (garbage
    policy) while the plain caller logs 'would_clamp' — this discriminates them."""
    marker = "r5_failclose_" + uuid.uuid4().hex[:12]
    ctx = {"contains_facts": True, "source": marker}
    # RealDictCursor path (the harness cur is a RealDictCursor)
    OG.apply_comms_role_clamp("counterparty", {"text": "x"}, ctx, cur=cur)
    # plain-cursor path on the same connection
    plain = cur.connection.cursor()
    try:
        OG.apply_comms_role_clamp("counterparty", {"text": "x"}, ctx, cur=plain)
    finally:
        plain.close()
    cur.execute("SELECT result FROM channel_audit WHERE event_type='role_clamp_shadow' "
                "AND payload->>'source' = %s ORDER BY id", (marker,))
    results = [r["result"] for r in cur.fetchall()]
    if len(results) != 2:
        raise TruthFailure(f"expected 2 role_clamp_shadow rows for the marker, got {len(results)}.")
    if len(set(results)) != 1:
        raise TruthFailure(
            f"cursor-parity BROKEN: plain vs RealDict cursor disagree on would_clamp {results} — the "
            f"RealDictCursor policy is self-referential garbage (T2 dict(zip) bug); the shadow audit lies.")
    if results[0] != "would_clamp":
        raise TruthFailure(
            f"counterparty+facts must clamp; both cursors logged {results[0]!r} — the clamp is not firing.")


# ── (2) fail-closed on a guard error in enforce mode ───────────────────────────────────────────────────
def _forced_error_guard(mode, recipient):
    """Run guard() with _classify_cur forced to raise (a gate error) and the mode pinned, returning the
    decision. Restores the module afterward. Used for both the positive and the negative legs."""
    orig_classify, orig_mode, orig_safe = OG._classify_cur, OG._mode, OG._safe_mode
    try:
        OG._classify_cur = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("forced gate error"))
        OG._mode = lambda *a, **k: mode          # body reads the pinned mode (before it throws)
        OG._safe_mode = lambda: mode             # the except path confirms the pinned mode
        dec, info = OG.guard("telegram", recipient, source="r5_test", preview="secret facts")
        return dec, info
    finally:
        OG._classify_cur, OG._mode, OG._safe_mode = orig_classify, orig_mode, orig_safe


def failclosed_outward_block(cur):
    # POSITIVE: enforce mode + gate error + OUTWARD recipient → HOLD (never a raw send).
    dec, info = _forced_error_guard("block", "700700700")
    if dec != "hold":
        raise TruthFailure(
            f"guard FAILED OPEN: block-mode gate error on an outward send returned {dec!r} (info={info}) — "
            f"raw unapproved text would dispatch. A21/A43 require HOLD.")


def failclosed_negative_shadow_allows(cur):
    # NEGATIVE leg A: the SAME forced error in SHADOW mode must ALLOW (shadow never blocks a real send).
    # If the fix over-corrected to always-hold, this bites.
    dec, _ = _forced_error_guard("shadow", "700700700")
    if dec != "allow":
        raise TruthFailure(
            f"shadow-mode gate error returned {dec!r} — shadow must be structurally non-blocking (allow).")


def failclosed_negative_internal_allows(cur):
    # NEGATIVE leg B: even in block mode, an INTERNAL recipient (operator chat) must ALLOW on error —
    # offline-sovereignty: the operator's own alerts are never held. If the fix blocked internal, this bites.
    dec, _ = _forced_error_guard("block", "6513067717")
    if dec != "allow":
        raise TruthFailure(
            f"block-mode gate error on the operator's own chat returned {dec!r} — offline-sovereignty "
            f"requires the operator/sim floor to always pass (allow).")


# ── (3) sim-guard + outward floor ──────────────────────────────────────────────────────────────────────
def sim_guard_on_every_telegram_send_node(cur):
    cur.execute("SELECT nodes FROM workflow_entity WHERE id=%s", (_WF_ID,))
    r = cur.fetchone()
    if not r:
        raise TruthFailure(f"'Leos Workflow' ({_WF_ID}) not found — the emission topology floor cannot verify.")
    nodes = r["nodes"]
    if isinstance(nodes, str):
        nodes = json.loads(nodes)
    missing = []
    for n in nodes:
        if (n.get("type") or "").lower() != "n8n-nodes-base.telegram":
            continue  # telegramTrigger / other node types are not text-send nodes
        chat = str((n.get("parameters") or {}).get("chatId") or "")
        if not chat:
            continue  # file/get ops have no chatId send target
        if "999" not in chat or '"0"' not in chat:
            missing.append(n.get("name"))
    if missing:
        raise TruthFailure(
            f"Telegram send node(s) missing the 999→'0' sim-guard: {missing} — a sim message could reach a "
            f"real chat_id.")


def code_emission_plane_still_governed(cur):
    """The code plane cannot be silently unwired: tg_send routes through outward_guard, leo_service's live
    send is gated by the fail-closed _send_decision, and outward_guard retains BOTH the isinstance cursor-
    parity guard (T2) and the fail-closed block-mode error branch (T1)."""
    def _read(rel):
        with open(os.path.join(_REPO, rel), encoding="utf-8") as fh:
            return fh.read()

    tg = _read("scripts/tg_send.py")
    if "outward_guard.guard(" not in tg:
        raise TruthFailure("tg_send.py no longer routes through outward_guard.guard() — A21 chokepoint unwired.")

    ls = _read("scripts/leo_service.py")
    if "_send_decision(" not in ls or "FAIL-CLOSED send gate" not in ls:
        raise TruthFailure("leo_service.py lost the fail-closed _send_decision gate on its live send path.")

    og = _read("scripts/outward_guard.py")
    if "isinstance(r, dict)" not in og:
        raise TruthFailure("outward_guard.apply_comms_role_clamp lost the isinstance cursor-parity guard (T2).")
    # the fail-closed block-mode error branch must be present in guard()'s except
    if 'eff_mode == "block"' not in og or 'fail-closed hold' not in og:
        raise TruthFailure("outward_guard.guard() lost its fail-closed block-mode error branch (T1).")


TESTS = [
    ("emission_failclose.cursor_parity_would_clamp", cursor_parity_would_clamp),
    ("emission_failclose.failclosed_outward_block", failclosed_outward_block),
    ("emission_failclose.failclosed_negative_shadow_allows", failclosed_negative_shadow_allows),
    ("emission_failclose.failclosed_negative_internal_allows", failclosed_negative_internal_allows),
    ("emission_failclose.sim_guard_on_every_telegram_send_node", sim_guard_on_every_telegram_send_node),
    ("emission_failclose.code_emission_plane_still_governed", code_emission_plane_still_governed),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
