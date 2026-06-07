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


CTN_SL_SUFFIX_RE = re.compile(
    r"\bCTN\s*s?\s*[-:]?\s*SL\s*[-]?\s*\d{4}\s*[-]?\s*\d{4}\s*[-]?\s*(\d{3,4})\b",
    re.I,
)

CV26360_MENTION_RE = re.compile(
    r"(civil\s+case|cv|case)\s+(no\.?)?\s*-?\s*26-?360",
    re.I,
)

DILG_SENDER_RE = re.compile(
    r"(dilgcamarinesnorte|fldomingo@dilg|@dilg\.gov|region\d*dilg|"
    r"dilgr\d*records|dilg5records|dilg_?records)",
    re.I,
)


def parse_arta_matter_codes_from_text(haystack: str) -> list[str]:
    """Extract MWK-ARTA-#### codes from CTN SL docket references in email text."""
    seen: list[str] = []
    for m in CTN_SL_SUFFIX_RE.finditer(haystack or ""):
        suffix = m.group(1)
        if len(suffix) == 3:
            suffix = "0" + suffix
        code = f"MWK-ARTA-{suffix}"
        if code not in seen:
            seen.append(code)
    return seen


def sanitize_gmail_matter_codes(
    *,
    from_addr: str | None,
    subject: str | None,
    body_plain: str | None,
    matter_codes: list[str] | None,
    valid_matter_codes: set[str] | None = None,
) -> list[str]:
    """Derive matter_codes from CTN text; CV26360 only when 26-360 is mentioned.

    deploy_355: ARTA Litigation Division mail is tagged by CTN suffix, not
    blanket-linked to Civil Case 26-360.
    """
    haystack = f"{from_addr or ''} {subject or ''} {body_plain or ''}"
    arta_codes = parse_arta_matter_codes_from_text(haystack)
    preserved = [
        mc
        for mc in (matter_codes or [])
        if mc and mc != "MWK-CV26360" and not mc.startswith("MWK-ARTA-")
    ]
    out: list[str] = []
    for mc in arta_codes + preserved:
        if mc not in out:
            out.append(mc)
    if CV26360_MENTION_RE.search(haystack) and "MWK-CV26360" not in out:
        out.append("MWK-CV26360")
    # DILG admin track — not Civil 26-360 unless explicitly cited above.
    if (
        not arta_codes
        and DILG_SENDER_RE.search(from_addr or "")
        and "MWK-ARTA-DILG" not in out
    ):
        out.append("MWK-ARTA-DILG")
    if valid_matter_codes is not None:
        out = [mc for mc in out if mc in valid_matter_codes]
    return out


def gmail_history_matter_code(matter_codes: list[str] | None) -> str | None:
    """Pick primary matter for client_history — prefer ARTA admin over civil."""
    if not matter_codes:
        return None
    for mc in matter_codes:
        if mc and mc.startswith("MWK-ARTA-"):
            return mc
    return matter_codes[0]


# Promotional / system noise — never a legal event on the spine or active KB.
NOISE_SENDER_RE = re.compile(
    r"(redfin\.com|realtor\.com|nerdwallet|agoda|kayak@|supergut|pelicanparts|"
    r"ocregister|hiive\.com|samsung|pelicanparts\.com|agoda-emails\.com|"
    r"newsletter|noreply@sg\.newsletter|harvardonline@|ifexphilippines|"
    r"github\.com|google-gemini|openai\.com|anthropic\.com|godaddy|"
    r"accounts\.google\.com|no-reply@tm\.openai|mail\.beehiiv|substack\.com|"
    r"constantcontact|mailchimp|sendgrid\.net|amazonses\.com|"
    r"listings@|marketing@|promo@|deals@|offers@)",
    re.I,
)

NOISE_CATEGORIES = frozenset({
    "promotional", "system_alert", "personal",
})

NOISE_SUBJECT_RE = re.compile(
    r"(new in tucson|price decrease|home for you|\d+\s+other updates|"
    r"special offer|%\s*off|unsubscribe|view in browser|weekly digest|"
    r"your receipt from apple|security alert(?!.*(?:filing|court))|"
    r"intro interest|credit card offer|deal of the day)",
    re.I,
)

PROMO_BODY_RE = re.compile(
    r"(unsubscribe|view this email in your browser|manage preferences|"
    r"you(?:'re| are) receiving this (?:email|message) because)",
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


def is_kb_pollution_email(
    *,
    from_addr: str | None = None,
    subject: str | None = None,
    body_plain: str | None = None,
    relevance_status: str | None = None,
    matter_codes: list[str] | None = None,
    raw_category: str | None = None,
) -> bool:
    """True when email pollutes the active KB (triage, matcher, Leo context).

    Noise is archived out of gmail_messages — never linked, never on spine.
    Legal mail with agency/counsel signals overrides promo-shaped subjects.
    """
    if relevance_status == "noise":
        return True

    sender = from_addr or ""
    text = f"{subject or ''}\n{(body_plain or '')[:6000]}"
    has_legal_signal = bool(
        LEGAL_ACTOR_RE.search(sender)
        or LEGAL_ACTION_RE.search(text)
        or (matter_codes and len(matter_codes) > 0)
    )

    if NOISE_SENDER_RE.search(sender) and not has_legal_signal:
        return True
    if raw_category in NOISE_CATEGORIES and not has_legal_signal:
        return True
    if NOISE_SUBJECT_RE.search(subject or "") and not has_legal_signal:
        return True
    if (
        PROMO_BODY_RE.search(text)
        and not has_legal_signal
        and not LEGAL_ACTOR_RE.search(sender)
    ):
        return True
    if NOISE_SENDER_RE.search(text) and not has_legal_signal:
        return True
    return False


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
    if is_kb_pollution_email(
        from_addr=from_addr,
        subject=subject,
        body_plain=body_plain,
        relevance_status=relevance_status,
        matter_codes=matter_codes,
        raw_category=raw_category,
    ):
        return False

    if matter_codes:
        return True
    if case_file:
        return True
    if client_code and raw_category not in ("promotional", "system_alert", "personal"):
        return True
    if relevance_status and relevance_status not in ("unlinked", "noise"):
        return True

    sender = from_addr or ""
    if raw_category in ("bill", "receipt", "bank_statement"):
        return False

    text = f"{subject or ''}\n{(body_plain or '')[:6000]}"
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


def archive_gmail_noise(cur, row: dict, *, reason: str, archived_by: str) -> bool:
    """Move one active gmail row to gmail_messages_archived; scrub KB refs."""
    gid = row["id"]
    cur.execute(
        "DELETE FROM client_history WHERE source_table = 'gmail_messages' AND source_id = %s",
        (str(gid),),
    )
    cur.execute("DELETE FROM correspondence_links WHERE gmail_id = %s", (gid,))
    cur.execute(
        """
        INSERT INTO gmail_messages_archived (
            id, message_id, thread_id, from_addr, from_name, to_addrs, cc_addrs,
            subject, body_plain, body_html, sent_at, received_at, labels,
            has_attachments, attachment_refs, document_id, case_file,
            landtek_thread_id, relevance_score, relevance_reasons, ingested_at,
            provenance_level, raw_payload, matter_codes, archived_at, archived_reason,
            archived_by
        )
        SELECT
            id, message_id, thread_id, from_addr, from_name, to_addrs, cc_addrs,
            subject, body_plain, body_html, sent_at, received_at, labels,
            has_attachments, attachment_refs, document_id, case_file,
            landtek_thread_id, relevance_score,
            COALESCE(relevance_reasons, '{}'::text[]) || ARRAY[%s],
            ingested_at, provenance_level, raw_payload, matter_codes,
            now(), %s, %s
          FROM gmail_messages WHERE id = %s
        ON CONFLICT (message_id) DO UPDATE SET
            archived_at = now(),
            archived_reason = EXCLUDED.archived_reason,
            archived_by = EXCLUDED.archived_by
        """,
        (reason, reason, archived_by, gid),
    )
    cur.execute("DELETE FROM gmail_messages WHERE id = %s", (gid,))
    return True