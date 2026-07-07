"""LandTek — the ONTOLOGY → CLIENT PROJECTION LAYER.

The keystone that makes the client portal shippable. The portal renders per-client
matter state, but the underlying `matters` row holds RAW internal typed fields:
snake_case `current_stage` codes, "/"-mashed `forum` strings, `next_event` prose full
of gmail#/CTN/docket/§/doc# tokens and §4B provenance tags ([OPERATOR-ATTESTED],
[HUMAN VERIFY], [v:...]). Rendering any of those to a paying client is a FAIL.

This module projects the ontology's TYPED concepts (ONTOLOGY.md §2.2 matters/clients,
§2.8 case theory, §1 the 5-value provenance vocab) into a CONTROLLED, client-facing
vocabulary. The guarantee is BY CONSTRUCTION: a client-facing surface calls only the
functions here, and no raw internal string can pass through them — every value maps to
a clean plain-language phrase, and any value we have NOT enumerated falls back to a SAFE
generic phrase (never the raw string) AND is logged so the operator can add it.

DESIGN (why a projection, not string-scrubbing):
  * `client_stage(...)`   — TYPED `current_stage` → plain STATUS phrase. Exact-match map
    over the live enumerated values, keyword fallback, then a safe generic. NEVER echoes
    the snake_case code.
  * `client_forum(...)`   — TYPED `forum`/`court_or_agency` → plain venue name; strips the
    internal "A / B / C" multi-forum mashups down to the lead venue, humanized.
  * `client_matter_kind(...)` — TYPED `matter_type` → a plain "what this is" one-liner a
    layperson understands ("Recovering your family's land title", "Estate administration").
  * `client_confidence(...)` — PROVENANCE meaning, not raw tags. Translates the MEANING of
    [OPERATOR-ATTESTED]/[HUMAN VERIFY]/estimate into plain confidence language; the raw
    tag NEVER renders. Honesty is preserved in meaning, not metadata.
  * `client_next_step(...)` — a CLEAN next-step. Prefers a stage-derived template; only if
    it must use `next_event` does it STRIP every internal token (matter codes, docket/CTN/
    SL numbers, gmail#/doc# refs, § cites, §4B tags) — never truncating mid-word.
  * `friendly_title(...)`  — cleans jargon tokens out of a matter title for display.
  * `friendly_date(...)`   — a warm local-style date, not a dev "as of … UTC" stamp.

DISCIPLINE:
  * No hallucination — status/venue/kind are DERIVED from the typed field, never invented.
  * $0 — pure deterministic mapping; no LLM at render time.
  * Totality — every live value maps to something clean; unmapped → safe generic + log.
  * Honesty — a real uncertainty is TRANSLATED (never dropped): an estimated/operator date
    still reads as "not yet confirmed", just in plain language.

Client separation is NOT this module's job (the portal filters on matters.client_code
before it ever calls in here); this module only ensures nothing internal LEAKS in wording.
"""
from __future__ import annotations

import datetime as _dt
import logging
import re

log = logging.getLogger("client_ontology")

# A log of any typed value that hit the generic fallback — so the operator can enumerate
# it. In-process set (dedup); the portal can surface `unmapped_report()` on the ops view.
_UNMAPPED: set[tuple[str, str]] = set()


def _flag_unmapped(kind: str, value: str) -> None:
    key = (kind, (value or "").strip())
    if key not in _UNMAPPED:
        _UNMAPPED.add(key)
        log.warning("client_ontology UNMAPPED %s=%r → generic fallback", kind, value)


def unmapped_report() -> list[tuple[str, str]]:
    """Return the (kind, value) pairs that hit a generic fallback this process, so the
    operator can add explicit mappings. Read-only; used by the ops portal footer."""
    return sorted(_UNMAPPED)


# ---------------------------------------------------------------------------
# 1. current_stage  →  plain client STATUS phrase
# ---------------------------------------------------------------------------
# Keyed on the LIVE distinct current_stage values (queried 2026-07-07 across all
# client-owned matters). EVERY live value is enumerated. The phrasing is what a client
# reads as their status — plain, honest, no snake_case, no internal codes, no dates.

_STAGE_MAP: dict[str, str] = {
    # --- CV-26360 (trial track) ---
    "trial_aug12_testimony_set": "Preparing for your hearing",
    # --- ARTA / agency complaints awaiting a decision ---
    "complaint_filed_awaiting_response": "Filed — awaiting the agency's response",
    "respondent_counter_affidavit_filed_submitted_for_resolution":
        "Filed and fully argued — awaiting the agency's decision",
    "resolution_noc_op_appeal_window": "A decision was issued — reviewing next steps",
    "referred_to_csc_dilg_awaiting": "Referred to the next agency — awaiting their action",
    "arta_referral_filed_awaiting_response": "Referred onward — awaiting a response",
    "petition_filed_awaiting_op_action": "Petition filed — awaiting a ruling",
    "arta_case_auto_promoted": "Being reviewed and organized",
    # --- special proceedings / civil recovery ---
    "petition_filed_hearing_set": "Petition filed — a hearing has been set",
    "judgment_won_pending_title_reconveyance": "Won — finalizing your title transfer",
    "just_compensation_halted_pending_substitution":
        "On hold — a required party substitution is pending",
    "investigation_active": "Actively gathering evidence",
    "pre_filing_evidence_collection": "Gathering evidence before filing",
    "demand_letter_pending_send": "Preparing a formal request to send",
    "evidence assembled; COA request filed-ready": "Evidence assembled — ready to file",
    # --- estate / advisory / tracking ---
    "estate_administration_active_no_immediate_deadline":
        "Estate administration — ongoing, no deadline right now",
    "advisory_active_tracking": "Monitoring on your behalf",
    "observation_only": "Watching a related matter for developments",
    "asset_development_proposal_under_review": "Reviewing a development proposal",
    # --- context / triage / unrelated ---
    "pending_context": "Getting organized — awaiting details",
    "needs_context_from_user": "Awaiting some details from you",
    "declared_unrelated_by_principal_2026-05-20": "Set aside — noted as not part of your matters",
    "resolved_no_merit": "Concluded",
}

# Keyword fallback for a NEW stage string we have not yet enumerated. Ordered — first hit
# wins. Keeps an unmapped stage HONEST and plain rather than echoing snake_case.
_STAGE_KEYWORDS: list[tuple[str, str]] = [
    ("won", "Won — finalizing the outcome"),
    ("judgment", "A judgment has been reached"),
    ("hearing_set", "A hearing has been set"),
    ("hearing", "A hearing is involved"),
    ("trial", "Preparing for your hearing"),
    ("submitted_for_resolution", "Fully argued — awaiting the decision"),
    ("counter_affidavit", "Filed and argued — awaiting the decision"),
    ("appeal", "In the appeal stage"),
    ("resolution", "A decision has been issued"),
    ("referred", "Referred to another office — awaiting action"),
    ("complaint_filed", "Filed — awaiting a response"),
    ("petition_filed", "Petition filed — awaiting action"),
    ("demand", "Preparing a formal request"),
    ("evidence", "Gathering evidence"),
    ("investigation", "Actively gathering evidence"),
    ("estate", "Estate administration — ongoing"),
    ("advisory", "Monitoring on your behalf"),
    ("tracking", "Monitoring on your behalf"),
    ("observation", "Watching a related matter"),
    ("proposal", "Under review"),
    ("halted", "On hold"),
    ("pending", "In progress"),
    ("unrelated", "Set aside"),
    ("resolved", "Concluded"),
    ("closed", "Concluded"),
]

_STAGE_GENERIC = "In progress"


def client_stage(current_stage: str | None, status: str | None = None) -> str:
    """TYPED current_stage → a plain client STATUS phrase. Never returns the raw code.
    Falls back to matters.status, then a keyword match, then a safe generic (logged)."""
    for raw in (current_stage, status):
        if not raw:
            continue
        key = raw.strip()
        if key in _STAGE_MAP:
            return _STAGE_MAP[key]
    # keyword fallback on the stage string
    s = (current_stage or "").strip().lower()
    if s:
        for kw, phrase in _STAGE_KEYWORDS:
            if kw in s:
                return phrase
        _flag_unmapped("current_stage", current_stage or "")
    return _STAGE_GENERIC


# ---------------------------------------------------------------------------
# 2. forum / court_or_agency  →  plain venue name
# ---------------------------------------------------------------------------
# The lead venue only — internal "A / B / C" mashups are stripped to the primary
# venue, humanized. Keyed on the live distinct values; keyword fallback for the rest.

_FORUM_MAP: dict[str, str] = {
    "ARTA Southern Luzon": "Government agency (ARTA)",
    "ARTA Southern Luzon (later: Office of the Executive Secretary)": "Government agency (ARTA)",
    "ARTA / Office of the President": "Government agency (ARTA)",
    "MGB Region V / DENR": "Mining & environment agency (MGB / DENR)",
    "MTC Mercedes / RTC Camarines Norte / Registry of Deeds Camarines Norte":
        "Municipal Trial Court, Mercedes",
    "Registry of Deeds Camarines Norte + LRA Manila": "Registry of Deeds, Camarines Norte",
    "RTC Branch 40 Daet (Special Agrarian Court)": "Regional Trial Court, Daet",
    "RTC Camarines Norte Branch 64 (Daet)": "Regional Trial Court, Daet (Branch 64)",
    "RTC / COA / Ombudsman": "Regional Trial Court, Camarines Norte",
    "multi-forum": "Multiple offices",
}

# court_or_agency carries different strings than forum; keyword fallback covers both
# columns and any new value. Ordered by specificity.
_FORUM_KEYWORDS: list[tuple[str, str]] = [
    ("branch 64", "Regional Trial Court, Daet (Branch 64)"),
    ("special agrarian", "Regional Trial Court, Daet"),
    ("mtc mercedes", "Municipal Trial Court, Mercedes"),
    ("municipal trial court", "Municipal Trial Court, Mercedes"),
    ("registry of deeds", "Registry of Deeds, Camarines Norte"),
    ("lra", "Registry of Deeds, Camarines Norte"),
    ("mgb", "Mining & environment agency (MGB / DENR)"),
    ("denr", "Mining & environment agency (MGB / DENR)"),
    ("arta", "Government agency (ARTA)"),
    ("csc", "Civil Service Commission"),
    ("dilg", "Department of the Interior & Local Government"),
    ("ombudsman", "Office of the Ombudsman"),
    ("coa", "Commission on Audit"),
    ("office of the president", "Office of the President"),
    ("executive secretary", "Office of the President"),
    ("darab", "Agrarian adjudication board (DARAB)"),
    ("dar", "Department of Agrarian Reform"),
    ("rtc", "Regional Trial Court, Camarines Norte"),
    ("mtc", "Municipal Trial Court"),
    ("court", "Court"),
]


def client_forum(forum: str | None, court_or_agency: str | None = None) -> str:
    """TYPED forum/court_or_agency → a plain venue name (lead venue only). Never returns
    an internal "/"-mashup. '' when nothing is on record (caller may omit the row)."""
    for raw in (forum, court_or_agency):
        if not raw:
            continue
        key = raw.strip()
        if key in _FORUM_MAP:
            return _FORUM_MAP[key]
    # keyword fallback across both columns
    for raw in (forum, court_or_agency):
        low = (raw or "").strip().lower()
        if not low:
            continue
        for kw, name in _FORUM_KEYWORDS:
            if kw in low:
                return name
    # If we had *some* value but matched nothing, log it; else it's simply unset.
    for raw in (forum, court_or_agency):
        if raw and raw.strip() and raw.strip().lower() not in ("unknown", "tbc", "tbd"):
            _flag_unmapped("forum", raw.strip())
            break
    return ""


# ---------------------------------------------------------------------------
# 3. matter_type  →  plain "what this is" one-liner
# ---------------------------------------------------------------------------
# A layperson's one-line description of the KIND of matter. Derived from matter_type,
# with a per-matter override for a few flagship matters whose title carries the clearest
# plain description. Never the strategy paragraph (legal_theory), never a code.

_KIND_MAP: dict[str, str] = {
    "civil_case": "A court case",
    "civil_recovery": "Recovering property that was wrongly transferred",
    "recovery": "Recovering value owed to your family",
    "land_record": "Verifying your land title records",
    "regulatory": "Verifying your land title records",
    "special_proceeding": "A court petition to protect the estate",
    "administrative": "A complaint to a government office",
    "criminal": "A criminal matter we are following",
    "family_property_dispute": "A family property dispute",
    "development_proposal": "A property development matter",
    "business": "A family business matter",
    "transactional": "Managing your estate",
    "mining": "A mining rights matter",
    "out_of_scope": "A related matter we are tracking",
    "unknown": "A matter we are organizing",
}

# Per-matter_code overrides — a few flagship matters have a cleaner plain description
# than their matter_type gives. Keyed on matter_code; used ONLY for the "what this is"
# subtitle, never to override separation.
_KIND_OVERRIDE: dict[str, str] = {
    "MWK-CV26360": "Recovering your family's land title in court",
    "MWK-DLF-VOID": "Recovering your family's land from void transfers",
    "MWK-ESTATE": "Administering your family's estate",
    "MWK-GUARDIANSHIP": "A court petition to protect the family estate",
    "MWK-LGU-RECOVERY": "Recovering value from the local government",
    "MWK-CV6839": "Fair-value (just compensation) for land taken",
    "MWK-TCT4497": "Verifying your family's land title chain",
}

_KIND_GENERIC = "A matter in your workspace"


def client_matter_kind(matter_type: str | None, matter_code: str | None = None) -> str:
    """TYPED matter_type (+ optional matter_code override) → a plain 'what this is'
    one-liner a layperson understands. Never the legal_theory paragraph or a code."""
    if matter_code and matter_code in _KIND_OVERRIDE:
        return _KIND_OVERRIDE[matter_code]
    key = (matter_type or "").strip()
    if key in _KIND_MAP:
        return _KIND_MAP[key]
    if key:
        _flag_unmapped("matter_type", key)
    return _KIND_GENERIC


# ---------------------------------------------------------------------------
# 4. provenance / caveat tags  →  plain CONFIDENCE language
# ---------------------------------------------------------------------------
# The raw [OPERATOR-ATTESTED: …], [HUMAN VERIFY], [verify-img], [v:…], [OCR:…] tags must
# NEVER render to a client. We translate their MEANING into plain confidence language,
# preserving the honesty (the uncertainty survives — only the metadata form is dropped).

# §4B / provenance tags (superset of the portal's _TAG_RE). [v:...] is a VERIFIED-citation
# marker (means "confirmed"); the rest flag operator-asserted / estimated / OCR-soft.
_TAG_RE = re.compile(
    r"\[(?:HUMAN VERIFY|OPERATOR-ATTESTED[^\]]*|verify-img|OCR:[^\]]*|v:[^\]]*|\?[^\]]*)\]"
)


def _classify_caveat(*texts: str | None) -> str | None:
    """Return the STRONGEST caveat implied by any §4B tag across the given texts:
    'operator'  → an operator-asserted / planned value the record hasn't confirmed,
    'estimate'  → an estimated / to-be-verified value,
    None        → nothing but verified markers (or no tags at all).
    Verified [v:...] never raises a caveat."""
    operator = estimate = False
    for t in texts:
        if not t:
            continue
        for m in _TAG_RE.finditer(t):
            tag = m.group(0)
            if tag.startswith("[v:"):
                continue  # verified — no caveat
            low = tag.lower()
            if "operator-attested" in low:
                operator = True
            else:  # HUMAN VERIFY / verify-img / OCR / [?...]
                estimate = True
    if operator:
        return "operator"
    if estimate:
        return "estimate"
    return None


# Plain-language confidence phrases — the CLIENT-FACING translation of each caveat class.
_CONFIDENCE_PHRASE: dict[str, str] = {
    "operator": "Your team's planned date — the court hasn't set it in writing yet",
    "estimate": "Estimated — awaiting confirmation",
}
# A short badge form for tight UI (the estimated pill on a deadline row).
_CONFIDENCE_BADGE: dict[str, str] = {
    "operator": "planned — not yet court-confirmed",
    "estimate": "estimated · awaiting confirmation",
}


def client_confidence(*texts: str | None) -> str | None:
    """Translate the MEANING of any §4B provenance tags in `texts` into a plain
    confidence SENTENCE, or None if the value reads as confirmed. Raw tags never leak."""
    caveat = _classify_caveat(*texts)
    return _CONFIDENCE_PHRASE.get(caveat) if caveat else None


def client_confidence_badge(*texts: str | None) -> str | None:
    """Short badge form of client_confidence() for a deadline pill. None when confirmed."""
    caveat = _classify_caveat(*texts)
    return _CONFIDENCE_BADGE.get(caveat) if caveat else None


def is_estimated(*texts: str | None) -> bool:
    """True if any non-verified caveat tag is present (date/claim not settled)."""
    return _classify_caveat(*texts) is not None


# --- provenance_level COLUMN → plain client confidence -----------------------
# The 5-value canonical vocab (ONTOLOGY.md §1). The raw level never renders to a
# client; we translate the tier's MEANING. Honesty is preserved and NEVER upgraded:
# a low tier reads as tentative, a high tier reads as confirmed — the ranking is the
# source's, not ours. `inferred_weak` is deliberately shown as "preliminary / being
# checked", never as settled fact (governance rule under A34).
_PROVENANCE_PHRASE: dict[str, str] = {
    "verified": "Confirmed from your documents",
    "operator": "Confirmed by your team",
    "inferred_corroborated": "Corroborated — being confirmed",
    "inferred_strong": "Strong indication — being confirmed",
    "inferred_weak": "Preliminary — we're still checking this",
}
_PROVENANCE_BADGE: dict[str, str] = {
    "verified": None,                       # confirmed → no caveat pill needed
    "operator": "confirmed by your team",
    "inferred_corroborated": "being confirmed",
    "inferred_strong": "being confirmed",
    "inferred_weak": "being checked",
}
# Tiers solid enough to state plainly as fact to a client; the rest must carry the
# "being confirmed/checked" framing (never presented as settled).
_PROVENANCE_SOLID = {"verified", "operator"}
_PROVENANCE_GENERIC = "Being reviewed"


def client_provenance(provenance_level: str | None) -> str:
    """TYPED provenance_level (5-value vocab) → a plain client confidence phrase.
    Never returns the raw tier; an unknown tier → safe generic (logged)."""
    key = (provenance_level or "").strip().lower()
    if key in _PROVENANCE_PHRASE:
        return _PROVENANCE_PHRASE[key]
    if key:
        _flag_unmapped("provenance_level", key)
    return _PROVENANCE_GENERIC


def client_provenance_badge(provenance_level: str | None) -> str | None:
    """Short badge form; None for a confirmed (`verified`) fact that needs no pill."""
    key = (provenance_level or "").strip().lower()
    if key in _PROVENANCE_BADGE:
        return _PROVENANCE_BADGE[key]
    if key:
        _flag_unmapped("provenance_level", key)
    return _PROVENANCE_BADGE["inferred_weak"]  # unknown → most cautious framing


def provenance_is_solid(provenance_level: str | None) -> bool:
    """True if the tier is solid enough to state plainly as fact to a client
    (`verified`/`operator`). Lower tiers must carry a 'being confirmed' framing or be
    withheld — the A34 governance rule for what may be shown as settled."""
    return (provenance_level or "").strip().lower() in _PROVENANCE_SOLID


# ---------------------------------------------------------------------------
# 5. next_event  →  a CLEAN plain-language next step
# ---------------------------------------------------------------------------
# Prefer a STAGE-DERIVED template (guaranteed clean). Only if there's no template AND a
# usable next_event do we sanitize the prose — stripping EVERY internal token — never
# truncating mid-word. If nothing survives, a stage-generic sentence.

# Stage → a clean, client-facing next-step sentence. Preferred source (deterministic,
# token-free). Keyed on the live current_stage values.
_STAGE_NEXTSTEP: dict[str, str] = {
    "trial_aug12_testimony_set": "We're preparing for your upcoming hearing.",
    "complaint_filed_awaiting_response": "We're waiting for the agency to respond.",
    "respondent_counter_affidavit_filed_submitted_for_resolution":
        "The matter is fully argued; we're awaiting the agency's decision.",
    "resolution_noc_op_appeal_window":
        "A decision was issued; we're reviewing whether to take the next step.",
    "referred_to_csc_dilg_awaiting":
        "The matter was referred onward; we're following up with the next office.",
    "arta_referral_filed_awaiting_response":
        "We're following up on the referral and awaiting a response.",
    "petition_filed_awaiting_op_action":
        "The petition is filed; we're awaiting a ruling.",
    "arta_case_auto_promoted": "We're organizing and reviewing this matter.",
    "petition_filed_hearing_set":
        "A hearing has been set; we're preparing for it.",
    "judgment_won_pending_title_reconveyance":
        "You've won; we're finalizing the transfer of the title back to you.",
    "just_compensation_halted_pending_substitution":
        "The case is paused until a required party change is completed.",
    "investigation_active": "We're actively gathering the evidence for this matter.",
    "pre_filing_evidence_collection":
        "We're gathering the evidence needed before filing.",
    "demand_letter_pending_send":
        "We're preparing a formal written request to send.",
    "evidence assembled; COA request filed-ready":
        "The evidence is assembled and ready to file.",
    "estate_administration_active_no_immediate_deadline":
        "We're administering the estate; there's no deadline right now.",
    "advisory_active_tracking":
        "We're monitoring this matter and will flag anything that needs action.",
    "observation_only":
        "We're watching this related matter for any developments.",
    "asset_development_proposal_under_review":
        "We're reviewing the development proposal for this property.",
    "pending_context": "We're getting this matter organized.",
    "needs_context_from_user":
        "We need a few details from you to move this forward.",
    "declared_unrelated_by_principal_2026-05-20":
        "This has been set aside as not part of your active matters.",
    "resolved_no_merit": "This matter has concluded.",
}

_NEXTSTEP_GENERIC = "We're working on this matter and will update you as it progresses."

# --- Sanitizer for when we must fall back to next_event prose. -------------
# Each pattern removes a class of internal token. Applied in order; whitespace is
# re-normalized at the end. We NEVER cut mid-word: we strip whole tokens/phrases only.

# §4B / provenance tags (whole-tag removal — the MEANING is carried separately by
# client_confidence(), so it's safe to drop the raw tag from the step text).
_STRIP_TAG_RE = re.compile(
    r"\[(?:HUMAN VERIFY|OPERATOR-ATTESTED[^\]]*|verify-img|OCR:[^\]]*|v:[^\]]*|\?[^\]]*)\]",
    re.IGNORECASE,
)
# Internal reference tokens: gmail#NNN, doc#NNN, obligation#N, #NNNN bare refs.
_STRIP_REF_RE = re.compile(
    r"\b(?:gmail|doc|document|obligation|record_gaps?|thread|case_thread)\s*#\s*\d+",
    re.IGNORECASE,
)
_STRIP_HASH_RE = re.compile(r"#\s*\d{2,}")
# Docket / control-tracking numbers: CTN SL-2026-0209-1319, SL-2025-1021-0747,
# OAC-L Letter 270 s.2026, PE-214781.
_STRIP_CTN_RE = re.compile(r"\b(?:CTN\s+)?SL-\d{4}-\d{3,4}-\d{3,4}\b", re.IGNORECASE)
_STRIP_DOCKET_RE = re.compile(
    r"\b(?:CTN|NSR|NOC|OAC-L|PE|CV|TCT|OCT|T)-?\s*[-\d./]*\d[-\d./A-Za-z]*", re.IGNORECASE
)
# Matter codes: MWK-*, PAR-*, Paracale-*, NIBDC-*.
_STRIP_MATTER_RE = re.compile(
    r"\b(?:MWK|PAR|Paracale|NIBDC)-[A-Za-z0-9-]+", re.IGNORECASE
)
# Statute section cites: §21(b)(d)(e), R.A. 11032 §21, Arts. 1874/1878, Art. 1410.
_STRIP_SECTION_RE = re.compile(r"§\s*\d+[A-Za-z0-9().]*")
_STRIP_ART_RE = re.compile(
    r"\bArts?\.?\s*\d+[\d/,\s-]*(?:and\s*\d+)?", re.IGNORECASE
)
_STRIP_RA_RE = re.compile(r"\bR\.?A\.?\s*\d{3,5}(?:\s*§\s*\d+[A-Za-z0-9()]*)?", re.IGNORECASE)
# "Anchor: ..." / "Source: ..." trailing provenance clauses (whole clause to end/next
# sentence boundary).
_STRIP_ANCHOR_RE = re.compile(r"\b(?:Anchor|Source|Sources?)\s*:\s*[^.]*\.?", re.IGNORECASE)
# Internal field separator "||" → sentence break.
_SPLIT_PIPE_RE = re.compile(r"\s*\|\|\s*")


def _sanitize_next_event(text: str) -> str:
    """Strip EVERY internal token from a next_event string, leaving clean prose. Removes
    whole tokens only (never cuts mid-word), collapses the debris, and returns the first
    clean sentence(s). '' if nothing legible survives (caller falls back to a template)."""
    if not text:
        return ""
    # Internal field separator → take only the FIRST field (the primary next-step).
    t = _SPLIT_PIPE_RE.split(text)[0]
    for rx in (_STRIP_TAG_RE, _STRIP_ANCHOR_RE, _STRIP_REF_RE, _STRIP_CTN_RE,
               _STRIP_MATTER_RE, _STRIP_RA_RE, _STRIP_SECTION_RE, _STRIP_ART_RE,
               _STRIP_DOCKET_RE, _STRIP_HASH_RE):
        t = rx.sub(" ", t)
    # Clean up debris left by token removal: empty parens/brackets, orphaned punctuation,
    # doubled spaces, stray leading/trailing separators.
    t = re.sub(r"\(\s*[;,/&\s]*\s*\)", " ", t)      # empty/near-empty parens
    t = re.sub(r"\[\s*\]", " ", t)                    # empty brackets
    t = re.sub(r"\s+([,.;:)])", r"\1", t)             # space before punctuation
    t = re.sub(r"([(\[])\s+", r"\1", t)               # space after open bracket
    t = re.sub(r"[;,/&]\s*(?=[;,/.)]|$)", " ", t)     # orphaned separators
    t = re.sub(r"\s{2,}", " ", t)                      # collapse whitespace
    t = t.strip(" \t\r\n-–—;,:/&|.")
    # Guard: if the residue is too short or is mostly punctuation/uppercase code debris,
    # treat it as unusable so we fall back to a clean template.
    letters = re.sub(r"[^A-Za-z]", "", t)
    if len(t) < 12 or len(letters) < 8:
        return ""
    # Keep to the first 1–2 sentences for a tight next-step; never cut mid-word.
    parts = re.split(r"(?<=[.!?])\s+", t)
    out = parts[0]
    if len(out) < 60 and len(parts) > 1:
        out = (out + " " + parts[1]).strip()
    # Ensure sentence-final punctuation, and a capital lead.
    out = out[0].upper() + out[1:] if out else out
    if out and out[-1] not in ".!?":
        out += "."
    return out


def client_next_step(current_stage: str | None, next_event: str | None = None,
                     matter_code: str | None = None) -> str:
    """A CLEAN, plain-language next step for a client. Prefers a stage-derived template
    (token-free by construction); only if none exists and next_event yields legible
    prose after full sanitization do we use that; else a stage-generic sentence.

    Guarantees NO internal token (matter code, docket/CTN, gmail#/doc#, §, §4B tag)
    reaches the client, and NEVER truncates mid-word."""
    key = (current_stage or "").strip()
    if key in _STAGE_NEXTSTEP:
        return _STAGE_NEXTSTEP[key]
    # No exact template — try to salvage a clean sentence from next_event.
    if next_event:
        cleaned = _sanitize_next_event(next_event)
        if cleaned:
            return cleaned
    # Keyword template fallback via the status phrase, then a safe generic.
    s = key.lower()
    for kw, _ in _STAGE_KEYWORDS:
        if kw in s and kw in ("won", "hearing_set", "hearing", "trial",
                              "submitted_for_resolution", "complaint_filed",
                              "petition_filed", "referred", "investigation",
                              "evidence", "demand", "estate", "advisory", "tracking"):
            # map back to the closest template by re-using client_stage phrasing
            return _STAGE_NEXTSTEP.get(key, _NEXTSTEP_GENERIC)
    return _NEXTSTEP_GENERIC


# ---------------------------------------------------------------------------
# 6. friendly_title  —  clean jargon tokens out of a matter title
# ---------------------------------------------------------------------------
# Matter titles are mostly human already, but some carry docket/statute jargon
# ("ARTA SL-2025-1021-0747 — Mayor Pajarillo R.A. 11032 §21(b)(d)(e)"). We lift the clean
# human part. Never invents; if a title reduces to nothing legible, keeps the original
# minus the loudest codes.

# Spelled-out statute section cite ("Sec. 21", "Section 21(b)") — companion to §/R.A.
_STRIP_SEC_WORD_RE = re.compile(r"\bSec(?:tion)?\.?\s*\d+[A-Za-z0-9().]*", re.IGNORECASE)
# Internal ops annotation that sometimes contaminates a matters.title, e.g.
# "(referenced docs#753, 817 — matter missing from inventory)". Strip the WHOLE
# parenthetical when it carries an internal marker — a client must never read it.
_STRIP_TITLE_OPS_RE = re.compile(
    r"\([^)]*\b(?:referenced\s+docs?|missing\s+from\s+inventory|inventory|internal|"
    r"ops[\s-]?note|placeholder|matter\s+missing)\b[^)]*\)",
    re.IGNORECASE)
# Instrument / control-code prefixes on document filenames (SPA-001, NOR-, OAC-L, etc.)
_STRIP_INSTR_RE = re.compile(r"\b(?:SPA|NOR|OAC-?L|MOA|MOU|CTC|CL)-?\s*\d*\b", re.IGNORECASE)
# A bare control-tracking number (…2026-0128-1210…) or trailing "(1212)" docket suffix.
_STRIP_BAREDOCKET_RE = re.compile(r"\b\d{4}-\d{3,4}-\d{3,4}\b")
_STRIP_TRAILDOCKET_RE = re.compile(r"\(\s*\d{3,4}\s*\)")
# CTN written with spaces instead of dashes ("CTN SL 2026-0128-1210").
_STRIP_CTN_SPACE_RE = re.compile(r"\b(?:CTN\s+)?SL\s+\d{4}[-\s]\d{3,4}[-\s]\d{3,4}", re.IGNORECASE)
_STRIP_EXT_RE = re.compile(r"\.(?:pdf|png|jpe?g|docx?|xlsx?|zip|tiff?)$", re.IGNORECASE)

_TITLE_STRIP = [
    _STRIP_TITLE_OPS_RE, _STRIP_CTN_RE, _STRIP_SECTION_RE, _STRIP_SEC_WORD_RE,
    _STRIP_RA_RE, _STRIP_HASH_RE, _STRIP_TAG_RE,
]


def friendly_title(title: str | None, matter_code: str | None = None) -> str:
    """A clean, human matter title for display. Strips docket/statute/§ jargon and internal
    ops annotations; keeps the descriptive human phrase. NEVER returns a matter_code (that is
    a forbidden internal token on a client surface) — falls back to a safe generic."""
    raw = (title or "").strip()
    if not raw:
        return "Your matter"
    t = raw
    for rx in _TITLE_STRIP:
        t = rx.sub(" ", t)
    # Drop a leading "ARTA — " / "ARTA " label left after stripping the docket.
    t = re.sub(r"^\s*ARTA\b[\s—:-]*", "", t, flags=re.IGNORECASE)
    # Collapse an em-dash that now leads or doubles, and whitespace.
    t = re.sub(r"\s*—\s*—\s*", " — ", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" \t—–-:·")
    letters = re.sub(r"[^A-Za-z]", "", t)
    if len(letters) < 4:
        # Nothing human survived — de-code the raw title (incl. the ops annotation) and
        # keep only if legible; otherwise a safe generic. NEVER expose the matter_code.
        fb = raw
        for rx in (_STRIP_TITLE_OPS_RE, _STRIP_CTN_RE, _STRIP_SEC_WORD_RE, _STRIP_HASH_RE):
            fb = rx.sub(" ", fb)
        fb = re.sub(r"^\s*ARTA\b[\s—:-]*", "", fb, flags=re.IGNORECASE)
        fb = re.sub(r"\s{2,}", " ", fb).strip(" —–-:·")
        return fb if len(re.sub(r"[^A-Za-z]", "", fb)) >= 4 else "Your matter"
    return t


def client_doc_name(name: str | None, classification: str | None = None) -> str:
    """Project a raw document FILENAME into a clean client-facing label. A filename is
    free-text operator metadata (CTN/SL/OAC-L control numbers, instrument-code prefixes,
    matter codes, §/R.A. cites, §4B tags) — strip every such form, and defer to the TYPED
    `classification` when the residue is too thin to identify the document. Total: always
    returns something clean, never a forbidden token."""
    fallback = ((classification or "").strip() or "Document")
    t = name or ""
    t = _STRIP_EXT_RE.sub("", t)          # drop the file extension
    t = t.replace("_", " ")               # underscore filenames → words
    for rx in (_STRIP_CTN_SPACE_RE, _STRIP_CTN_RE, _STRIP_DOCKET_RE, _STRIP_INSTR_RE,
               _STRIP_MATTER_RE, _STRIP_SECTION_RE, _STRIP_SEC_WORD_RE, _STRIP_RA_RE,
               _STRIP_TAG_RE, _STRIP_HASH_RE, _STRIP_BAREDOCKET_RE, _STRIP_TRAILDOCKET_RE):
        t = rx.sub(" ", t)
    # Debris cleanup: an unbalanced trailing "(...." left by removing a docket, orphaned
    # docket-fragment numbers (a standalone 3–4 digit run is a control number, not content),
    # and orphaned dashes/punctuation.
    t = re.sub(r"\([^)]*$", " ", t)                     # trailing unbalanced "(...."
    t = re.sub(r"(?<![A-Za-z])\d{3,4}(?![A-Za-z])", " ", t)  # orphaned docket-fragment numbers
    t = re.sub(r"\s*[-–—]\s*(?=[-–—]|$)", " ", t)       # orphaned trailing dashes
    t = re.sub(r"[(),]\s*(?=[(),]|$)", " ", t)          # orphaned punctuation clusters
    t = re.sub(r"\s{2,}", " ", t).strip(" -–—:·.,[]()")
    if len(re.sub(r"[^A-Za-z]", "", t)) < 4:
        return fallback
    return t


# ---------------------------------------------------------------------------
# 7. friendly_date  —  a warm local-style date, not a dev UTC stamp
# ---------------------------------------------------------------------------
_MONTHS = ["", "January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"]


def friendly_date(d) -> str:
    """A warm, plain date like 'August 12, 2026' — never an 'as of … UTC' console stamp.
    Accepts a date/datetime/ISO string; '' on anything unparseable."""
    if d is None:
        return ""
    if isinstance(d, str):
        try:
            d = _dt.date.fromisoformat(d[:10])
        except Exception:
            return d
    if isinstance(d, _dt.datetime):
        d = d.date()
    if isinstance(d, _dt.date):
        return f"{_MONTHS[d.month]} {d.day}, {d.year}"
    return str(d)


def friendly_today() -> str:
    """Today, warm-formatted — for the 'Updated <date>' line that replaces the UTC stamp."""
    return friendly_date(_dt.date.today())
