#!/usr/bin/env python3
"""Deploy 259 — doc_date backfill for undated MWK docs.

174 MWK-001 docs are missing doc_date. Breakdown shows ~77 have a normalized
doc_date_norm already populated but doc_date (the text form) is NULL —
trivial SQL copy. The remaining ~97 are truly undated and need extraction.

Three-pass backfill (deterministic; no LLM in this deploy):

  Pass 1 — COPY doc_date_norm → doc_date for any MWK doc where the norm
           is populated but the text form is empty. Cheap, instant, ~77 fixes.

  Pass 2 — FILENAME leading YYYY-MM-DD extraction. smart_filename or
           original_filename starts with a date (e.g., 2023-10-01_property_*),
           write it to both doc_date_norm + doc_date.

  Pass 3 — FIRST RELIABLE DATE in extracted_text. Look for ISO YYYY-MM-DD
           or 'Month DD, YYYY' in the first 4000 chars. Mark quality
           'inferred_text_header' so it's clear this is weaker provenance.

LLM extraction (Haiku via doc_date_extractor.py) is left as an explicit
follow-up — this deploy moves the deterministic needle first.

Idempotent. Audited via app.actor='jonathan_deploy_259'.

Usage:
  python3 migrations/apply_deploy_259_mwk_doc_date_backfill.py            # report
  python3 migrations/apply_deploy_259_mwk_doc_date_backfill.py --apply    # commit
"""
import argparse
import re
import sys
from datetime import date

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

CASE_FILE = "MWK-001"

ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
MONTH_NAMES = {
    "january":1, "february":2, "march":3, "april":4, "may":5, "june":6,
    "july":7, "august":8, "september":9, "october":10, "november":11, "december":12,
    "jan":1, "feb":2, "mar":3, "apr":4, "jun":6, "jul":7, "aug":8, "sep":9, "sept":9,
    "oct":10, "nov":11, "dec":12,
}
MONTH_DD_YYYY_RE = re.compile(
    r"\b(" + "|".join(MONTH_NAMES.keys()) + r")\.?\s+(\d{1,2}),?\s+(\d{4})\b",
    re.IGNORECASE,
)


def parse_iso(s):
    m = ISO_DATE_RE.search(s or "")
    if not m:
        return None
    try:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    # Sanity: must be in 1850-2100 window
    if d.year < 1850 or d.year > 2100:
        return None
    return d


def parse_month_dd_yyyy(s):
    if not s:
        return None
    m = MONTH_DD_YYYY_RE.search(s)
    if not m:
        return None
    mo = MONTH_NAMES.get(m.group(1).lower())
    if not mo:
        return None
    try:
        d = date(int(m.group(3)), mo, int(m.group(2)))
    except ValueError:
        return None
    if d.year < 1850 or d.year > 2100:
        return None
    return d


def extract_from_filename(fn):
    if not fn:
        return None
    # Leading YYYY-MM-DD prefix
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", fn)
    if m:
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if 1850 <= d.year <= 2100:
                return d
        except ValueError:
            pass
    return None


def extract_from_text_head(text):
    """Look for the first reliable date in the first 4000 chars."""
    if not text:
        return None
    head = text[:4000]
    iso = parse_iso(head)
    if iso:
        return iso
    return parse_month_dd_yyyy(head)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if args.apply:
        cur.execute("SET LOCAL app.actor = 'jonathan_deploy_259'")

    print(f"Deploy 259 — MWK doc_date backfill ({CASE_FILE})")
    print("=" * 60)

    # Pre-state
    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE doc_date IS NULL) AS missing_dd,
               COUNT(*) FILTER (WHERE doc_date_norm IS NULL) AS missing_norm,
               COUNT(*) FILTER (WHERE doc_date IS NULL AND doc_date_norm IS NULL) AS truly_undated
          FROM documents WHERE case_file = %s
    """, (CASE_FILE,))
    pre = cur.fetchone()
    print(f"  Before: doc_date NULL={pre['missing_dd']} | doc_date_norm NULL={pre['missing_norm']} | both NULL={pre['truly_undated']}")

    # --- Pass 1: copy doc_date_norm → doc_date ---
    cur.execute("""
        SELECT id, doc_date_norm
          FROM documents
         WHERE case_file = %s
           AND doc_date IS NULL
           AND doc_date_norm IS NOT NULL
    """, (CASE_FILE,))
    pass1 = cur.fetchall()
    print(f"\n  Pass 1 — copy doc_date_norm → doc_date: {len(pass1)} docs")

    if args.apply:
        for r in pass1:
            cur.execute("UPDATE documents SET doc_date = %s WHERE id = %s",
                        (r["doc_date_norm"].isoformat(), r["id"]))

    # --- Pass 2: filename leading date ---
    cur.execute("""
        SELECT id, smart_filename, original_filename
          FROM documents
         WHERE case_file = %s
           AND doc_date IS NULL AND doc_date_norm IS NULL
    """, (CASE_FILE,))
    pass2_candidates = cur.fetchall()
    pass2 = []
    for r in pass2_candidates:
        d = extract_from_filename(r.get("smart_filename")) or extract_from_filename(r.get("original_filename"))
        if d:
            pass2.append((r["id"], d))
    print(f"\n  Pass 2 — filename leading YYYY-MM-DD: {len(pass2)} hits "
          f"(of {len(pass2_candidates)} candidates)")
    if args.apply:
        for doc_id, d in pass2:
            cur.execute("""UPDATE documents
                              SET doc_date = %s, doc_date_norm = %s,
                                  doc_date_quality = COALESCE(doc_date_quality, 'inferred_filename')
                            WHERE id = %s""",
                        (d.isoformat(), d, doc_id))

    # --- Pass 3: extracted_text head ---
    cur.execute("""
        SELECT id, extracted_text
          FROM documents
         WHERE case_file = %s
           AND doc_date IS NULL AND doc_date_norm IS NULL
    """, (CASE_FILE,))
    pass3_candidates = cur.fetchall()
    pass3 = []
    for r in pass3_candidates:
        d = extract_from_text_head(r.get("extracted_text"))
        if d:
            pass3.append((r["id"], d))
    print(f"\n  Pass 3 — first date in extracted_text head: {len(pass3)} hits "
          f"(of {len(pass3_candidates)} candidates)")
    if args.apply:
        for doc_id, d in pass3:
            cur.execute("""UPDATE documents
                              SET doc_date = %s, doc_date_norm = %s,
                                  doc_date_quality = COALESCE(doc_date_quality, 'inferred_text_header')
                            WHERE id = %s""",
                        (d.isoformat(), d, doc_id))

    if args.apply:
        conn.commit()
        print("\n  ✓ COMMITTED")
    else:
        print("\n  (dry-run — pass --apply to commit)")

    # Post-state
    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE doc_date IS NULL) AS missing_dd,
               COUNT(*) FILTER (WHERE doc_date_norm IS NULL) AS missing_norm,
               COUNT(*) FILTER (WHERE doc_date IS NULL AND doc_date_norm IS NULL) AS truly_undated
          FROM documents WHERE case_file = %s
    """, (CASE_FILE,))
    post = cur.fetchone()
    print(f"\n  After:  doc_date NULL={post['missing_dd']} | doc_date_norm NULL={post['missing_norm']} | both NULL={post['truly_undated']}")
    if args.apply:
        print(f"  Net: closed {pre['missing_dd'] - post['missing_dd']} doc_date gaps, "
              f"{pre['truly_undated'] - post['truly_undated']} truly-undated gaps")
        print("  Remaining truly-undated docs need LLM extraction (doc_date_extractor.py or follow-up).")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
