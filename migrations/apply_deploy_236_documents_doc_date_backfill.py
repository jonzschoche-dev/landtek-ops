#!/usr/bin/env python3
"""Deploy 236 — backfill documents.doc_date from filename + text header.

424 of 953 docs (44%) have NULL doc_date. The chronological chronicle, timeline
queries, and any "what happened on date X" question are unusable for these.

Priority (most reliable first):
  1. Filename leading `YYYY-MM-DD_` pattern (the canonical filename convention)
  2. instruments_on_title.entry_date if the doc has an instruments_on_title row
  3. resolutions.resolution_date if doc is a resolution
  4. First date in first 500 chars of extracted_text (header date)

Conservative: only sets doc_date when a single clear date is found in one of
the priority sources. Multi-candidate or citation-style dates leave NULL.

Idempotent (only updates NULL doc_date).
"""
import re
from datetime import date

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


# Filename: leading "YYYY-MM-DD" or "YYYY-MM-DD_" or "YYYY-MM-DD "
FN_DATE_RE = re.compile(r"^[\s/]*(\d{4})-(\d{2})-(\d{2})[_\s.-]")

# Header dates in body text
DATE_RES = [
    # DD Month YYYY  — e.g., "20 April 2026"
    re.compile(r"\b(\d{1,2})\s+([A-Z][a-z]{2,8})\s+(\d{4})\b"),
    # Month DD, YYYY — e.g., "April 20, 2026"
    re.compile(r"\b([A-Z][a-z]{2,8})\s+(\d{1,2}),?\s+(\d{4})\b"),
    # YYYY-MM-DD
    re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"),
]

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "Jun": 6, "Jul": 7,
    "Aug": 8, "Sep": 9, "Sept": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def safe_date(y, m, d):
    """Build date; return None if invalid or out of plausible range."""
    try:
        y, m, d = int(y), int(m), int(d)
    except (TypeError, ValueError):
        return None
    if not (1900 <= y <= 2030):
        return None
    if not (1 <= m <= 12):
        return None
    if not (1 <= d <= 31):
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_text_date(text, window=500):
    """First plausible header date in the first `window` chars. Excludes citation-style."""
    if not text:
        return None
    head = text[:window]

    # Skip if window starts with citation-style text
    citation_markers = ["G.R. No.", "G.R. NO.", "v.", "vs.", "Citing", "see also"]

    candidates = []

    # DD Month YYYY
    for m in DATE_RES[0].finditer(head):
        d, mon_name, y = m.group(1), m.group(2), m.group(3)
        mon = MONTHS.get(mon_name) or MONTHS.get(mon_name.capitalize())
        if mon:
            dt = safe_date(y, mon, d)
            if dt:
                # Check immediate context for citation markers
                ctx = head[max(0, m.start() - 40):m.end() + 10]
                if not any(c in ctx for c in citation_markers):
                    candidates.append((m.start(), dt))

    # Month DD, YYYY
    for m in DATE_RES[1].finditer(head):
        mon_name, d, y = m.group(1), m.group(2), m.group(3)
        mon = MONTHS.get(mon_name)
        if mon:
            dt = safe_date(y, mon, d)
            if dt:
                ctx = head[max(0, m.start() - 40):m.end() + 10]
                if not any(c in ctx for c in citation_markers):
                    candidates.append((m.start(), dt))

    # YYYY-MM-DD
    for m in DATE_RES[2].finditer(head):
        y, mo, d = m.group(1), m.group(2), m.group(3)
        dt = safe_date(y, mo, d)
        if dt:
            ctx = head[max(0, m.start() - 40):m.end() + 10]
            if not any(c in ctx for c in citation_markers):
                candidates.append((m.start(), dt))

    if not candidates:
        return None
    # Earliest position (header date)
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def parse_filename_date(filename):
    if not filename:
        return None
    m = FN_DATE_RE.match(filename)
    if not m:
        return None
    return safe_date(m.group(1), m.group(2), m.group(3))


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("Deploy 236 — documents.doc_date backfill")
    print("=" * 60)

    cur.execute("""
        SELECT id, smart_filename, COALESCE(extracted_text, '') AS extracted_text
          FROM documents WHERE doc_date IS NULL AND case_file = 'MWK-001'
         ORDER BY id
    """)
    rows = cur.fetchall()
    print(f"\n  Scanning {len(rows)} MWK-001 docs with NULL doc_date…")

    from_filename = 0
    from_instruments = 0
    from_resolutions = 0
    from_text = 0
    still_null = 0

    for r in rows:
        doc_id = r["id"]
        fn = r["smart_filename"]
        text = r["extracted_text"]

        # Priority 1: filename
        d = parse_filename_date(fn)
        source = "filename" if d else None

        # Priority 2: instruments_on_title.entry_date
        if not d:
            cur.execute(
                "SELECT entry_date FROM instruments_on_title "
                " WHERE doc_id = %s AND entry_date IS NOT NULL"
                " ORDER BY entry_date LIMIT 1",
                (doc_id,),
            )
            iot = cur.fetchone()
            if iot and iot["entry_date"]:
                d = iot["entry_date"]
                source = "instruments"

        # Priority 3: resolutions.resolution_date
        if not d:
            cur.execute(
                "SELECT resolution_date FROM resolutions "
                " WHERE source_doc_id = %s AND resolution_date IS NOT NULL LIMIT 1",
                (doc_id,),
            )
            rr = cur.fetchone()
            if rr and rr["resolution_date"]:
                d = rr["resolution_date"]
                source = "resolutions"

        # Priority 4: parse text header
        if not d:
            d = parse_text_date(text)
            if d:
                source = "text"

        if d:
            cur.execute("UPDATE documents SET doc_date = %s WHERE id = %s AND doc_date IS NULL",
                        (d, doc_id))
            if cur.rowcount > 0:
                if source == "filename":
                    from_filename += 1
                elif source == "instruments":
                    from_instruments += 1
                elif source == "resolutions":
                    from_resolutions += 1
                elif source == "text":
                    from_text += 1
        else:
            still_null += 1

    total_set = from_filename + from_instruments + from_resolutions + from_text
    print(f"\n  ✓ {total_set} docs backfilled:")
    print(f"      from filename:    {from_filename}")
    print(f"      from instruments: {from_instruments}")
    print(f"      from resolutions: {from_resolutions}")
    print(f"      from text header: {from_text}")
    print(f"  ○ {still_null} docs still NULL — no date found in any source")

    # Final coverage
    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE case_file = 'MWK-001') AS mwk_total,
               COUNT(*) FILTER (WHERE case_file = 'MWK-001' AND doc_date IS NOT NULL) AS mwk_dated
          FROM documents
    """)
    rr = cur.fetchone()
    pct = 100 * rr["mwk_dated"] / max(1, rr["mwk_total"])
    print()
    print(f"  Final MWK-001 coverage: {rr['mwk_dated']}/{rr['mwk_total']} dated ({pct:.1f}%)")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
