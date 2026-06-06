#!/usr/bin/env python3
"""correspondence_spine — shared email ↔ client ↔ matter ↔ goal linkage.

Used by gmail_watcher, client_history_scan, correspondence_matcher, and
deploy_342 trigger/backfill. Single source for client_code resolution and
relevance_status computation.
"""
from __future__ import annotations

# matter_code prefix → client_code (mirrors case_theories._clients.CLIENTS)
MATTER_PREFIX_CLIENT: dict[str, str] = {
    "MWK-": "MWK-001",
    "PAR-": "Paracale-001",
}

RELEVANCE_ORDER = ("unlinked", "client_only", "matter_linked", "goal_linked", "assessed")


def resolve_client_for_case(cur, case_file: str | None) -> str | None:
    """case_file → client_code via clients or matters."""
    if not case_file:
        return None
    cur.execute("SELECT client_code FROM clients WHERE case_file = %s LIMIT 1", (case_file,))
    r = cur.fetchone()
    if r:
        return r["client_code"] if isinstance(r, dict) else r[0]
    cur.execute(
        "SELECT DISTINCT client_code FROM matters WHERE case_file = %s LIMIT 1",
        (case_file,),
    )
    r = cur.fetchone()
    if not r:
        return None
    return r["client_code"] if isinstance(r, dict) else r[0]


def resolve_client_from_matter_codes(cur, matter_codes: list[str] | None) -> str | None:
    """Derive client_code from matter_code prefix or matters table."""
    if not matter_codes:
        return None
    for mc in matter_codes:
        if not mc:
            continue
        for prefix, client_code in MATTER_PREFIX_CLIENT.items():
            if mc.startswith(prefix):
                return client_code
    cur.execute(
        "SELECT DISTINCT client_code FROM matters WHERE matter_code = ANY(%s) LIMIT 1",
        (list(matter_codes),),
    )
    r = cur.fetchone()
    if not r:
        return None
    return r["client_code"] if isinstance(r, dict) else r[0]


def resolve_client_code(
    cur,
    *,
    case_file: str | None = None,
    matter_codes: list[str] | None = None,
    existing: str | None = None,
) -> str | None:
    """Best-effort client_code from any available signal."""
    if existing:
        return existing
    if case_file:
        cc = resolve_client_for_case(cur, case_file)
        if cc:
            return cc
    return resolve_client_from_matter_codes(cur, matter_codes)


def compute_relevance_status(
    *,
    client_code: str | None,
    matter_codes: list[str] | None,
    has_goal_links: bool,
    has_assessment: bool,
) -> str:
    """Map row state → relevance_status enum."""
    if has_assessment:
        return "assessed"
    if has_goal_links:
        return "goal_linked"
    if matter_codes and len(matter_codes) > 0:
        return "matter_linked"
    if client_code:
        return "client_only"
    return "unlinked"


def gmail_history_matter_code(matter_codes: list[str] | None) -> str | None:
    """Pick primary matter for client_history.matter_code (first linked)."""
    if not matter_codes:
        return None
    return matter_codes[0]