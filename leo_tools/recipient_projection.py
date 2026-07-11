#!/usr/bin/env python3
"""recipient_projection.py — one truth, N recipient-shaped projections (A75; design: docs/RECIPIENT_PROJECTION.md).

Generalizes ClientProjection (A32/A33, `client_ontology.py`) beyond the paying client: EVERY recipient of
the pulse — human or agent — receives the incorporated truth through a profile that fixes WHO (the A5/A35
isolation wall, enforced in the QUERY, never the formatter) · PURPOSE (the next increment) · FORM (HUMAN
narrative vs MACHINE typed-with-handles) · DOSE (push ceiling vs PULL_COMPLETE).

Humans fail from too much; agents fail from too little. So: HUMAN form translates (plain confidence per
A34, via client_ontology — reused, never forked) and is push-ceilinged; MACHINE form keeps provenance
handles INTACT (doc/fact IDs, provenance enums — an agent must cite and verify) and a pulled work-slice
is complete-in-one-payload (the ceiling governs push, never truncates pull).

Registry is code-first (reviewed, versioned — the client_ontology precedent); promote to a table only
when profiles outgrow review.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PULL_COMPLETE = "PULL_COMPLETE"

# key -> RecipientProfile (docs/RECIPIENT_PROJECTION.md §3)
PROFILES = {
    # Deliverable-emitter projection (A75 graduation, deploy_858): brief_drafter's verified-fact
    # work-slice for drafting counsel work-product. PULL_COMPLETE — a draft needs the WHOLE verified
    # base (starving it yields a thin draft); the A70 incorporation gate decides IF it may draft at all.
    "brief-drafter": {
        "kind": "agent",
        "who": {"matter_scope": "per-invocation --matter", "role": "drafting agent — verified-only; "
                "output is a DRAFT for counsel review, never filed"},
        "purpose": "draft counsel work-product grounded strictly in this matter's verified facts",
        "form": "MACHINE",
        "dose": PULL_COMPLETE,
        "channel": "cli",
    },
    # Deliverable-emitter projection (A75 graduation, deploy_870): case_memo's verified fact slice
    # (statement + excerpt + source handle) for the counsel-ready action memo. PULL_COMPLETE — the
    # memo cites the whole verified base; the A70 gate decides IF a memo may build at all.
    "case-memo": {
        "kind": "agent",
        "who": {"matter_scope": "per-invocation argv[1]", "role": "counsel-ready memo renderer — "
                "verified-only, cites the source; output is a DRAFT memo, never filed"},
        "purpose": "render a counsel-grade action memo grounded strictly in this matter's verified facts",
        "form": "MACHINE",
        "dose": PULL_COMPLETE,
        "channel": "cli",
    },
    # Deliverable-emitter projection (A75 graduation, deploy_874): case_bundle's verified fact slice
    # (statement + source handle) captioning the bound exhibit PDF. PULL_COMPLETE — the bundle cites
    # the whole verified base; the A70 gate decides IF a bundle may bind at all.
    "case-bundle": {
        "kind": "agent",
        "who": {"matter_scope": "per-invocation argv[1]", "role": "exhibit-bundle binder — verified-only "
                "fact captions; output is a bound PDF DRAFT for counsel, never filed"},
        "purpose": "caption a bound exhibit PDF from this matter's verified facts",
        "form": "MACHINE",
        "dose": PULL_COMPLETE,
        "channel": "cli",
    },
    # The first agent-facing projection (deploy_844 proof): the ombudsman hunter's fact work-slice.
    "ombudsman-hunter": {
        "kind": "agent",
        "who": {"matter_scope_env": "OMB_SCOPE", "role": "offense lead engine (leads, never files)"},
        "purpose": "scan this client's verified record for public-officer misconduct signals",
        "form": "MACHINE",
        "dose": PULL_COMPLETE,          # a pulled work-slice: completeness wins (agents starve on too-little)
        "channel": "cli",               # internal; outward moves stay behind A21
    },
    # The second agent-facing projection (A75 rollout T1): the verify-worker's doc work-slice — the
    # reader that grows the verified corpus. Breadth-fair across ALL governed matters BY DESIGN; the
    # WHO wall is declared explicitly ('%') and still enforced IN THE QUERY (verify_loop.doc_worklist's
    # SQL takes the scope as a bound parameter), so narrowing it is a one-line profile change, never
    # a post-filter.
    "verify-worker": {
        "kind": "agent",
        "who": {"matter_scope": "%", "role": "autonomous corpus reader — breadth-fair across all governed "
                                             "matters (internal; writes only through the hardened provenance gate)"},
        "purpose": "read the next legible source docs and grow the verified corpus (verified = verbatim-grounded quote only)",
        "form": "MACHINE",
        "dose": PULL_COMPLETE,          # pulled work-slice arrives COMPLETE; --limit paces WORK, never truncates the slice
        "channel": "cli",               # systemd oneshot (landtek-verify-worker.timer, 15 min); nothing outward
    },
    # The push-side projection (A75 rollout T2): the pulse orchestrator's work-order payloads
    # (calendar_orchestrator.py, deploy_840). PUSH path — the dose ceiling is REAL here:
    # dose.push_max_per_window IS the orchestrator's per-tick cap (its DEFAULT_CAP reads this value;
    # over-cap items are DEFERRED WITH A LOG LINE, never silently dropped).
    "pulse-orchestrator": {
        "kind": "agent",
        "who": {"matter_scope": "%", "role": "the pulse — fires deliverable-prep work orders from dated agenda "
                                             "items (enqueue-only; every order ends in a human T3 hold)"},
        "purpose": "start preparation on the next dated increment (T-14 prep) as a supervised, fail-closed work order",
        "form": "MACHINE",
        "dose": {"push_max_per_window": 10, "window": "pulse tick (daily 05:30 Asia/Manila, landtek-pulse-orchestrator.timer)"},
        "channel": "db",                # work_orders rows via the supervisor state machine; never sends anything
    },
    # Worked-example human profile (design §4) — NOT wired; the tenant surface arrives with Property v2.0.
    "tenant-example": {
        "kind": "human",
        "who": {"client_code": None, "role": "tenant"},
        "purpose": "confirm or act on the single next obligation (e.g. rent due)",
        "form": "HUMAN",
        "dose": {"push_max_per_window": 1, "window": "day"},   # S14: one point, no double-tap
        "channel": "telegram (A26 token-as-switch; outward-gated)",
    },
}


def profile(key):
    p = PROFILES.get(key)
    if p is None:
        raise KeyError(f"no RecipientProfile {key!r} — register it in recipient_projection.PROFILES "
                       f"(no recipient reads raw un-projected data, A75)")
    return dict(p, key=key)


def project_fact_slice(cur, profile_key, matter_scope):
    """MACHINE-form fact work-slice for an agent profile: typed dicts, provenance handles intact,
    client/matter scope enforced IN THE QUERY (the WHO wall), complete-in-one-payload (PULL_COMPLETE)."""
    p = profile(profile_key)
    if p["form"] != "MACHINE":
        raise ValueError(f"{profile_key!r} is a {p['form']} profile — project_fact_slice serves MACHINE only")
    cur.execute("""
        SELECT id, matter_code,
               COALESCE(statement, '')         AS statement,
               COALESCE(source_id::text, '')   AS source_id,
               COALESCE(provenance_level, '')  AS provenance_level,
               COALESCE(excerpt, '')           AS excerpt
        FROM matter_facts WHERE matter_code LIKE %s
    """, (matter_scope,))
    return [{"fact_id": r[0], "matter_code": r[1], "statement": r[2],
             "excerpt": r[5],
             "source_id": r[3], "provenance_level": r[4]} for r in cur.fetchall()]


def project_doc_slice(cur, profile_key, matter_scope=None):
    """MACHINE-form DOC work-slice for a reader agent (A75 T1): the ranked next-reads worklist,
    handles intact (doc id · matter_code · ranking signals), scope enforced IN THE QUERY (the WHO
    wall — verify_loop.doc_worklist binds it as a SQL parameter, never a post-filter), and
    complete-in-one-payload (PULL_COMPLETE: the slice is never paginated/truncated here; a caller's
    --limit paces how much WORK it takes per tick, not how much slice it may see)."""
    p = profile(profile_key)
    if p["form"] != "MACHINE":
        raise ValueError(f"{profile_key!r} is a {p['form']} profile — project_doc_slice serves MACHINE only")
    if p["dose"] != PULL_COMPLETE:
        raise ValueError(f"{profile_key!r} is not a PULL_COMPLETE profile — a doc work-slice is pulled, "
                         f"complete-in-one-payload (dose ceilings govern push, never pull)")
    scope = matter_scope or p["who"].get("matter_scope")
    if not scope:
        raise ValueError(f"{profile_key!r} declares no matter_scope — the WHO wall must be explicit (A5)")
    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from verify_loop import doc_worklist  # the ONE worklist query (reused, never forked); scope goes into its SQL
    return doc_worklist(cur, matter_scope=scope)


def project_pulse_payload(profile_key, item, due_date, rule):
    """MACHINE-form PUSH payload for a pulse-fired work order (A75 T2): typed dict, handles intact
    (agenda uid · matter/client codes · due date · firing rule) so the downstream agent can trace the
    order back to the dated item that fired it. PUSH path: the CALLER enforces this profile's
    dose.push_max_per_window per tick (deferrals logged, never silent) — this function shapes one
    payload; it does not dose."""
    p = profile(profile_key)
    if p["form"] != "MACHINE":
        raise ValueError(f"{profile_key!r} is a {p['form']} profile — project_pulse_payload serves MACHINE only")
    return {
        "profile": p["key"],
        "rule": rule,
        "item_uid": item.uid,                       # the agenda handle — load-bearing, never stripped
        "title": (item.title or "")[:200],
        "matter_code": item.matter or None,
        "client_code": item.client or None,
        "owner": item.owner or None,
        "due_date": due_date.isoformat(),
    }


def render_human_fact(statement, provenance_level):
    """HUMAN-form rendering of one fact: plain statement + translated (never upgraded) confidence.
    Reuses client_ontology (A32/A33/A34) — the one vocabulary, not a fork."""
    import client_ontology as co
    badge = co.client_provenance_badge(provenance_level)
    return statement + (f" ({badge})" if badge else "")


import re as _re

# internal provenance/grounding handles the GATE uses to verify, but a HUMAN client must never see (A32).
_HANDLE_RE = _re.compile(r"\(?\b(?:doc|fact)\s*:\s*\d+\)?|§\s*[\d.]+|\bA\d{1,3}\b|\bV\d{1,2}\b", _re.IGNORECASE)


def render_human_reply(text):
    """HUMAN-form projection of a free-text reply (A32/A34): strip internal handles (doc:N / fact:N /
    §x / A-invariant / V-check tokens) so the client sees plain language, never provenance plumbing.
    The answer-gate verifies grounding on the handled form FIRST; this projects the passed reply."""
    if not text:
        return text
    t = _HANDLE_RE.sub("", text)
    # a stripped handle can leave a dangling connective ("...as mentioned in ." / "...see ,") — drop it
    t = _re.sub(r"\b(?:as mentioned in|as noted in|as stated in|as per|per|see|refer to)\s*(?=[.,;:!?]|$)",
                "", t, flags=_re.IGNORECASE)
    t = _re.sub(r"\s{2,}", " ", t)
    t = _re.sub(r"\s+([.,;:!?])", r"\1", t)
    return t.strip()
