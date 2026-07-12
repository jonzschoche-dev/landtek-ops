#!/usr/bin/env python3
"""comm_agent_max.py — L4, the COMM-AGENT-MAX brain (SHADOW). The sentient web's output layer.

One event in → the two-plane pipeline out:
  INTERNAL plane (gate-free, maximal accuracy):  resolve sender → propagate() the client's ego-network
    (A76, deploy_882; per-hop A5 guard inside it). Nothing is clamped here — internal reasoning is hot.
  EMISSION plane (the ONLY clamped surface): classify the candidate's disclosure → apply the A79 role
    clamp at the single gate (outward_guard) → apply A75 projection PER THE CLAMP'S directive → decide the
    next action from the role's gate_default → shadow-log the entire hair-split decision.

SENDS NOTHING. Every candidate is role-clamped, dose-aware, projection-shaped by construction. Callable
from any adapter and from the future reactive P2 path. Flip to enforce = act on `next_action` (one place).

  from comm_agent_max import handle_chat_event
  handle_chat_event(cur, <channel_message_id>[, candidate_text=<leo_service reply>])
"""
import os
import sys
import json

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, _SCRIPTS)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import outward_guard as OG            # scripts/ — the gate + A79 clamp
import equilibrium_propagate as EP    # scripts/ — the A76 reactive engine (internal plane)
try:
    import recipient_projection as RP  # leo_tools/ — A75 projection
except Exception:
    RP = None


def classify_output_disclosure(text, internal_record):
    """Tag the candidate by disclosure tier so the clamp can hair-split. CRUDE today (contains_facts +
    the internal record's flags); swaps for a richer classifier when the desk mints the output-disclosure
    invariant — L4 consumes the richer return with no call-site change."""
    text = text or ""
    contains_facts = bool(text.strip())
    contradiction = bool(internal_record and internal_record.get("contradictions"))
    cross_matter = bool(internal_record and internal_record.get("cascades"))
    tier = ("contradiction" if contradiction else
            "cross_matter_cascade" if cross_matter else
            "verified_fact" if contains_facts else "general")
    return {"tier": tier, "contains_facts": contains_facts,
            "contradiction": contradiction, "cross_matter": cross_matter}


def _role_policy(cur, role):
    cur.execute("SELECT disclosure_ceiling, gate_default, dose_ceiling, cadence, projection_profile "
                "FROM v_comms_role_policy WHERE role=%s", (role or "",))
    r = cur.fetchone()
    if not r:
        return dict(OG._SAFE_DEFAULT_POLICY)
    keys = ("disclosure_ceiling", "gate_default", "dose_ceiling", "cadence", "projection_profile")
    return dict(r) if isinstance(r, dict) else dict(zip(keys, r))


def _resolve_sender(cur, channel_message_id):
    cur.execute("""SELECT c.name AS channel, cm.channel_user_id, cm.text_content, cm.direction,
                          cu.role AS raw_role, cu.mapped_client_code AS client
                     FROM channel_messages cm JOIN channels c ON c.id = cm.channel_id
                     LEFT JOIN channel_users cu
                            ON cu.channel_id = cm.channel_id AND cu.channel_user_id = cm.channel_user_id
                    WHERE cm.id = %s""", (channel_message_id,))
    r = cur.fetchone()
    if not r:
        return None
    d = dict(r)
    cls = OG.classify(d["channel"], d["channel_user_id"])
    d["role"] = "internal" if cls == "internal" else OG.ROLE_ALIAS.get((d.get("raw_role") or "").lower())
    return d


def _apply_projection(text, profile):
    """A75, downstream of the clamp directive. human_safe → S14 human-readable; machine_typed → typed as-is."""
    if profile == "machine_typed" or not text:
        return text
    try:
        return RP.render_human_reply(text) if RP else text
    except Exception:
        return text


def handle_chat_event(cur, channel_message_id, candidate_text=None, mode="shadow"):
    s = _resolve_sender(cur, channel_message_id)
    if not s:
        return {"error": "channel_message not found", "id": channel_message_id}
    if s["direction"] != "inbound":
        return {"skipped": "not an inbound event", "id": channel_message_id}

    role, client = s["role"], s["client"]

    # ── INTERNAL PLANE (gate-free): perturb the client's ego-network via A76. Hot, accurate, unclamped. ──
    internal = None
    if client:
        cur.execute("SELECT matter_code FROM matters WHERE client_code=%s ORDER BY matter_code LIMIT 1",
                    (client,))
        m = cur.fetchone()
        if m:
            seed = (m["matter_code"] if isinstance(m, dict) else m[0])
            internal = EP.propagate(cur, "matter", seed, interaction_ref=f"cm:{channel_message_id}", hops=2)

    # ── EMISSION PLANE (the only clamped surface) ──
    text = candidate_text if candidate_text is not None else (s["text_content"] or "")
    disclosure = classify_output_disclosure(text, internal)
    policy = _role_policy(cur, role)
    ctx = {"contains_facts": disclosure["contains_facts"], "disclosure_level": disclosure["tier"],
           "source": "comm_agent_max"}
    OG.apply_comms_role_clamp(role, {"text": text}, ctx, cur=cur)   # A79 shadow clamp (logs would-clamp)
    would_clamp, reason = OG._clamp_decision(policy, ctx)
    projected = _apply_projection(text, policy["projection_profile"])  # A75 per clamp directive

    gd = policy["gate_default"]
    if would_clamp or gd in ("refuse", "hold"):
        next_action = "hold_for_operator"
    elif gd == "onboarding":
        next_action = "onboarding_flow"
    else:
        next_action = "would_send"   # SHADOW: never actually sent

    decision = {
        "channel_message_id": channel_message_id, "role": role, "client": client,
        "disclosure_tier": disclosure["tier"], "would_clamp": would_clamp, "clamp_reason": reason,
        "projection_profile": policy["projection_profile"], "dose_ceiling": policy["dose_ceiling"],
        "cadence": policy["cadence"], "next_action": next_action,
        "projected_len": len(projected or ""),
        "internal_ego_nodes": (internal or {}).get("ego_nodes"),
        "internal_contradictions": (internal or {}).get("contradictions"),
        "internal_cross_client_refused": (internal or {}).get("cross_client_refused"),
        "emitted": False, "mode": mode,
    }
    try:  # shadow-log the whole hair-split (A39); never break on logging
        cur.execute("INSERT INTO channel_audit (channel_id, event_type, payload, result) "
                    "VALUES (NULL, 'comm_agent_shadow', %s, %s)", (json.dumps(decision), next_action))
    except Exception:
        pass
    return decision


if __name__ == "__main__":
    import psycopg2, psycopg2.extras
    if len(sys.argv) < 2:
        sys.exit("usage: comm_agent_max.py <channel_message_id>")
    c = psycopg2.connect(EP.DSN); c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    print(json.dumps(handle_chat_event(cur, int(sys.argv[1])), indent=2, default=str))
