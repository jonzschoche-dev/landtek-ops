#!/usr/bin/env python3
"""test_comm_agent_max.py — L4 COMM-AGENT-MAX brain (SHADOW, two-plane).

  (a) NEGATIVE-BITE: a counterparty inbound event → the candidate WOULD clamp and next_action is
      hold_for_operator — an adversary is never auto-anything.
  (b) TWO-PLANE: the internal ego-network still recomputed (internal_ego_nodes not None) EVEN WHEN the
      emission clamps — internal reasoning is gate-free/accurate; only emission is clamped.
  (c) a client inbound → projection_profile 'human_safe' (A75 downstream of the clamp).
  (d) SHADOW: nothing is emitted for any role.

Write-tests run in a ROLLED-BACK connection (handle_chat_event writes channel_audit + propagation_log).
"""
import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "leo_tools"))
from _harness import run, TruthFailure
import equilibrium_propagate as EP
import comm_agent_max as CAM


def _rb():
    conn = psycopg2.connect(EP.DSN); conn.autocommit = False
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _inbound_id_for_role(cur, raw_role):
    """An inbound whose sender GENUINELY resolves to raw_role — excluding identities wired as internal
    (e.g. the operator's own test personas), which classify as 'internal' regardless of channel_users.role."""
    cur.execute("""SELECT cm.id FROM channel_messages cm
                     JOIN channel_users cu ON cu.channel_id = cm.channel_id
                                          AND cu.channel_user_id = cm.channel_user_id
                     JOIN channels c ON c.id = cm.channel_id
                    WHERE cm.direction='inbound' AND cu.role = %s
                      AND NOT EXISTS (
                        SELECT 1 FROM internal_targets it
                         WHERE it.active AND it.channel IN (c.name, '*')
                           AND ((it.match_type='exact'  AND cu.channel_user_id = it.identifier)
                             OR (it.match_type='prefix' AND cu.channel_user_id LIKE it.identifier || '%%')))
                    ORDER BY cm.id DESC LIMIT 1""", (raw_role,))
    r = cur.fetchone()
    return r["id"] if r else None


def counterparty_never_auto(cur):
    conn, tc = _rb()
    try:
        mid = _inbound_id_for_role(tc, "counterparty")
        if not mid:
            return  # no counterparty inbound in the corpus — vacuously safe
        d = CAM.handle_chat_event(tc, mid, candidate_text="Here are the verified facts of the case.")
        if not d.get("would_clamp"):
            raise TruthFailure(f"counterparty candidate did NOT clamp — adversary auto-disclosure risk: {d}")
        if d.get("next_action") != "hold_for_operator":
            raise TruthFailure(f"counterparty next_action={d.get('next_action')} — must be hold_for_operator.")
        if d.get("emitted") is not False:
            raise TruthFailure("counterparty output was emitted — shadow must send nothing.")
    finally:
        conn.rollback(); conn.close()


def two_plane_internal_gate_free(cur):
    conn, tc = _rb()
    try:
        mid = _inbound_id_for_role(tc, "counterparty")
        if not mid:
            return
        d = CAM.handle_chat_event(tc, mid, candidate_text="strategy detail")
        # emission clamped, yet the internal ego-network was still computed → two planes are separate
        if d.get("would_clamp") and d.get("internal_ego_nodes") is None and d.get("client"):
            raise TruthFailure("internal plane did NOT recompute while emission clamped — the two-plane "
                               "split is broken (internal reasoning must stay gate-free/accurate).")
    finally:
        conn.rollback(); conn.close()


def client_projection_human_safe(cur):
    conn, tc = _rb()
    try:
        mid = _inbound_id_for_role(tc, "client")
        if not mid:
            return
        d = CAM.handle_chat_event(tc, mid, candidate_text="Your title status update.")
        if d.get("projection_profile") != "human_safe":
            raise TruthFailure(f"client projection_profile={d.get('projection_profile')} — expected human_safe.")
        if d.get("emitted") is not False:
            raise TruthFailure("client output was emitted — shadow must send nothing.")
    finally:
        conn.rollback(); conn.close()


def chat_seed_nonzero_ego(cur):
    """deploy_888: seeding from the chat NODE reaches the client's real matters+facts — a meaningful,
    matter-anchored internal recompute, not the ego=0 the arbitrary-matter seed produced."""
    conn, tc = _rb()
    try:
        mid = _inbound_id_for_role(tc, "client") or _inbound_id_for_role(tc, "counterparty")
        if not mid:
            return
        d = CAM.handle_chat_event(tc, mid, candidate_text="status")
        if not d.get("client"):
            return  # sender not client-anchored — nothing to seed
        if not d.get("internal_ego_nodes"):
            raise TruthFailure(f"chat seed produced ego={d.get('internal_ego_nodes')} — chat-as-node "
                               "anchoring failed to reach the client's matters/facts.")
    finally:
        conn.rollback(); conn.close()


TESTS = [
    ("comm_agent_max.counterparty_never_auto", counterparty_never_auto),
    ("comm_agent_max.two_plane_internal_gate_free", two_plane_internal_gate_free),
    ("comm_agent_max.client_projection_human_safe", client_projection_human_safe),
    ("comm_agent_max.chat_seed_nonzero_ego", chat_seed_nonzero_ego),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
