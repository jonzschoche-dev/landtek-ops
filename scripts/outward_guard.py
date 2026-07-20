#!/usr/bin/env python3
"""outward_guard.py — the single governed chokepoint for every OUTWARD move (Phase 1: SHADOW).

Every real egress (tg_send, the SMTP bridges, execution_tracker's mark-filed claim, case_bundle's
raw sendDocument) calls guard() right before it dispatches. The guard classifies the recipient:

  internal  — the operator (Jonathan) or the simulator range → NOT an outward move; let it pass.
  outward   — a party / official / client / anyone else       → an outward move; must be governed.

MODE (outward_guard_config.mode, flip like ontology_validator_config):
  'shadow'  — LOG the decision it WOULD make; change NOTHING. Every send still goes out. (Phase 1.)
  'block'   — an outward send with no matching approved outward_action order is auto-enqueued as one
              and HELD at T3; the caller gets ('hold', ...) and does NOT dispatch.

Design invariants:
  * FAIL-SAFE: any error inside the guard returns ('allow', ...). A guard bug must never block a real
    send (degrade, don't crash). In shadow it is structurally incapable of blocking anyway.
  * OWN CONNECTION: the guard opens its own short-lived autocommit connection for all its DB work, so
    it is immune to the caller's cursor_factory / transaction state and its shadow log always persists.
  * GOVERNED classifier: "who is internal" lives in the internal_targets table (data, not code). A
    hardcoded FLOOR (operator chat + sim prefix) keeps it fail-safe when the DB is unreachable —
    we never mis-hold the operator's own alerts (offline-sovereignty).
  * IDEMPOTENT (block mode): a retried send with the same (target, content_hash) maps to the SAME
    held order, never a duplicate — so a retry loop can't flood the queue.

API:
  classify(channel, recipient) -> 'internal' | 'outward'
  guard(channel, recipient, content_hash=None, source='', preview='') -> (decision, info)
        # decision in {'allow','hold'}; shadow always 'allow'. Extra kwargs (cur=...) are ignored.
"""
from __future__ import annotations
import os
import json
import hashlib
from datetime import datetime, timezone

import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# Fail-safe FLOOR — used only if internal_targets can't be read. Mirrors the migration's seed.
# If the DB is down we must still recognise the operator + sim as internal (never hold their traffic).
FLOOR_INTERNAL = {
    "telegram": [("6513067717", "exact"), ("999000", "prefix")],
    "email": [("jonzschoche@gmail.com", "exact"), ("jonathan@hayuma.org", "exact")],
}

# outward_action step template (used only in block mode when auto-enqueuing). Mirrors supervisor.KINDS.
_OUTWARD_STEPS = [
    {"name": "prepare", "agent": "domain-agent", "mode": "handoff", "tier": "T2", "status": "pending", "result": None},
    {"name": "approve", "agent": "human",        "mode": "handoff", "tier": "T3", "status": "pending", "result": None},
]


def _conn():
    c = psycopg2.connect(DSN, connect_timeout=4)
    c.autocommit = True
    return c


def _norm(channel: str, recipient) -> str:
    r = str(recipient).strip()
    return r.lower() if channel == "email" else r


def _match(recipient: str, identifier: str, match_type: str, channel: str) -> bool:
    ident = identifier.lower() if channel == "email" else identifier
    if match_type == "exact":
        return recipient == ident
    if match_type == "prefix":
        return recipient.startswith(ident)
    if match_type == "domain":  # email only: recipient's domain equals identifier
        return "@" in recipient and recipient.split("@", 1)[1] == ident
    return False


def _floor_is_internal(channel: str, recipient: str) -> bool:
    for ident, mt in FLOOR_INTERNAL.get(channel, []):
        if _match(recipient, ident, mt, channel):
            return True
    return False


def _classify_cur(cur, channel: str, recipient: str) -> str:
    cur.execute(
        "SELECT identifier, match_type FROM internal_targets "
        "WHERE active AND channel IN (%s, '*')",
        (channel,),
    )
    for ident, mt in cur.fetchall():
        if _match(recipient, ident, mt, channel):
            return "internal"
    return "outward"


def classify(channel: str, recipient, **_ignore) -> str:
    """'internal' if the recipient matches a governed internal_targets row (or the fail-safe floor)."""
    r = _norm(channel, recipient)
    try:
        conn = _conn()
        try:
            return _classify_cur(conn.cursor(), channel, r)
        finally:
            conn.close()
    except Exception:
        return "internal" if _floor_is_internal(channel, r) else "outward"


def _mode(cur) -> str:
    try:
        cur.execute("SELECT mode FROM outward_guard_config WHERE id = 1")
        row = cur.fetchone()
        if not row:
            return "shadow"
        return (row["mode"] if isinstance(row, dict) else row[0])  # cursor-parity
    except Exception:
        return "shadow"


def _safe_mode() -> str:
    """Read the guard mode on its OWN short-lived connection — used by the fail-closed error path only.
    Returns 'shadow' on any failure: a mode we cannot positively confirm as enforcing must NOT block a
    real send (offline-sovereignty). The realistic enforce-mode fail-open — a logic bug in guard()'s body
    while the DB is up and mode='block' — is caught here because this fresh read succeeds and returns
    'block'. (deploy_989 / R5-T1)"""
    try:
        c = _conn()
        try:
            return _mode(c.cursor())
        finally:
            c.close()
    except Exception:
        return "shadow"


def _find_approval(cur, target: str, content_hash: str):
    """A live approval = an outward_action order for this target+content, human-cleared (status=done),
    not yet consumed. content_hash is stored in target_ref as '<target>#<hash>' at enqueue time."""
    if not content_hash:
        return None
    cur.execute(
        "SELECT id FROM work_orders WHERE kind='outward_action' AND status='done' "
        "AND target_ref = %s AND NOT (audit::text LIKE %s) "
        "ORDER BY updated_at DESC LIMIT 1",
        (f"{target}#{content_hash}", '%"consumed"%'),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _auto_enqueue(cur, target: str, content_hash: str, source: str, preview: str):
    """Block mode only: create (or reuse) an outward_action held at T3 for this exact outward move."""
    tref = f"{target}#{content_hash}" if content_hash else target
    # Idempotency: an OPEN order for this exact (target, content) already holds it — reuse, don't dup.
    cur.execute(
        "SELECT id FROM work_orders WHERE kind='outward_action' AND target_ref=%s "
        "AND status IN ('queued','in_progress','awaiting_handoff','blocked_governance') LIMIT 1",
        (tref,),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    title = f"[{source}] outward -> {target}: {(preview or '')[:80]}"
    audit = json.dumps([{"at": datetime.now(timezone.utc).isoformat(),
                         "from": None, "to": "queued",
                         "note": f"auto-enqueued by outward_guard (source={source})"}])
    cur.execute(
        "INSERT INTO work_orders (kind, title, status, steps, current_step, governed, target_ref, audit) "
        "VALUES ('outward_action', %s, 'queued', %s, 0, true, %s, %s) RETURNING id",
        (title, json.dumps(_OUTWARD_STEPS), tref, audit),
    )
    return cur.fetchone()[0]


def _log(cur, channel, source, target, content_hash, classification, decision, approved_order, preview):
    try:
        cur.execute(
            "INSERT INTO outward_shadow_log "
            "(channel, source, guard_target, content_hash, classification, would_decision, approved_order, preview) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (channel, source, target, content_hash, classification, decision,
             approved_order, (preview or "")[:280]),
        )
    except Exception:
        pass  # logging must never break a send


# ── A79 role axis (deploy_879) — the single role-clamp read at this one exit ─────────────────────────
# Every externalizing path (COMM-AGENT-MAX bot reply, A76/P2 reactive increment, A75 pulse) passes the
# guard; here it also resolves the recipient's canonical role and logs what its policy WOULD clamp.
# SHADOW: never alters a send. Flip to enforce = act on would_clamp in guard() (one-line change, post-Aug-12).

# Reconcile the three prior vocabularies (channel_users.role / approve_user set / sim) into the canonical
# 6. Anything unmapped (partner, prospect, unknown, unauthorized, …) → None → the most-restrictive safe
# default. Fail-closed by construction: an unrecognised role is treated like a stranger, never like a client.
ROLE_ALIAS = {
    "operator": "internal", "owner": "internal", "internal": "internal", "agent": "agent",
    "client": "client", "counsel": "counsel", "counterparty": "counterparty", "public": "public",
}
_SAFE_DEFAULT_POLICY = {"disclosure_ceiling": "none", "gate_default": "hold", "dose_ceiling": 0,
                        "cadence": "gentle", "projection_profile": "human_safe"}


def _resolve_role(cur, channel, recipient, classification):
    """(channel, recipient) → canonical role. Internal classification wins; else map channel_users.role."""
    if classification == "internal":
        return "internal"
    try:
        cur.execute("SELECT cu.role FROM channel_users cu JOIN channels c ON c.id = cu.channel_id "
                    "WHERE c.name = %s AND cu.channel_user_id = %s", (channel, str(recipient)))
        row = cur.fetchone()
        raw = ((row[0] if row else "") or "").lower()
    except Exception:
        raw = ""
    return ROLE_ALIAS.get(raw)  # None → safe default in the clamp


def _clamp_decision(policy, context):
    """PURE: given a role policy + output context, would the clamp fire, and why? (Testable in isolation.)

    A80 tier NOT YET COMPARED (R5-T3, held): the output-disclosure tier that comm_agent_max computes
    (context['disclosure_level'] ∈ {contradiction, cross_matter_cascade, verified_fact, general}) is
    logged but NOT compared here against the role's disclosure_ceiling ∈ {none, machine_typed,
    facts_plus_strategy, full}. The two are different axes with NO shared vocabulary; wiring the
    comparison requires the ontology desk to reconcile them (see docs/DIRECTIVE_A80_disclosure_vocab.md).
    This executor does NOT self-mint that mapping. Until the directive lands, the tier stays advisory and
    the clamp fires only on the two ceiling/gate signals below (fail-closed for none/refuse)."""
    if policy.get("gate_default") == "refuse":
        return True, "role gate_default=refuse — never auto-anything"
    if policy.get("disclosure_ceiling") == "none" and context.get("contains_facts"):
        return True, "disclosure_ceiling=none forbids facts/content"
    return False, None


def apply_comms_role_clamp(recipient_role, proposed_output, context, cur=None):
    """Read v_comms_role_policy once, log what would clamp, and (SHADOW) return proposed_output UNCHANGED.
    The one contract the bot/engine/pulse share. Never raises; never blocks in shadow."""
    own = cur is None
    conn = None
    try:
        if own:
            conn = _conn(); cur = conn.cursor()
        policy = None
        try:
            cur.execute("SELECT disclosure_ceiling, gate_default, dose_ceiling, cadence, projection_profile "
                        "FROM v_comms_role_policy WHERE role = %s", (recipient_role or "",))
            r = cur.fetchone()
            if r:
                # cursor-parity: a RealDictCursor caller (leo_instant, comm_agent_soak, comm_agent_max)
                # returns a dict row; zip(keys, dict) would iterate the row's KEYS → self-referential
                # garbage, so would_clamp read False for every counterparty. Guard on isinstance (mirrors
                # comm_agent_max._role_policy) so the shadow audit tells the truth. (deploy_989 / R5-T2)
                _keys = ("disclosure_ceiling", "gate_default", "dose_ceiling", "cadence", "projection_profile")
                policy = dict(r) if isinstance(r, dict) else dict(zip(_keys, r))
        except Exception:
            policy = None
        if policy is None:
            policy = dict(_SAFE_DEFAULT_POLICY)  # unknown/unmapped role → most restrictive
        would_clamp, reason = _clamp_decision(policy, context)
        audit = {"role": recipient_role, "policy": {k: policy[k] for k in policy},
                 "would_clamp": would_clamp, "clamp_reason": reason,
                 "disclosure_level": context.get("disclosure_level"), "source": context.get("source"),
                 "at": datetime.now(timezone.utc).isoformat()}
        try:  # shadow audit → channel_audit (A39); logging must never break a send
            cur.execute("INSERT INTO channel_audit (channel_id, event_type, payload, result) "
                        "VALUES (NULL, 'role_clamp_shadow', %s, %s)",
                        (json.dumps(audit), "would_clamp" if would_clamp else "clear"))
        except Exception:
            pass
        return proposed_output  # SHADOW: the send is never altered
    finally:
        if own and conn is not None:
            conn.close()


def guard(channel, recipient, content_hash=None, source="", preview="", **_ignore):
    """Decide whether an outward move may proceed. SHADOW: always ('allow', ...) after logging.
    Returns ('allow'|'hold', info). NEVER raises — a guard failure defaults to allow.
    Accepts and ignores a caller cur= (the guard always uses its own connection)."""
    conn = None
    try:
        if content_hash is None:
            content_hash = hashlib.sha256((preview or "").encode("utf-8")).hexdigest()[:16]
        conn = _conn()
        cur = conn.cursor()
        mode = _mode(cur)
        target = f"{channel}:{recipient}"
        cls = _classify_cur(cur, channel, _norm(channel, recipient))

        # A79 role-axis shadow clamp: resolve the recipient's canonical role and log what its policy
        # WOULD clamp. Shadow — advisory only, never alters the decision below. Fail-safe (own try).
        try:
            _role = _resolve_role(cur, channel, _norm(channel, recipient), cls)
            apply_comms_role_clamp(_role, {"preview": preview},
                                   {"contains_facts": bool((preview or "").strip()),
                                    "source": source, "target": target}, cur=cur)
        except Exception:
            pass

        if cls == "internal":
            _log(cur, channel, source, target, content_hash, cls, "internal_skip", None, preview)
            return ("allow", {"classification": cls, "mode": mode})

        # outward — is there already a human-approved order for this exact move?
        approved = _find_approval(cur, target, content_hash)
        if approved:
            _log(cur, channel, source, target, content_hash, cls, "would_allow_approved", approved, preview)
            if mode == "block":
                cur.execute(  # consume the approval so it authorizes exactly one send
                    "UPDATE work_orders SET audit = audit || %s::jsonb WHERE id=%s",
                    (json.dumps([{"at": datetime.now(timezone.utc).isoformat(), "note": "consumed"}]), approved),
                )
            return ("allow", {"classification": cls, "mode": mode, "order": approved})

        # outward, no approval
        _log(cur, channel, source, target, content_hash, cls, "would_hold", None, preview)
        if mode == "block":
            oid = _auto_enqueue(cur, target, content_hash, source, preview)
            return ("hold", {"classification": cls, "mode": mode, "order": oid,
                             "reason": "no approved outward_action; held at T3"})
        return ("allow", {"classification": cls, "mode": mode, "shadow": True})
    except Exception as e:
        # FAIL-CLOSED for an outward send in enforce (block) mode (A21/A43): a guard error must never let
        # unapproved raw text reach a party. OFFLINE-SOVEREIGN for internal: the operator/sim (floor-
        # classified without the DB) are never held — their own alerts must always flow. SHADOW-SAFE: in
        # shadow the guard is structurally non-blocking, so it still allows (never blocks a real send).
        # This changes behaviour ONLY on the block-mode error path — which is not active today — so it
        # makes the future enforce switch trustworthy without altering current shadow behaviour. (R5-T1)
        try:
            is_internal = _floor_is_internal(channel, _norm(channel, recipient))
        except Exception:
            is_internal = True   # cannot even classify → treat as internal-safe (never block on a bug)
        eff_mode = _safe_mode()
        if eff_mode == "block" and not is_internal:
            return ("hold", {"classification": "outward", "mode": eff_mode,
                             "reason": "guard error — fail-closed hold (A21/A43)", "error": str(e)})
        return ("allow", {"error": str(e), "mode": eff_mode})  # shadow / internal / unknown-mode: allow
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="outward_guard — classify/guard a hypothetical send")
    ap.add_argument("channel"); ap.add_argument("recipient")
    ap.add_argument("--preview", default="test"); ap.add_argument("--source", default="cli")
    a = ap.parse_args()
    print("classify:", classify(a.channel, a.recipient))
    print("guard   :", guard(a.channel, a.recipient, source=a.source, preview=a.preview))
