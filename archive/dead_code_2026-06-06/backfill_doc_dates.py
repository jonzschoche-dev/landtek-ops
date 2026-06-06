#!/usr/bin/env python3
"""Backfill doc_date_norm for documents missing it (deploy_154).

Surfaced by coverage_auditor (deploy_152): 289 MWK docs lack doc_date_norm,
which is the upstream gap blocking them from client_history. Four-phase
extraction, cheapest first:

  Phase 1: filename regex      (free, instant)
  Phase 2: extracted_text regex (free, instant)
  Phase 3: inherit from parent gmail message via gmail_attachments
           or filename hash match  (free, instant)
  Phase 4: Haiku LLM extraction (~$0.001/doc, only for residual)

CLI:
  python3 backfill_doc_dates.py --case MWK-001 --phases 1,2,3   # free phases
  python3 backfill_doc_dates.py --case MWK-001 --phases 4        # LLM pass
  python3 backfill_doc_dates.py --case MWK-001                   # all phases
  python3 backfill_doc_dates.py --case MWK-001 --dry-run         # report only
"""
import argparse
import re
import sys
from datetime import date, datetime
sys.path.insert(0, "/root/landtek")
from landtek_core import db

# ── Phase 1: filename patterns ──────────────────────────────────────────
ISO_DATE = re.compile(r'(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)')
YEAR_MONTH = re.compile(r'(?<!\d)(\d{4})-(\d{2})(?!\d)')
YEAR_ONLY = re.compile(r'(?<!\d)(\d{4})(?!\d)')
MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7, 'aug': 8,
    'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


def safe_date(y, m, d):
    """Try to construct a date; allow common OCR/typo corrections."""
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        # Common: day > 31 (e.g., "33" → likely "13" or "03"); skip
        return None


def parse_filename(fname):
    if not fname or fname.startswith(('YYYY', 'null')):
        return None
    # Strip Gmail hash prefix
    fname_clean = re.sub(r'^[0-9a-f]+__', '', fname)
    # Try ISO YYYY-MM-DD
    m = ISO_DATE.search(fname_clean)
    if m:
        d = safe_date(*m.groups())
        if d and date(1900, 1, 1) <= d <= date.today():
            return d, "filename_iso"
    # Year-month only — assume day=01
    m = YEAR_MONTH.search(fname_clean)
    if m:
        y, mo = m.groups()
        d = safe_date(y, mo, "01")
        if d and date(1900, 1, 1) <= d <= date.today():
            return d, "filename_year_month"
    # Year-only — assume Jan 1 (provenance: weak)
    m = YEAR_ONLY.search(fname_clean)
    if m:
        y = int(m.group(1))
        if 1900 <= y <= date.today().year:
            return date(y, 1, 1), "filename_year_only"
    return None


# ── Phase 2: extracted_text patterns ────────────────────────────────────
# "this 15th day of August 2005", "August 15, 2005", "15 August 2005", etc.
DAY_OF_MONTH_YEAR = re.compile(
    r'(\d{1,2})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?'
    r'(january|february|march|april|may|june|july|august|september|october|november|december|'
    r'jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)'
    r'[\s,]+(\d{4})',
    re.IGNORECASE
)
MONTH_DAY_YEAR = re.compile(
    r'(january|february|march|april|may|june|july|august|september|october|november|december|'
    r'jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s+'
    r'(\d{1,2})(?:st|nd|rd|th)?[\s,]+(\d{4})',
    re.IGNORECASE
)


def parse_text(text, max_chars=4000):
    if not text:
        return None
    t = text[:max_chars].lower()
    # Prefer "day of MONTH YEAR" (notarized docs use this form)
    for pattern, order in [(DAY_OF_MONTH_YEAR, "dmy"), (MONTH_DAY_YEAR, "mdy")]:
        for m in pattern.finditer(t):
            g = m.groups()
            if order == "dmy":
                d, mo, y = g[0], MONTHS.get(g[1].lower()), g[2]
            else:
                mo, d, y = MONTHS.get(g[0].lower()), g[1], g[2]
            if mo is None:
                continue
            dt = safe_date(y, mo, d)
            if dt and date(1900, 1, 1) <= dt <= date.today():
                return dt, f"text_{order}"
    # Fall back to bare year in text body
    m = ISO_DATE.search(t)
    if m:
        dt = safe_date(*m.groups())
        if dt and date(1900, 1, 1) <= dt <= date.today():
            return dt, "text_iso"
    return None


# ── Phase 3: inherit from parent gmail message ──────────────────────────
def parse_from_gmail(cur, doc_id, fname):
    """If filename starts with a gmail hash, look up the parent message."""
    if not fname:
        return None
    m = re.match(r'^([0-9a-f]{8,})__', fname)
    if not m:
        return None
    gmail_hash = m.group(1)
    # gmail_messages.message_id has the same hash prefix (Gmail's globally-unique ID)
    cur.execute("""
        SELECT received_at, sent_at FROM gmail_messages
         WHERE message_id = %s OR message_id LIKE %s
         LIMIT 1
    """, (gmail_hash, f"{gmail_hash}%"))
    r = cur.fetchone()
    if r and (r["received_at"] or r["sent_at"]):
        dt = (r["received_at"] or r["sent_at"]).date()
        return dt, "gmail_inherited"
    return None


# ── Phase 4: Haiku LLM extraction ───────────────────────────────────────
def parse_via_haiku(client, doc_id, fname, text):
    if not text or len(text.strip()) < 50:
        return None
    from llm_billing import anthropic_call
    prompt = (
        f"You will receive the OCR text of a legal/property document. "
        f"Return ONLY the primary date of the document — when it was executed, "
        f"signed, dated, or filed. If you cannot identify a single primary date, "
        f"reply NONE. Reply in EXACTLY one of these formats:\n"
        f"  YYYY-MM-DD\n"
        f"  NONE\n\n"
        f"Filename: {fname}\n\n"
        f"Text:\n{text[:3000]}"
    )
    try:
        msg = anthropic_call(
            client,
            called_from="backfill_doc_dates",
            purpose="date_extraction",
            case_file=None,
            model="claude-haiku-4-5-20251001",
            max_tokens=20,
            messages=[{"role": "user", "content": prompt}],
        )
        out = msg.content[0].text.strip()
        if out == "NONE":
            return None
        m = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', out)
        if m:
            d = safe_date(*m.groups())
            if d and date(1900, 1, 1) <= d <= date.today():
                return d, "haiku"
    except Exception as e:
        print(f"    haiku error doc#{doc_id}: {str(e)[:120]}")
    return None


def run(case_file, phases, dry_run=False, limit=None):
    limit_clause = f"LIMIT {int(limit)}" if limit else ""
    with db() as cur:
        cur.execute(f"""
            SELECT id, COALESCE(smart_filename, original_filename) AS fname,
                   extracted_text, classification
              FROM documents
             WHERE case_file = %s AND doc_date_norm IS NULL
             ORDER BY id
             {limit_clause}
        """, (case_file,))
        rows = cur.fetchall()
    print(f"Found {len(rows)} docs in {case_file} without doc_date_norm")

    counts = {"filename": 0, "text": 0, "gmail": 0, "haiku": 0, "still_missing": 0}
    updates = []
    client = None

    for i, r in enumerate(rows, 1):
        result = None
        if 1 in phases:
            result = parse_filename(r["fname"])
            if result: counts["filename"] += 1
        if not result and 2 in phases:
            result = parse_text(r["extracted_text"])
            if result: counts["text"] += 1
        if not result and 3 in phases:
            with db() as cur:
                result = parse_from_gmail(cur, r["id"], r["fname"])
            if result: counts["gmail"] += 1
        if not result and 4 in phases:
            if client is None:
                import anthropic
                from landtek_core import get
                client = anthropic.Anthropic(api_key=get("ANTHROPIC_API_KEY"))
            result = parse_via_haiku(client, r["id"], r["fname"], r["extracted_text"])
            if result: counts["haiku"] += 1
            if i % 25 == 0:
                print(f"  ... haiku pass {i}/{len(rows)}, found {counts['haiku']}")

        if result:
            dt, source = result
            updates.append((r["id"], dt, source))
        else:
            counts["still_missing"] += 1

    print(f"\n=== Backfill results for {case_file} ===")
    for k, v in counts.items():
        print(f"  {k:>15}: {v}")

    if dry_run:
        print("\n(dry-run — no DB updates)")
        return counts, updates

    # Apply updates
    if updates:
        with db() as cur:
            for doc_id, dt, source in updates:
                cur.execute("""
                    UPDATE documents
                       SET doc_date_norm = %s,
                           updated_at = NOW()
                     WHERE id = %s AND doc_date_norm IS NULL
                """, (dt, doc_id))
        print(f"\n✅ Updated {len(updates)} docs with extracted dates")
    return counts, updates


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="MWK-001")
    ap.add_argument("--phases", default="1,2,3",
                    help="comma-separated phases to run; e.g. '1,2,3' or '4' or '1,2,3,4'")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    phases = set(int(p) for p in args.phases.split(","))
    run(args.case, phases, dry_run=args.dry_run, limit=args.limit)
