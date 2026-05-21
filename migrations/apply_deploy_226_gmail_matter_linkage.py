#!/usr/bin/env python3
"""Deploy 226 — gmail_messages ↔ matter linkage.

Closes the biggest data-layer gap surfaced by the May 21 audit:
  732 gmail messages, 0 linked to any matter.

Architecture:
  - `gmail_messages.matter_codes TEXT[]` — array of matter_codes, not a single FK.
    Real emails span multiple matters (e.g., the April 20 deferral letter listed
    three CTNs in one message).
  - GIN index for fast ANY() / overlap queries.
  - Backfill via deterministic regex over subject + body:
      * CTN SL-YYYY-NNNN-XXXX → MWK-ARTA-XXXX (suffix mapping)
      * "Civil Case 26-360" / "CV 26-360" / "26-360" → MWK-CV26360
      * "CV 6839" / "Civil Case 6839" → MWK-CV6839
  - Validated against the matters table — only codes that exist as matter_code
    get assigned. Spurious regex matches are silently filtered.

This is the DATA layer, not LLM. No negotiator in the path. Idempotent.
"""
import re
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


SCHEMA_SQL = """
ALTER TABLE gmail_messages
    ADD COLUMN IF NOT EXISTS matter_codes TEXT[] DEFAULT '{}'::text[];

CREATE INDEX IF NOT EXISTS idx_gmail_messages_matter_codes
    ON gmail_messages USING GIN(matter_codes);

-- For querying "all emails on matter X" we want a partial index on activity too
CREATE INDEX IF NOT EXISTS idx_gmail_messages_matter_codes_partial
    ON gmail_messages (sent_at DESC)
 WHERE cardinality(matter_codes) > 0;
"""


# CTN format: "CTN SL-YYYY-NNNN-XXXX" — XXXX is the suffix that distinguishes the case
CTN_RE = re.compile(
    r"\bCTN\s*[-:]?\s*SL\s*[-]?\s*(\d{4})\s*[-]?\s*(\d{4})\s*[-]?\s*(\d{3,4})\b",
    re.IGNORECASE,
)

# Civil Case references
CV_RE = re.compile(
    r"\b(?:Civil\s+Case|CV|Case)\s*(?:No\.?)?\s*[-]?\s*(\d{1,4})[-]?(\d{1,4})\b",
    re.IGNORECASE,
)

# Direct numeric matches inside "Civil Case 26-360" context
CV_KNOWN_TO_MATTER = {
    "26-360": "MWK-CV26360",
    "26360":  "MWK-CV26360",
    "6839":   "MWK-CV6839",
    "6922":   "MWK-PARALLEL-CV6922",
}


def derive_matter_codes(text, valid_matter_codes):
    """Return set of matter_codes in text that also exist in matters table.

    Conservative: only emit codes that pass validation. Spurious regex hits
    filtered silently.
    """
    if not text:
        return set()
    codes = set()

    # CTN → MWK-ARTA-<suffix>
    for m in CTN_RE.finditer(text):
        suffix = m.group(3)
        if len(suffix) == 3:
            suffix = "0" + suffix
        candidate = f"MWK-ARTA-{suffix}"
        if candidate in valid_matter_codes:
            codes.add(candidate)

    # CV references (need a known mapping)
    for m in CV_RE.finditer(text):
        # m.group(1)-m.group(2) is the "26-360" portion
        ref_hyphen = f"{m.group(1)}-{m.group(2)}"
        ref_solid = f"{m.group(1)}{m.group(2)}"
        for k in (ref_hyphen, ref_solid):
            if k in CV_KNOWN_TO_MATTER:
                cand = CV_KNOWN_TO_MATTER[k]
                if cand in valid_matter_codes:
                    codes.add(cand)

    return codes


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("Deploy 226 — gmail_messages ↔ matter linkage")
    print("=" * 60)

    print("\n[1/4] Schema: ADD COLUMN matter_codes + GIN index")
    cur.execute(SCHEMA_SQL)
    print("  ✓ schema ready")

    print("\n[2/4] Loading valid matter_codes from `matters`")
    cur.execute("SELECT matter_code FROM matters")
    valid = set(r["matter_code"] for r in cur.fetchall())
    print(f"  ✓ {len(valid)} matter_codes")
    print(f"    sample: {sorted(valid)[:5]}…")

    print("\n[3/4] Backfilling gmail_messages.matter_codes")
    cur.execute("""
        SELECT id, subject, body_plain
          FROM gmail_messages
         WHERE cardinality(COALESCE(matter_codes, '{}'::text[])) = 0
         ORDER BY id
    """)
    rows = cur.fetchall()
    print(f"  Scanning {len(rows)} gmail messages…")

    linked = 0
    multi_matter = 0
    per_matter = {}

    for r in rows:
        text = (r["subject"] or "") + "\n" + (r["body_plain"] or "")
        codes = derive_matter_codes(text, valid)
        if not codes:
            continue
        sorted_codes = sorted(codes)
        cur.execute(
            "UPDATE gmail_messages SET matter_codes = %s WHERE id = %s",
            (sorted_codes, r["id"]),
        )
        linked += 1
        if len(sorted_codes) > 1:
            multi_matter += 1
        for c in sorted_codes:
            per_matter[c] = per_matter.get(c, 0) + 1

    print(f"  ✓ {linked} messages linked to ≥1 matter ({multi_matter} multi-matter)")
    print()
    print("  Per-matter email counts (top 12):")
    for code, n in sorted(per_matter.items(), key=lambda x: -x[1])[:12]:
        print(f"    {code:<25s} {n} emails")

    print("\n[4/4] Sanity checks")
    cur.execute("SELECT COUNT(*) AS n FROM gmail_messages WHERE cardinality(matter_codes) > 0")
    linked_after = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM gmail_messages")
    total = cur.fetchone()["n"]
    print(f"  Total gmail messages: {total}")
    print(f"  Linked to ≥1 matter: {linked_after} ({100 * linked_after / max(1, total):.1f}%)")

    print()
    print("=" * 60)
    print("✓ Deploy 226 complete.")
    print()
    print("Try: SELECT id, sent_at::date, subject FROM gmail_messages")
    print("       WHERE 'MWK-ARTA-1321' = ANY(matter_codes) ORDER BY sent_at DESC LIMIT 20;")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
