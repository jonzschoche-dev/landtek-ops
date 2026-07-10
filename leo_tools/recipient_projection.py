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
    # The first agent-facing projection (deploy_844 proof): the ombudsman hunter's fact work-slice.
    "ombudsman-hunter": {
        "kind": "agent",
        "who": {"matter_scope_env": "OMB_SCOPE", "role": "offense lead engine (leads, never files)"},
        "purpose": "scan this client's verified record for public-officer misconduct signals",
        "form": "MACHINE",
        "dose": PULL_COMPLETE,          # a pulled work-slice: completeness wins (agents starve on too-little)
        "channel": "cli",               # internal; outward moves stay behind A21
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
               COALESCE(provenance_level, '')  AS provenance_level
        FROM matter_facts WHERE matter_code LIKE %s
    """, (matter_scope,))
    return [{"fact_id": r[0], "matter_code": r[1], "statement": r[2],
             "source_id": r[3], "provenance_level": r[4]} for r in cur.fetchall()]


def render_human_fact(statement, provenance_level):
    """HUMAN-form rendering of one fact: plain statement + translated (never upgraded) confidence.
    Reuses client_ontology (A32/A33/A34) — the one vocabulary, not a fork."""
    import client_ontology as co
    badge = co.client_provenance_badge(provenance_level)
    return statement + (f" ({badge})" if badge else "")
