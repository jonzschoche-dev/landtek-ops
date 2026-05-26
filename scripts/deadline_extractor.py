#!/usr/bin/env python3
"""deadline_extractor.py — deterministic deadline extraction from inbound docs/emails.

NORTH STAR: zero hallucinations. This is a regex-only extractor (no LLM). Every
calendar_event it creates carries:

  - source_doc_id or source_email_id (back-reference for audit)
  - raw_clause (verbatim quote that triggered extraction)
  - extraction_method = 'regex' + a specific pattern name
  - deadline_kind (appeal | filing | hearing | response | compliance | other)
  - status = 'proposed' for inferred relative deadlines pending operator confirm,
             'scheduled' for explicitly-dated hearings/orders

Scope (last N days, default 60):
  1. documents where matter_code starts with MWK- or PAR- AND extracted_text matches
     deadline patterns
  2. gmail_messages where matter_codes is non-empty AND body_plain matches
     deadline patterns
  3. Idempotent: dedupe via (source_doc_id, source_email_id, raw_clause_hash)

Two passes:
  A) ABSOLUTE: "hearing on 14 May 2026 at 10:00 AM" → start_at = parsed datetime,
     status='scheduled'.
  B) RELATIVE: "within fifteen (15) days from notice of this Resolution" →
     receipt_anchor = sent_at (email) or document_date (doc) or created_at (fallback);
     deadline_at = anchor + N days; status='proposed' (operator confirms anchor).

CRITICAL DISCIPLINE:
  - INBOUND ONLY. Outbound letters Jonathan sent ("please respond within 15 days")
    impose deadlines on counterparties, not on us. We skip these via heuristic:
    doc/email is INBOUND if from_addr does NOT match jonzschoche OR the document
    extracted_text begins with an external agency letterhead (not Jonathan's).

Usage:
  python3 deadline_extractor.py                  # run once, last 60 days
  python3 deadline_extractor.py --days 30        # last 30 days
  python3 deadline_extractor.py --doc 707        # single document
  python3 deadline_extractor.py --email 38220    # single email
  python3 deadline_extractor.py --dry-run        # print, don't insert
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

DSN = os.environ.get(
    "PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
)
ACTOR = "deadline_extractor"

MANILA_TZ = timezone(timedelta(hours=8))

# ------------------------------------------------------------------------
# Pattern library
# ------------------------------------------------------------------------

# Numeric-word lookup for "fifteen (15)" style
NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty-five": 45, "sixty": 60,
}

# A. RELATIVE — strict legal-deadline patterns. Two flavors:
#    STRONG: clause anchors to "this Resolution/Order/Notice/Decision" → emit
#    WEAK:   clause anchors to generic "from notice/receipt" → emit ONLY if
#            preceded by directive language ("you may", "you shall", etc.)
RELATIVE_PATTERNS = [
    # Appeal window — STRONG anchor (this Resolution/Order/Decision)
    (
        "appeal_window_strong",
        re.compile(
            r"(?P<clause>(?:Notice\s+of\s+Appeal|appeal|petition\s+for\s+review)[^.]{0,200}?"
            r"within\s+(?:(?P<word>[a-z]+)\s*\(\s*)?(?P<n>\d{1,3})\s*\)?\s*"
            r"(?P<unit>calendar\s+|working\s+|business\s+)?days?"
            r"[^.]{0,80}?(?:from\s+notice\s+of\s+this\s+(?:resolution|order|decision|judgment)|"
            r"of\s+this\s+(?:resolution|order|decision|judgment)))",
            re.IGNORECASE | re.DOTALL,
        ),
        "appeal",
    ),
    # Appeal window — WEAK anchor (requires directive pre-context)
    (
        "appeal_window_weak",
        re.compile(
            r"(?P<clause>(?:Notice\s+of\s+Appeal|appeal\s+(?:to|with)|petition\s+for\s+review)[^.]{0,200}?"
            r"within\s+(?:(?P<word>[a-z]+)\s*\(\s*)?(?P<n>\d{1,3})\s*\)?\s*"
            r"(?P<unit>calendar\s+|working\s+|business\s+)?days?"
            r"[^.]{0,80}?from\s+(?:notice|receipt|service))",
            re.IGNORECASE | re.DOTALL,
        ),
        "appeal",
    ),
    # Comment/answer/counter-affidavit filing window
    (
        "comment_window",
        re.compile(
            r"(?P<clause>(?:file|submit|serve)\s+(?:your\s+)?(?:comment|answer|response|opposition|counter[-\s]?affidavit|reply|rejoinder)[^.]{0,140}?"
            r"within\s+(?:(?P<word>[a-z]+)\s*\(\s*)?(?P<n>\d{1,3})\s*\)?\s*"
            r"(?P<unit>calendar\s+|working\s+|business\s+)?days?"
            r"[^.]{0,80}?(?:from\s+(?:notice|receipt|service)|of\s+this\s+(?:order|resolution|notice)))",
            re.IGNORECASE | re.DOTALL,
        ),
        "filing",
    ),
    # "comply within N days" — needs directive pre-context
    (
        "compliance_window",
        re.compile(
            r"(?P<clause>(?:comply|compliance|submit)\s+(?:with\s+[^.]{0,80}?)?within\s+"
            r"(?:(?P<word>[a-z]+)\s*\(\s*)?(?P<n>\d{1,3})\s*\)?\s*"
            r"(?P<unit>calendar\s+|working\s+|business\s+)?days?"
            r"[^.]{0,80}?(?:from\s+(?:notice|receipt|service)|of\s+this\s+(?:order|resolution|notice)))",
            re.IGNORECASE | re.DOTALL,
        ),
        "compliance",
    ),
]

# Patterns that REQUIRE directive pre-context (weak anchor)
WEAK_ANCHOR_PATTERNS = {"appeal_window_weak", "compliance_window"}

# B. ABSOLUTE — hearing/conference on specific date
MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

ABSOLUTE_PATTERNS = [
    # "set for hearing on 14 May 2026 at 10:00 AM"
    (
        "hearing_on_date",
        re.compile(
            r"(?P<clause>(?:set|scheduled)\s+(?:for\s+)?(?:hearing|pre-?trial(?:\s+conference)?|conference)\s+"
            r"on\s+(?P<day>\d{1,2})\s+(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\s+(?P<year>20\d{2})"
            r"(?:\s+at\s+(?P<hour>\d{1,2})(?:[:.](?P<min>\d{2}))?\s*(?P<ampm>AM|PM|am|pm)?)?)",
            re.IGNORECASE,
        ),
        "hearing",
    ),
    # "hearing on May 14, 2026 at 10:00 AM"
    (
        "hearing_on_date_us",
        re.compile(
            r"(?P<clause>(?:set\s+for\s+|scheduled\s+for\s+)?hearing\s+"
            r"(?:is\s+)?(?:set\s+|scheduled\s+)?on\s+(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\s+(?P<day>\d{1,2}),?\s+(?P<year>20\d{2})"
            r"(?:\s+at\s+(?P<hour>\d{1,2})(?:[:.](?P<min>\d{2}))?\s*(?P<ampm>AM|PM|am|pm)?)?)",
            re.IGNORECASE,
        ),
        "hearing",
    ),
]

# Reject-context — clauses where a specific historical date appears in or right
# next to the clause are retrospective rule citations, not current directives.
HISTORICAL_DATE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*(?:19\d{2}|20[01]\d|202[0-5])\b",
    re.IGNORECASE,
)

# Directive pre-context — these phrases within 100 chars before a weak-anchor
# clause indicate the deadline is a directive (not a quoted rule).
DIRECTIVE_PRE = re.compile(
    r"(?i)(you\s+(?:may|shall|must|are|will)|"
    r"complainant\s+(?:may|shall|must|is\s+(?:directed|ordered))|"
    r"respondent\s+(?:may|shall|must|is\s+(?:directed|ordered))|"
    r"the\s+(?:movant|petitioner|complainant|respondent|parties)\s+(?:are|is)?\s*(?:may|shall|must|hereby)|"
    r"hereby\s+(?:directed|ordered|required|granted)|"
    r"you\s+are\s+hereby|"
    r"is\s+hereby\s+(?:directed|ordered|required)|"
    r"are\s+hereby\s+(?:directed|ordered|required)|"
    r"however,?\s+you|"  # Pajarillo: "However, you may file"
    r"wherefore,?\s+(?:premises|the\s+(?:movant|complainant|respondent))|"
    r"ordered\s+that)"
)


def has_directive_pre(text: str, m: re.Match, window: int = 140) -> bool:
    s = m.start("clause") if "clause" in m.groupdict() else m.start()
    pre = text[max(0, s - window):s]
    return bool(DIRECTIVE_PRE.search(pre))


def has_historical_date_nearby(text: str, m: re.Match, window: int = 60) -> bool:
    s = m.start("clause") if "clause" in m.groupdict() else m.start()
    e = m.end("clause") if "clause" in m.groupdict() else m.end()
    span = text[max(0, s - window):min(len(text), e + window)]
    return bool(HISTORICAL_DATE.search(span))


# Heuristics to identify INBOUND documents/emails
JONATHAN_EMAILS = re.compile(r"jonzschoche@gmail|zschoche@", re.IGNORECASE)
EXTERNAL_LETTERHEAD = re.compile(
    r"(ANTI-?RED\s*TAPE\s*AUTHORITY|REPUBLIC\s+OF\s+THE\s+PHILIPPINES.*(?:COURT|CIVIL\s+SERVICE|OFFICE\s+OF\s+THE\s+PRESIDENT|DEPARTMENT\s+OF\s+THE\s+INTERIOR|PENRO|MGB|DENR|MUNICIPAL\s+TRIAL\s+COURT|REGIONAL\s+TRIAL\s+COURT|OFFICE\s+OF\s+THE\s+BAR\s+CONFIDANT|SUPREME\s+COURT|COURT\s+OF\s+APPEALS|SANDIGANBAYAN|OMBUDSMAN)|COMMISSION\s+ON\s+AUDIT|CIVIL\s+SERVICE\s+COMMISSION)",
    re.IGNORECASE | re.DOTALL,
)
# Jonathan-as-author letterhead (outbound)
JONATHAN_AUTHOR = re.compile(
    r"^\s*(JONATHAN\s+(?:PAUL\s+)?ZSCHOCHE|Jonathan\s+P?\.?\s*Zschoche)[^\n]{0,80}\n[^\n]{0,80}(Attorney-?in-?Fact|Dasmari)",
    re.IGNORECASE,
)


# ------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------

def parse_num(word: str | None, num: str) -> int:
    """Return integer; prefer numeric form, fall back to word form."""
    try:
        n = int(num)
        if n > 0 and n <= 365:
            return n
    except (TypeError, ValueError):
        pass
    if word and word.lower() in NUM_WORDS:
        return NUM_WORDS[word.lower()]
    return 0


def parse_absolute(match: re.Match) -> datetime | None:
    """Parse named groups (day, month, year, hour, min, ampm) → tz-aware datetime."""
    gd = match.groupdict()
    try:
        day = int(gd["day"])
        month = MONTH_MAP[gd["month"].lower()]
        year = int(gd["year"])
        hour = int(gd.get("hour") or 9)
        minute = int(gd.get("min") or 0)
        ampm = (gd.get("ampm") or "").lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        return datetime(year, month, day, hour, minute, tzinfo=MANILA_TZ)
    except (KeyError, ValueError, TypeError):
        return None


def is_inbound_doc(extracted_text: str) -> bool:
    """Heuristic: does this look like an inbound document (deadline runs against us)?"""
    if not extracted_text:
        return False
    head = extracted_text[:1500]
    if JONATHAN_AUTHOR.search(head):
        return False  # Jonathan wrote it → outbound
    if EXTERNAL_LETTERHEAD.search(head):
        return True
    # Court / agency reference patterns even if letterhead is OCR-fuzzy
    if re.search(r"(CTN\s*SL-|Civil\s+Case\s+No|G\.?R\.?\s+No|CA-G\.?R\.?\s+SP|Order\s+dated|Resolution\s+dated)", head, re.IGNORECASE):
        # Could still be outbound (Jonathan replying), check for author signal
        if JONATHAN_AUTHOR.search(head):
            return False
        return True
    return False


def is_inbound_email(from_addr: str | None) -> bool:
    if not from_addr:
        return False
    return not JONATHAN_EMAILS.search(from_addr)


def normalize_unit(unit: str | None) -> str:
    if not unit:
        return "calendar"
    u = unit.strip().lower()
    if "work" in u:
        return "working"
    if "bus" in u:
        return "business"
    if "cal" in u:
        return "calendar"
    return "calendar"


def add_days(anchor: datetime, n: int, unit: str) -> datetime:
    """Add N days to anchor. Working/business days skip weekends.
    PH legal practice: 'days' default is calendar days unless prefixed."""
    if unit in ("working", "business"):
        d = anchor
        added = 0
        while added < n:
            d = d + timedelta(days=1)
            if d.weekday() < 5:  # 0=Mon..4=Fri
                added += 1
        return d
    return anchor + timedelta(days=n)


def clause_hash(s: str) -> str:
    return hashlib.sha256(s.strip().encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------------

@dataclass
class Extraction:
    title: str
    description: str
    start_at: datetime
    deadline_kind: str  # appeal | filing | hearing | response | compliance | other
    raw_clause: str
    pattern_name: str
    confidence: float
    status: str  # 'scheduled' or 'proposed'
    related_case: str | None
    matter_code: str | None
    source_doc_id: int | None
    source_email_id: int | None


# ------------------------------------------------------------------------
# Core extraction
# ------------------------------------------------------------------------

def extract_from_text(
    text: str,
    *,
    anchor_date: datetime,
    matter_code: str | None,
    related_case: str | None,
    source_doc_id: int | None = None,
    source_email_id: int | None = None,
) -> list[Extraction]:
    """Run all patterns over text; return Extraction[] for each unique deadline."""
    out: list[Extraction] = []
    if not text:
        return out
    seen_clauses: set[str] = set()
    seen_results: set[tuple[str, str]] = set()  # (kind, YYYY-MM-DD)
    seen_spans: list[tuple[int, int]] = []  # to suppress overlapping matches

    def span_overlaps(m: re.Match) -> bool:
        s = m.start("clause") if "clause" in m.groupdict() else m.start()
        e = m.end("clause") if "clause" in m.groupdict() else m.end()
        for (a, b) in seen_spans:
            if not (e < a or s > b):
                return True
        seen_spans.append((s, e))
        return False

    # ABSOLUTE first (more specific, higher confidence)
    for name, pat, kind in ABSOLUTE_PATTERNS:
        for m in pat.finditer(text):
            dt = parse_absolute(m)
            if not dt:
                continue
            # Skip past dates (anything before today minus 1 day)
            if dt < datetime.now(MANILA_TZ) - timedelta(days=1):
                continue
            if span_overlaps(m):
                continue
            clause = " ".join(m.group("clause").split())[:300]
            key = clause_hash(clause.lower())
            if key in seen_clauses:
                continue
            seen_clauses.add(key)
            result_key = (kind, dt.strftime("%Y-%m-%d"))
            if result_key in seen_results:
                continue
            seen_results.add(result_key)
            title = f"Hearing — {dt.strftime('%d %b %Y %H:%M')}"
            if matter_code:
                title = f"Hearing ({matter_code}) — {dt.strftime('%d %b %Y %H:%M')}"
            out.append(Extraction(
                title=title,
                description=f"Auto-extracted hearing date.\n\nVerbatim clause:\n  \"{clause}\"\n\nPattern: {name}",
                start_at=dt,
                deadline_kind=kind,
                raw_clause=clause,
                pattern_name=name,
                confidence=0.85,
                status="scheduled",
                related_case=related_case,
                matter_code=matter_code,
                source_doc_id=source_doc_id,
                source_email_id=source_email_id,
            ))

    # RELATIVE
    for name, pat, kind in RELATIVE_PATTERNS:
        for m in pat.finditer(text):
            gd = m.groupdict()
            n = parse_num(gd.get("word"), gd.get("n", ""))
            if n <= 0 or n > 365:
                continue
            # Reject retrospective citations (historical date in/near clause)
            if has_historical_date_nearby(text, m):
                continue
            # Weak-anchor patterns require explicit directive pre-context
            if name in WEAK_ANCHOR_PATTERNS and not has_directive_pre(text, m):
                continue
            if span_overlaps(m):
                continue
            unit = normalize_unit(gd.get("unit"))
            clause = " ".join(m.group("clause").split())[:300]
            key = clause_hash(clause.lower())
            if key in seen_clauses:
                continue
            seen_clauses.add(key)
            deadline_at = add_days(anchor_date, n, unit)
            result_key = (kind, deadline_at.strftime("%Y-%m-%d"))
            if result_key in seen_results:
                continue
            seen_results.add(result_key)
            # Skip past deadlines (already lapsed by more than 7 days)
            if deadline_at < datetime.now(MANILA_TZ) - timedelta(days=7):
                continue
            kind_human = {
                "appeal": "APPEAL deadline",
                "filing": "Filing deadline",
                "compliance": "Compliance deadline",
                "response": "Response deadline",
            }.get(kind, "Deadline")
            title = f"{kind_human} — {deadline_at.strftime('%d %b %Y')}"
            if matter_code:
                title = f"{kind_human} ({matter_code}) — {deadline_at.strftime('%d %b %Y')}"
            anchor_human = anchor_date.strftime("%d %b %Y")
            out.append(Extraction(
                title=title,
                description=(
                    f"Auto-extracted deadline.\n\n"
                    f"Verbatim clause:\n  \"{clause}\"\n\n"
                    f"Computed: {n} {unit} day(s) from anchor {anchor_human} = {deadline_at.strftime('%a %d %b %Y')}\n"
                    f"Pattern: {name}\n"
                    f"NOTE: anchor date is best-guess receipt date — operator should confirm."
                ),
                start_at=deadline_at,
                deadline_kind=kind,
                raw_clause=clause,
                pattern_name=name,
                confidence=0.75 if kind == "appeal" else 0.65,
                status="proposed",
                related_case=related_case,
                matter_code=matter_code,
                source_doc_id=source_doc_id,
                source_email_id=source_email_id,
            ))

    return out


# ------------------------------------------------------------------------
# Persistence
# ------------------------------------------------------------------------

def upsert_extractions(cur, extractions: list[Extraction], *, dry_run: bool = False) -> dict:
    """Idempotent insert into calendar_events. Skip if (source_doc_id|source_email_id, raw_clause_hash) already exists."""
    inserted = 0
    skipped = 0
    for e in extractions:
        h = clause_hash(e.raw_clause.lower())
        cur.execute(
            """
            SELECT id FROM calendar_events
             WHERE source = 'deadline_extractor'
               AND source_msg_id = %s
             LIMIT 1
            """,
            (f"{h}:{e.source_doc_id or 0}:{e.source_email_id or 0}",),
        )
        if cur.fetchone():
            skipped += 1
            continue
        if dry_run:
            print(f"    [DRY] would insert: {e.title}")
            print(f"          status={e.status} kind={e.deadline_kind} conf={e.confidence}")
            print(f"          clause: {e.raw_clause[:120]}...")
            inserted += 1
            continue
        cur.execute(
            """
            INSERT INTO calendar_events (
                title, description, start_at, related_case,
                source, source_msg_id, status,
                source_doc_id, source_email_id,
                deadline_kind, extraction_method, extraction_confidence,
                raw_clause
            ) VALUES (%s, %s, %s, %s, 'deadline_extractor', %s, %s, %s, %s, %s, 'regex', %s, %s)
            RETURNING id
            """,
            (
                e.title, e.description, e.start_at, e.related_case,
                f"{h}:{e.source_doc_id or 0}:{e.source_email_id or 0}",
                e.status,
                e.source_doc_id, e.source_email_id,
                e.deadline_kind, e.confidence, e.raw_clause,
            ),
        )
        new_id = cur.fetchone()[0]
        inserted += 1
        print(f"    ✓ #{new_id} {e.title}  [{e.status}/{e.deadline_kind} conf={e.confidence}]")
    return {"inserted": inserted, "skipped": skipped}


# ------------------------------------------------------------------------
# Drivers
# ------------------------------------------------------------------------

def matter_to_related_case(matter_code: str | None) -> str | None:
    if not matter_code:
        return None
    if matter_code.startswith("MWK-CV"):
        # MWK-CV26360 → "Civil Case 26-360"
        m = re.match(r"MWK-CV(\d+)", matter_code)
        if m:
            n = m.group(1)
            return f"Civil Case {n[:2]}-{n[2:]}"
    return matter_code


def parse_doc_date(doc_date_text: str | None) -> datetime | None:
    """document_date is freeform text; try common forms."""
    if not doc_date_text:
        return None
    s = doc_date_text.strip()
    for fmt in ("%d %B %Y", "%B %d, %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=MANILA_TZ)
        except ValueError:
            continue
    return None


def run_documents(cur, *, days: int, only_doc: int | None, dry_run: bool) -> dict:
    if only_doc:
        cur.execute(
            "SELECT id, matter_code, extracted_text, document_date, created_at "
            "FROM documents WHERE id = %s",
            (only_doc,),
        )
    else:
        cur.execute(
            """
            SELECT id, matter_code, extracted_text, document_date, created_at
              FROM documents
             WHERE (matter_code LIKE 'MWK-%%' OR matter_code LIKE 'PAR-%%')
               AND extracted_text IS NOT NULL
               AND LENGTH(extracted_text) > 200
               AND created_at > now() - interval '%s days'
             ORDER BY created_at DESC
            """,
            (days,),
        )
    total = {"inserted": 0, "skipped": 0, "docs_scanned": 0, "docs_inbound": 0}
    for row in cur.fetchall():
        total["docs_scanned"] += 1
        text = row["extracted_text"]
        if not is_inbound_doc(text):
            continue
        total["docs_inbound"] += 1
        # Anchor: doc_date if parseable, else created_at - 1 day (transmission lag)
        anchor = parse_doc_date(row.get("document_date")) or row["created_at"]
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=MANILA_TZ)
        extracts = extract_from_text(
            text,
            anchor_date=anchor,
            matter_code=row["matter_code"],
            related_case=matter_to_related_case(row["matter_code"]),
            source_doc_id=row["id"],
        )
        if extracts:
            print(f"\n  doc#{row['id']} [{row['matter_code']}] — {len(extracts)} extraction(s)")
            r = upsert_extractions(cur, extracts, dry_run=dry_run)
            total["inserted"] += r["inserted"]
            total["skipped"] += r["skipped"]
    return total


def run_emails(cur, *, days: int, only_email: int | None, dry_run: bool) -> dict:
    if only_email:
        cur.execute(
            "SELECT id, from_addr, subject, body_plain, sent_at, matter_codes "
            "FROM gmail_messages WHERE id = %s",
            (only_email,),
        )
    else:
        cur.execute(
            """
            SELECT id, from_addr, subject, body_plain, sent_at, matter_codes
              FROM gmail_messages
             WHERE matter_codes IS NOT NULL
               AND array_length(matter_codes, 1) > 0
               AND body_plain IS NOT NULL
               AND LENGTH(body_plain) > 50
               AND sent_at > now() - interval '%s days'
             ORDER BY sent_at DESC
            """,
            (days,),
        )
    total = {"inserted": 0, "skipped": 0, "emails_scanned": 0, "emails_inbound": 0}
    for row in cur.fetchall():
        total["emails_scanned"] += 1
        if not is_inbound_email(row["from_addr"]):
            continue
        total["emails_inbound"] += 1
        text = row["body_plain"] or ""
        # Strip CID image refs and Outlook noise
        text = re.sub(r"\[cid:[^\]]+\]", " ", text)
        text = re.sub(r"\r\n|\r", "\n", text)
        anchor = row["sent_at"]
        if anchor and anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=MANILA_TZ)
        # Use first matter_code as primary
        mc = (row["matter_codes"] or [None])[0]
        extracts = extract_from_text(
            text,
            anchor_date=anchor or datetime.now(MANILA_TZ),
            matter_code=mc,
            related_case=matter_to_related_case(mc),
            source_email_id=row["id"],
        )
        if extracts:
            print(f"\n  email#{row['id']} [{mc}] from {row['from_addr']} — {len(extracts)} extraction(s)")
            print(f"    subject: {(row['subject'] or '')[:120]}")
            r = upsert_extractions(cur, extracts, dry_run=dry_run)
            total["inserted"] += r["inserted"]
            total["skipped"] += r["skipped"]
    return total


# ------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60, help="lookback window in days")
    ap.add_argument("--doc", type=int, help="extract from a single document id")
    ap.add_argument("--email", type=int, help="extract from a single email id")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", choices=["docs", "emails"], help="restrict to one source")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(f"SET LOCAL app.actor = %s", (ACTOR,))

    print(f"deadline_extractor — lookback {args.days}d, dry_run={args.dry_run}")
    print("=" * 60)

    doc_totals = {"inserted": 0, "skipped": 0, "docs_scanned": 0, "docs_inbound": 0}
    email_totals = {"inserted": 0, "skipped": 0, "emails_scanned": 0, "emails_inbound": 0}

    if args.only != "emails":
        print("\n  Pass 1: documents")
        doc_totals = run_documents(cur, days=args.days, only_doc=args.doc, dry_run=args.dry_run)
        print(f"  → {doc_totals['docs_scanned']} scanned, {doc_totals['docs_inbound']} inbound, "
              f"{doc_totals['inserted']} inserted, {doc_totals['skipped']} skipped")

    if args.only != "docs":
        print("\n  Pass 2: gmail_messages")
        email_totals = run_emails(cur, days=args.days, only_email=args.email, dry_run=args.dry_run)
        print(f"  → {email_totals['emails_scanned']} scanned, {email_totals['emails_inbound']} inbound, "
              f"{email_totals['inserted']} inserted, {email_totals['skipped']} skipped")

    if args.dry_run:
        conn.rollback()
        print("\n  [DRY RUN — rolled back]")
    else:
        conn.commit()
        print("\n  ✓ COMMITTED")

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
