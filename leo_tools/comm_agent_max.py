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
    import leo_service as LS           # scripts/ — the generation + delivery engine (the orchestrator calls it)
except Exception:
    LS = None
try:
    import relationship_profile as RPRO  # scripts/ — the living per-relationship organ (Increment 2)
except Exception:
    RPRO = None
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


def _matter_tokens(matter_code):
    """DISTINCTIVE identifier tokens only, e.g. 'MWK-ARTA-1891' -> {ARTA-1891, 1891}; 'MWK-CV26360' ->
    {CV26360}. Kept: compound-dashed codes, alphanumeric codes (letters+digits), pure-numeric dockets
    >=4 digits. DROPPED: pure-alpha category words (ARTA, LGU, VOID, ESTATE, DLF) — they false-match
    generic prose ('VOID' in 'avoid', 'ARTA' the agency, 'LGU' the office) — and client/non-ID prefixes.
    This is the fix for the soak's 4/4 false positives."""
    import re
    GENERIC = {"MWK", "PAR", "NIBDC", "PARACALE", "AUTO"}
    parts = [p for p in matter_code.split("-") if p and p.upper() not in GENERIC]
    toks = set()
    if len(parts) >= 2:
        toks.add("-".join(parts))                      # full compound e.g. ARTA-1891 (highly distinctive)
    for p in parts:
        has_digit, has_alpha = bool(re.search(r"\d", p)), bool(re.search(r"[A-Za-z]", p))
        if has_digit and has_alpha:
            toks.add(p)                                # alphanumeric, e.g. CV26360
        elif has_digit:
            m = re.search(r"\d{4,}", p)
            if m:
                toks.add(m.group(0))                   # pure-numeric docket, >=4 digits only
        # pure-alpha part -> DROPPED (generic)
    return {t for t in toks if len(t) >= 4}


def _token_present(token, text):
    """Word-boundary match (alnum-safe both sides) — 'VOID' must NOT match 'avoid', '1891' must NOT match
    inside '218915'."""
    import re
    return re.search(r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])", text, re.I) is not None


def resolve_chat_matter(cur, channel_message_id, client_code):
    """[STUB — designed + tested, NOT yet the graph anchor] Resolve the SPECIFIC matter a chat is about.
    Ladder: (1) keyword/entity match of the message text against the client's matter identifiers;
    (2) [deferred] the sender's most-recent matter context via propagation_log/leo_interactions;
    (3) fallback = the client's most fact-rich matter (today's heuristic). Returns (matter_code, method).

    Not wired into the chat_context edge yet — the view still anchors to the biggest matter until the
    post-soak increment replaces it with this resolver's output (avoids touching the live traversal
    surface mid-soak). Proven by test_matter_disambig."""
    cur.execute("SELECT text_content FROM channel_messages WHERE id=%s", (channel_message_id,))
    r = cur.fetchone()
    txt = ((r["text_content"] if isinstance(r, dict) else (r[0] if r else "")) or "").lower()

    # (1) keyword match against the client's matters — word-boundary; longest (most distinctive) token wins
    cur.execute("SELECT matter_code FROM matters WHERE client_code=%s", (client_code,))
    best_mc, best_len = None, 0
    for row in cur.fetchall():
        mc = row["matter_code"] if isinstance(row, dict) else row[0]
        for tok in _matter_tokens(mc):
            if len(tok) > best_len and _token_present(tok, txt):
                best_mc, best_len = mc, len(tok)
    if best_mc:
        return best_mc, "keyword"

    # (3) fallback: the client's most fact-rich matter (current heuristic)
    cur.execute("""SELECT matter_code FROM matter_facts
                    WHERE _client_of(matter_code)=%s AND provenance_level='verified'
                    GROUP BY matter_code ORDER BY count(*) DESC LIMIT 1""", (client_code,))
    row = cur.fetchone()
    mc = (row["matter_code"] if isinstance(row, dict) else (row[0] if row else None))
    return mc, "fallback_biggest"


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


def handle_chat_event(cur, channel_message_id, candidate_text=None, force_shadow=True, mode="shadow"):
    """THE single equilibrium-aligned orchestrator for one inbound event (the convergence):
      A76 propagate (internal, gate-free) → leo_service.generate_reply (grounded, memory, equilibrium-
      informed) → A79 clamp → A75 projection → next_action; sends ONLY when force_shadow=False AND the
      clamp says would_send. Two planes preserved: internal reasoning is unclamped; only emission clamps."""
    s = _resolve_sender(cur, channel_message_id)
    if not s:
        return {"error": "channel_message not found", "id": channel_message_id}
    if s["direction"] != "inbound":
        return {"skipped": "not an inbound event", "id": channel_message_id}

    role, client = s["role"], s["client"]
    channel, uid, message = s["channel"], str(s["channel_user_id"]), (s["text_content"] or "")

    # ── INTERNAL PLANE (gate-free): A76 ego-network recompute on the chat node (per-hop A5 on the matview) ──
    internal = None
    if client:
        internal = EP.propagate(cur, "chat", channel_message_id,
                                interaction_ref=f"cm:{channel_message_id}", hops=2)

    # ── LIVING PROFILE (Increment 2): after propagate, evolve the per-relationship record from this
    # verified exchange (append-only arc + living summary) — it feeds generation and grows every time. ──
    profile = None
    tending = []
    if client and RPRO is not None:
        try:
            profile = RPRO.observe(cur, channel, uid, client, s.get("entity_id"),
                                   channel_message_id, message, internal)
        except Exception:
            profile = None
        # ── ANTICIPATORY TENDING (agentic increment): from the record's OBSERVED themes, surface 0-2
        # genuinely time-sensitive items THIS relationship cares about — an input to generation, never a
        # command. Empty is valid + common. Deterministic + $0. The arc records what was surfaced. ──
        if profile is not None:
            try:
                tending = RPRO.anticipate(cur, client, profile)
                RPRO.record_anticipation(cur, channel, uid, channel_message_id, tending)
            except Exception:
                tending = []

    # ── GENERATION (the convergence): grounded reply, informed by the equilibrium state, the living
    # relationship profile AND anticipatory tending. NOT the raw inbound echo. candidate_text override
    # wins (tests/soak). ──
    # Phase A: purpose router FIRST (A85 — same try_purpose_route as ls.process). Preformed packs
    # (title / corpus / mprb) must NOT be re-phrased by A75 or links/dose break.
    gen = None
    preformed = False
    route_via = None
    if candidate_text is not None:
        text = candidate_text
    elif client and LS is not None:
        try:
            route = LS.try_purpose_route(cur, client, message)
        except Exception:
            route = None
        if route and route.get("text") and route.get("preformed"):
            text = route["text"]
            preformed = True
            route_via = route.get("via")
            gen = {"text": text, "verdict": "preformed", "via": route_via, "remediated": False}
        else:
            # Inject MPRB into generation when matters resolve (internal plane)
            mprb_ctx = internal
            try:
                import matter_brief as mb
                brief = mb.assemble_for_message(cur, client, message)
                if brief and mprb_ctx is not None and isinstance(mprb_ctx, dict):
                    mprb_ctx = dict(mprb_ctx)
                    mprb_ctx["mprb_render"] = mb.render(brief)
                elif brief:
                    mprb_ctx = {"mprb_render": mb.render(brief),
                                "contradictions": (internal or {}).get("contradictions"),
                                "cascades": (internal or {}).get("cascades")}
            except Exception:
                mprb_ctx = internal
            gen = LS.generate_reply(cur, channel, uid, message, client, internal_context=mprb_ctx,
                                    relationship_profile=profile, inbound_msg_id=channel_message_id,
                                    relationship_tending=tending)
            text = gen.get("text") or ""
    else:
        text = ""   # unresolved client → A25 hold (no generation)

    # ── EMISSION PLANE (the only clamped surface) ──
    disclosure = classify_output_disclosure(text, internal)
    policy = _role_policy(cur, role)
    ctx = {"contains_facts": disclosure["contains_facts"], "disclosure_level": disclosure["tier"],
           "source": "comm_agent_max"}
    OG.apply_comms_role_clamp(role, {"text": text}, ctx, cur=cur)   # A79 clamp (shadow-logs would-clamp)
    would_clamp, reason = OG._clamp_decision(policy, ctx)
    # preformed artifacts: clamp decides whether/to-whom; projection does NOT rewrite
    if preformed:
        projected = text
    else:
        projected = _apply_projection(text, policy["projection_profile"])  # A75

    gd = policy["gate_default"]
    guard_class = OG.classify(channel, uid)   # A21: 'internal' (operator) vs 'outward'
    if client is None:
        next_action = "held_a25"
    elif would_clamp or gd in ("refuse", "hold"):
        next_action = "hold_for_operator"
    elif gd == "onboarding":
        next_action = "onboarding_flow"
    elif guard_class == "outward":
        # A21 outward chokepoint: A79 shapes WHAT/HOW a role may receive, but the actual outward SEND
        # still holds for approval until per-role enforce — so the orchestrator is never less strict
        # than the live internal/outward floor. Internal (operator) is the only auto-send.
        next_action = "hold_for_operator"
    else:
        next_action = "would_send"

    emitted = False
    if not force_shadow and next_action == "would_send" and projected and LS is not None:
        try:                                # LIVE cutover path (Step 4) — send via the generation engine
            emitted = bool(LS._deliver(channel, uid, projected))
        except Exception:
            emitted = False

    decision = {
        "channel_message_id": channel_message_id, "role": role, "client": client,
        "disclosure_tier": disclosure["tier"], "would_clamp": would_clamp, "clamp_reason": reason,
        "projection_profile": policy["projection_profile"], "dose_ceiling": policy["dose_ceiling"],
        "cadence": policy["cadence"], "next_action": next_action,
        "would_send_human": projected, "projected_len": len(projected or ""),
        "generated": bool(gen), "gate_verdict": (gen or {}).get("verdict"),
        "preformed": preformed, "route_via": route_via,
        "internal_ego_nodes": (internal or {}).get("ego_nodes"),
        "internal_contradictions": (internal or {}).get("contradictions"),
        "internal_cross_client_refused": (internal or {}).get("cross_client_refused"),
        "tending": tending, "tending_count": len(tending or []),
        "emitted": emitted, "mode": mode,
    }
    try:  # shadow-log the whole hair-split (A39); never break on logging
        cur.execute("INSERT INTO channel_audit (channel_id, event_type, payload, result) "
                    "VALUES (NULL, 'comm_agent_shadow', %s, %s)", (json.dumps(decision, default=str), next_action))
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
