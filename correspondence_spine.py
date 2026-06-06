#!/usr/bin/env python3
"""correspondence_spine — shared email ↔ client ↔ matter ↔ goal linkage.

Used by gmail_watcher, client_history_scan, correspondence_matcher, and
deploy_342 trigger/backfill. Single source for client_code resolution and
relevance_status computation.
"""
from __future__ import annotations

import re

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


# Promotional / system noise — never a legal event on the spine.
NOISE_SENDER_RE = re.compile(
    r"(redfin\.com|agoda|kayak@|supergut|pelicanparts|ocregister|"
    r"newsletter|noreply@sg\.newsletter|harvardonline@|ifexphilippines|"
    r"github\.com|google-gemini|openai\.com|anthropic\.com|godaddy|"
    r"accounts\.google\.com|no-reply@tm\.openai)",
    re.I,
)

# Agency, court, counsel, LGU — communications that may require reaction.
LEGAL_ACTOR_RE = re.compile(
    r"(arta\.gov|litigationdivision|barandon|dilg|op\.gov|"
    r"mercedesmunicipality|mercedes\.gov|loidamacale|pajarillo|"
    r"landbank|lra\.gov|registryofdeeds|botor|colenacious|"
    r"litigationdi|southernluzon|complaints\.southernluzon|"
    r"fldomingo@dilg|bayan ng mercedes)",
    re.I,
)

# Filing, order, hearing — an action that develops a situation.
LEGAL_ACTION_RE = re.compile(
    r"(\bCTN\s*SL\b|\bARTA\s+Case\b|civil\s+case\s+no|"
    r"\bresolution\b|\bmanifestation\b|\bNOC\b|\bOSCA\b|\bNSR\b|"
    r"\bhearing\b|\bpretrial\b|\bmediation\b|\bcomplaint\b|"
    r"\bpetition\b|\bappeal\b|\baffidavit\b|\bmotion\b|"
    r"\border\b|\bfiling\b|notice\s+of\s+(appeal|closure|compliance|referral)|"
    r"office\s+of\s+the\s+president|supervisory\s+review|"
    r"counter\s+affidavit|indorsement)",
    re.I,
)


def is_legal_event_email(
    *,
    from_addr: str | None = None,
    subject: str | None = None,
    body_plain: str | None = None,
    relevance_status: str | None = None,
    client_code: str | None = None,
    case_file: str | None = None,
    matter_codes: list[str] | None = None,
    raw_category: str | None = None,
) -> bool:
    """True when email is a legal event for canonical history.

    Jonathan 2026-06-06: an email is a legal event — an action which may
    require a reaction or to be noted for further development of a situation.

    Includes: matter-linked mail, agency/counsel correspondence, filings,
    orders, hearings, manifestations. Excludes: promotional/system noise.
    """
    if matter_codes:
        return True
    if case_file:
        return True
    if client_code:
        return True
    if relevance_status and relevance_status != "unlinked":
        return True

    sender = from_addr or ""
    if NOISE_SENDER_RE.search(sender):
        return False
    if raw_category in ("promotional", "bill", "receipt", "bank_statement", "system_alert"):
        return False

    text = f"{subject or ''}\n{(body_plain or '')[:6000]}"
    if NOISE_SENDER_RE.search(text) and not LEGAL_ACTION_RE.search(text):
        return False

    if LEGAL_ACTOR_RE.search(sender):
        return True
    if LEGAL_ACTION_RE.search(text):
        return True
    if raw_category == "legal_correspondence" and LEGAL_ACTION_RE.search(text):
        return True
    return False


def is_relevant_for_canonical_history(**kwargs) -> bool:
    """Alias — canonical history = legal events only."""
    return is_legal_event_email(**kwargs)