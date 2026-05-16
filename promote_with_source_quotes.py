#!/usr/bin/env python3
"""Deploy 106 — Source-quote promotion to 'verified'.

Per CLAUDE.md:
  verified = directly cited to a source doc with a quoted excerpt.

For each inferred_strong / inferred_corroborated entity:
  1. Search documents.extracted_text for VERBATIM appearance of canonical_name
  2. If found: extract ±150 char context window as the source quote
  3. Promote to 'verified', append [SOURCE QUOTE from DOC X] line to notes

Safety constraints:
  - canonical_name must be >= 6 chars (skip noise)
  - type restricted to structured entities (person, org, property, location,
    reference_number, deed_or_instrument, case_or_docket)
  - Skip date_event + financial_amount (too easily false-positive)
  - One DOC source per promotion (the first matching doc, deterministic)
"""
import argparse
import re
import sys
from datetime import datetime, timezone
import psycopg2
import psycopg2.extras

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")

PROMOTABLE_TYPES = (
    "person", "organization", "property", "location",
    "reference_number", "deed_or_instrument", "case_or_docket",
    "legal_provision",
)
MIN_NAME_LEN = 6
CONTEXT_BEFORE = 100
CONTEXT_AFTER = 200


def safe_quote(text):
    """Trim and clean a substring for use as a quote excerpt."""
    if not text:
        return ""
    t = text.replace("\n", " ").replace("\r", " ").replace("  ", " ").strip()
    # Don't break in the middle of an apostrophe or quote
    return t.replace("\\", "\\\\").replace("'", "''")[:600]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=None, help="Limit to case_file (None = all)")
    ap.add_argument("--limit", type=int, default=None, help="Cap entities processed")
    ap.add_argument("--commit", action="store_true", help="Actually update (else dry run)")
    args = ap.parse_args()

    conn = psycopg2.connect(**DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    type_list_sql = ",".join(["'%s'" % t for t in PROMOTABLE_TYPES])
    sql = f"""
      SELECT id, type, canonical_name, mentions_count, provenance_level
        FROM entities
       WHERE provenance_level IN ('inferred_strong', 'inferred_corroborated')
         AND length(canonical_name) >= {MIN_NAME_LEN}
         AND type IN ({type_list_sql})
       ORDER BY mentions_count DESC, id
    """
    if args.limit:
        sql += f" LIMIT {args.limit}"
    cur.execute(sql)
    candidates = cur.fetchall()
    print(f"  candidates: {len(candidates)} entities")

    promoted = 0
    skipped_nomatch = 0
    skipped_ambig = 0
    type_counts = {}

    for e in candidates:
        name = e["canonical_name"]
        # Skip dangerous patterns (could match too broadly)
        if name.lower() in ("land", "case", "document", "letter", "notice",
                            "republic", "philippines", "barangay", "decision",
                            "court", "law", "section", "title", "deed",
                            "the philippines", "official receipt", "no.",
                            "ra no.", "republic act"):
            skipped_ambig += 1
            continue

        # Find first matching document
        cur.execute("""
            SELECT id, original_filename,
                   position(%s IN extracted_text) AS pos,
                   extracted_text
              FROM documents
             WHERE extracted_text ILIKE %s
               AND extracted_text IS NOT NULL
             ORDER BY id ASC
             LIMIT 1
        """, (name, "%" + name + "%"))
        doc = cur.fetchone()
        if not doc:
            skipped_nomatch += 1
            continue

        # Confirm it's case-sensitive matchable (ILIKE matched but POSITION uses case-sensitive)
        pos = doc["pos"]
        if not pos or pos < 1:
            # ILIKE matched but case-sensitive POSITION didn't — try lowercase
            txt_lower = doc["extracted_text"].lower()
            pos_l = txt_lower.find(name.lower())
            if pos_l < 0:
                skipped_nomatch += 1
                continue
            pos = pos_l + 1

        start = max(1, pos - CONTEXT_BEFORE)
        end = pos + len(name) + CONTEXT_AFTER
        quote_excerpt = doc["extracted_text"][start - 1:end]
        quote = safe_quote(quote_excerpt)
        doc_id = doc["id"]

        if args.commit:
            try:
                cur.execute("""
                    UPDATE entities
                       SET provenance_level = 'verified',
                           verified_by = 'source_quote_promotion_v1',
                           verified_at = now(),
                           notes = COALESCE(NULLIF(notes, ''), '') ||
                                   CASE WHEN notes IS NULL OR notes = '' THEN '' ELSE E'\n' END ||
                                   '[SOURCE QUOTE from DOC ' || %s || ']: "' || %s || '"'
                     WHERE id = %s
                """, (doc_id, quote, e["id"]))
                promoted += 1
                type_counts[e["type"]] = type_counts.get(e["type"], 0) + 1
            except Exception as ex:
                print(f"    update fail e_id={e['id']}: {ex}")
                skipped_nomatch += 1
        else:
            promoted += 1
            type_counts[e["type"]] = type_counts.get(e["type"], 0) + 1

        if promoted > 0 and promoted % 100 == 0:
            print(f"    progress: promoted={promoted}, no-match={skipped_nomatch}, ambig-skip={skipped_ambig}")

    print(f"\n  ✓ promoted: {promoted}")
    print(f"  - skipped no source-doc match: {skipped_nomatch}")
    print(f"  - skipped ambiguous-pattern: {skipped_ambig}")
    print(f"\n  Promotions by type:")
    for t in sorted(type_counts.keys(), key=lambda x: -type_counts[x]):
        print(f"    {t:25} {type_counts[t]}")

    # Final distribution
    cur.execute("""
      SELECT provenance_level, count(*) FROM entities GROUP BY 1 ORDER BY count(*) DESC;
    """)
    print(f"\n  Final entities distribution:")
    for r in cur.fetchall():
        print(f"    {r['provenance_level']:25} {r['count']}")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
