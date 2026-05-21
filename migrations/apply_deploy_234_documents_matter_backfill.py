#!/usr/bin/env python3
"""Deploy 234 — backfill documents.matter_code from extracted_text + filename.

Scope: MWK-001 documents only (per "stick with MWK until it's right" directive).

`documents.matter_code` is currently sparse — most MWK docs have only the
coarse case_file='MWK-001' tag. This blocks the matter-level traversal:
`lookup.py --matter MWK-ARTA-1210` returns 0 docs because the documents
aren't tagged to that specific matter.

Approach (deterministic regex, same conventions as deploy_226 gmail backfill):
  - CTN SL-YYYY-NNNN-XXXX → MWK-ARTA-XXXX (suffix mapping)
  - "Civil Case 26-360" / "CV 26-360" → MWK-CV26360
  - "CV 6839" → MWK-CV6839
  - "Civil Case 6922" → MWK-PARALLEL-CV6922

Validated against the matters table — only codes that exist as matter_code
get assigned.

Conservative: leaves docs with ambiguous (multi-matter or unclear) references
in NULL state for later manual or LLM review via proposed_changes.

This is a single-value column (matter_code TEXT), not an array. For docs that
genuinely span multiple matters (e.g., consolidated petitions), the strongest
single match wins; secondary linkages remain queryable via emails / resolutions
that reference all matters.

Idempotent: only updates NULL matter_code rows. Re-running is safe.
"""
import re
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


CTN_RE = re.compile(
    r"\bCTN\s*[-:]?\s*SL\s*[-]?\s*(\d{4})\s*[-]?\s*(\d{4})\s*[-]?\s*(\d{3,4})\b",
    re.IGNORECASE,
)
CV_RE = re.compile(
    r"\b(?:Civil\s+Case|CV|Case)\s*(?:No\.?)?\s*[-]?\s*(\d{1,4})[-]?(\d{1,4})\b",
    re.IGNORECASE,
)
CV_KNOWN_TO_MATTER = {
    "26-360": "MWK-CV26360",
    "26360":  "MWK-CV26360",
    "6839":   "MWK-CV6839",
    "6922":   "MWK-PARALLEL-CV6922",
}


def derive_best_matter(text, filename, valid_matter_codes):
    """Return the single strongest matter_code match, or None."""
    if not text and not filename:
        return None
    haystack = ((filename or "") + "\n" + (text or ""))[:50000]

    candidates = {}  # matter_code → score
    # CTN matches (strong; specific)
    for m in CTN_RE.finditer(haystack):
        suffix = m.group(3)
        if len(suffix) == 3:
            suffix = "0" + suffix
        cand = f"MWK-ARTA-{suffix}"
        if cand in valid_matter_codes:
            candidates[cand] = candidates.get(cand, 0) + 3

    # CV references (also strong when known)
    for m in CV_RE.finditer(haystack):
        for k in (f"{m.group(1)}-{m.group(2)}", f"{m.group(1)}{m.group(2)}"):
            if k in CV_KNOWN_TO_MATTER:
                cand = CV_KNOWN_TO_MATTER[k]
                if cand in valid_matter_codes:
                    candidates[cand] = candidates.get(cand, 0) + 3

    # Filename direct match (e.g., "MWK-CV26360_brief.pdf" — rare but possible)
    fn_lower = (filename or "").lower()
    for mc in valid_matter_codes:
        if mc.lower() in fn_lower:
            candidates[mc] = candidates.get(mc, 0) + 5  # filename match is very strong

    if not candidates:
        return None
    # Best single match. Ties go to the more-specific (longer matter code).
    return max(candidates.items(), key=lambda x: (x[1], len(x[0])))[0]


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("Deploy 234 — documents.matter_code backfill (MWK-001 scope)")
    print("=" * 60)

    cur.execute("SELECT matter_code FROM matters WHERE matter_code LIKE 'MWK-%'")
    valid = set(r["matter_code"] for r in cur.fetchall())
    print(f"\n  {len(valid)} MWK matter_codes available for assignment")

    cur.execute("""
        SELECT id, smart_filename, COALESCE(extracted_text, '') AS extracted_text
          FROM documents
         WHERE case_file = 'MWK-001'
           AND matter_code IS NULL
           AND LENGTH(COALESCE(extracted_text, '')) + LENGTH(COALESCE(smart_filename, '')) > 50
         ORDER BY id
    """)
    rows = cur.fetchall()
    print(f"  Scanning {len(rows)} MWK-001 docs with NULL matter_code…")

    updated = 0
    by_matter = {}
    for r in rows:
        cand = derive_best_matter(r["extracted_text"], r["smart_filename"], valid)
        if not cand:
            continue
        cur.execute(
            "UPDATE documents SET matter_code = %s WHERE id = %s AND matter_code IS NULL",
            (cand, r["id"]),
        )
        if cur.rowcount > 0:
            updated += 1
            by_matter[cand] = by_matter.get(cand, 0) + 1

    print(f"\n  ✓ {updated} docs tagged to a specific matter")
    print()
    print("  Per-matter coverage (top 12):")
    for mc, n in sorted(by_matter.items(), key=lambda x: -x[1])[:12]:
        print(f"    {mc:<25s} {n}")

    # Final audit
    cur.execute("""
        SELECT
          COUNT(*) FILTER (WHERE case_file = 'MWK-001') AS mwk_total,
          COUNT(*) FILTER (WHERE case_file = 'MWK-001' AND matter_code IS NOT NULL) AS mwk_tagged
          FROM documents
    """)
    r = cur.fetchone()
    pct = 100 * r["mwk_tagged"] / max(1, r["mwk_total"])
    print()
    print(f"  Final MWK-001 coverage: {r['mwk_tagged']}/{r['mwk_total']} docs matter-tagged ({pct:.1f}%)")

    cur.close()
    conn.close()
    print()
    print("Now: lookup.py --matter MWK-ARTA-1210 will show docs in addition to emails.")


if __name__ == "__main__":
    main()
