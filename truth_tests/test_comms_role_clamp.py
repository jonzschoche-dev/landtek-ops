#!/usr/bin/env python3
"""test_comms_role_clamp.py — A79 role axis (deploy_879), SHADOW invariants.

  (a) comms_role_policy is seeded with exactly the 6 canonical roles; refuse-roles are dose 0.
  (b) NEGATIVE-BITE: a counterparty output that carries facts WOULD clamp (never auto-anything) — and a
      counterparty WITHOUT facts still clamps (refuse is unconditional).
  (c) a permitted recipient (client, full disclosure) does NOT false-clamp on facts.
  (d) an unknown/unmapped role falls to the most-restrictive safe default (fail-closed).
  (e) SHADOW never blocks: apply_comms_role_clamp returns the output object UNCHANGED for every role.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from _harness import run, TruthFailure
import outward_guard as OG


def _policy(cur, role):
    cur.execute("SELECT disclosure_ceiling, gate_default, dose_ceiling, cadence, projection_profile "
                "FROM v_comms_role_policy WHERE role=%s", (role,))
    r = cur.fetchone()
    if not r:
        raise TruthFailure(f"comms_role_policy has no row for '{role}'.")
    return dict(r)  # RealDictRow → dict keyed by column name


def policy_seeded_six(cur):
    cur.execute("SELECT count(*) AS n FROM v_comms_role_policy")
    n = cur.fetchone()["n"]
    if n != 6:
        raise TruthFailure(f"expected 6 canonical roles in comms_role_policy, got {n}.")
    cur.execute("SELECT role FROM v_comms_role_policy WHERE gate_default='refuse' AND dose_ceiling<>0")
    bad = cur.fetchall()
    if bad:
        raise TruthFailure(f"refuse-role with nonzero dose_ceiling: {bad} — refuse must be dose 0.")


def counterparty_facts_bites(cur):
    cp = _policy(cur, "counterparty")
    fires, reason = OG._clamp_decision(cp, {"contains_facts": True})
    if not fires:
        raise TruthFailure("counterparty + facts did NOT clamp — an adversary could be auto-disclosed to.")
    # refuse is unconditional: even with no facts, a counterparty auto-output clamps
    fires_nofacts, _ = OG._clamp_decision(cp, {"contains_facts": False})
    if not fires_nofacts:
        raise TruthFailure("counterparty (no facts) did NOT clamp — refuse must be unconditional.")


def client_facts_pass(cur):
    cl = _policy(cur, "client")
    fires, _ = OG._clamp_decision(cl, {"contains_facts": True})
    if fires:
        raise TruthFailure("client + facts falsely clamped — a full-disclosure client may receive facts.")


def safe_default_on_unknown(cur):
    fires, _ = OG._clamp_decision(OG._SAFE_DEFAULT_POLICY, {"contains_facts": True})
    if not fires:
        raise TruthFailure("safe default did not clamp on facts — unmapped roles must be fail-closed.")
    out = {"text": "hello"}
    ret = OG.apply_comms_role_clamp("no_such_role_xyz", out, {"contains_facts": True}, cur=cur)
    if ret is not out:
        raise TruthFailure("apply_comms_role_clamp altered the output for an unknown role — shadow must not.")


def shadow_never_blocks(cur):
    out = {"text": "sensitive strategy"}
    ret = OG.apply_comms_role_clamp("counterparty", out, {"contains_facts": True}, cur=cur)
    if ret is not out:
        raise TruthFailure("SHADOW clamp altered a counterparty output — shadow must block/alter NOTHING.")


TESTS = [
    ("comms_role_clamp.policy_seeded_six", policy_seeded_six),
    ("comms_role_clamp.counterparty_facts_bites", counterparty_facts_bites),
    ("comms_role_clamp.client_facts_pass", client_facts_pass),
    ("comms_role_clamp.safe_default_on_unknown", safe_default_on_unknown),
    ("comms_role_clamp.shadow_never_blocks", shadow_never_blocks),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
