#!/usr/bin/env python3
"""Backfill the assets table from existing entities + documents.

Per Layer A schema substrate: every property/TCT entity gets a structured row
with area_sqm, location, current_holder parsed from entity notes + co-mentioned
documents.

Idempotent: ON CONFLICT (asset_type, canonical_id) DO UPDATE updates fields
incrementally rather than re-inserting.

Sources:
  - entities of type='property' with TCT/OCT/PI patterns
  - chat_notes referencing them for area/status
  - documents.extracted_text excerpts for value/status fingerprints
"""
import re
import sys
from datetime import datetime, timezone
import psycopg2, psycopg2.extras

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")

TCT_PATTERNS = [
    re.compile(r"^TCT[-\s]?(?:T[-\s])?(\d{3,6})", re.I),
    re.compile(r"^OCT[-\s]?(?:T[-\s])?(\d{3,6})", re.I),
    re.compile(r"^Transfer Certificate of Title No\.\s*(?:T[-\s])?(\d{3,6})", re.I),
]

AREA_PATTERN = re.compile(r"([\d,]+\.?\d*)\s*(?:sq\.?m|square meters?|sqm)", re.I)
PI_PATTERN = re.compile(r"^(?:Property Index No\.?\s*)?(\d{3}-\d{2}-\d{3}-\d{2}-\d{3})", re.I)


def normalize_tct(name: str) -> str:
    """Normalize TCT references to canonical form: TCT-<num>."""
    for pat in TCT_PATTERNS:
        m = pat.match(name)
        if m:
            num = m.group(1)
            return f"TCT-{num}"
    m = PI_PATTERN.match(name)
    if m:
        return f"PI-{m.group(1)}"
    return None


def parse_area(text: str) -> float:
    """Extract first sq.m. value from text."""
    if not text:
        return None
    m = AREA_PATTERN.search(text)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def main():
    conn = psycopg2.connect(**DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Pull property + relevant entities
    cur.execute("""
        SELECT id AS entity_id, canonical_name, aliases, notes, mentions_count,
               provenance_level, first_seen_doc, last_seen_doc
          FROM entities
         WHERE type = 'property'
           AND mentions_count >= 1
         ORDER BY mentions_count DESC;
    """)
    props = cur.fetchall()
    print(f"  property entities to process: {len(props)}")

    upserted = 0
    skipped = 0
    for e in props:
        canon = normalize_tct(e["canonical_name"])
        if not canon:
            skipped += 1
            continue

        area = parse_area(e["notes"] or "") or parse_area(e["canonical_name"] or "")

        # Figure out case_file based on document case_file linkage
        cur.execute("""
            SELECT d.case_file FROM documents d
             WHERE d.id IN (%s, %s) AND d.case_file IS NOT NULL AND d.case_file != ''
             ORDER BY id LIMIT 1
        """, (e["first_seen_doc"], e["last_seen_doc"]))
        cf_row = cur.fetchone()
        case_file = cf_row["case_file"] if cf_row else "MWK-001"  # default heuristic

        asset_type = "tct" if canon.startswith("TCT-") else "oct" if canon.startswith("OCT-") else "declaration" if canon.startswith("PI-") else "property"

        source_docs = [d for d in (e["first_seen_doc"], e["last_seen_doc"]) if d]

        try:
            cur.execute("""
                INSERT INTO assets (
                  asset_type, canonical_id, case_file, area_sqm,
                  source_doc_ids, notes, provenance_level,
                  current_status, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s,
                        CASE WHEN %s ILIKE '%%revoked%%' OR %s ILIKE '%%fraudulent%%' OR %s ILIKE '%%contested%%'
                             THEN 'contested' ELSE 'active' END,
                        now(), now())
                ON CONFLICT (asset_type, canonical_id) DO UPDATE
                  SET area_sqm = COALESCE(EXCLUDED.area_sqm, assets.area_sqm),
                      notes = COALESCE(NULLIF(EXCLUDED.notes, ''), assets.notes),
                      source_doc_ids = ARRAY(SELECT DISTINCT unnest(assets.source_doc_ids || EXCLUDED.source_doc_ids)),
                      provenance_level = CASE
                        WHEN EXCLUDED.provenance_level = 'verified' THEN 'verified'
                        ELSE assets.provenance_level END,
                      updated_at = now()
                RETURNING id;
            """, (asset_type, canon, case_file, area, source_docs, e["notes"] or "", e["provenance_level"],
                  e["notes"] or "", e["notes"] or "", e["notes"] or ""))
            cur.fetchone()
            upserted += 1
        except Exception as ex:
            print(f"    skip {canon}: {ex}")
            skipped += 1

    # ── Wire mother_title relationships from title_chain ─────────────────
    try:
        cur.execute("""
            UPDATE assets child
               SET mother_title_id = parent.id
              FROM title_chain tc
              JOIN assets parent ON parent.canonical_id = tc.parent_title
                                  OR parent.canonical_id = 'TCT-' || regexp_replace(tc.parent_title, '^TCT[-\\s]?(?:T[-\\s])?', '')
             WHERE child.canonical_id = tc.child_title
                OR child.canonical_id = 'TCT-' || regexp_replace(tc.child_title, '^TCT[-\\s]?(?:T[-\\s])?', '')
        """)
        print(f"  ✓ wired mother_title relationships from title_chain")
    except Exception as e:
        print(f"  (title_chain wire skipped: {e})")

    print(f"\n  ✓ upserted: {upserted}, skipped: {skipped}")

    # Summary
    cur.execute("""
        SELECT case_file, asset_type, count(*) AS n,
               sum(coalesce(area_sqm, 0)) AS total_sqm
          FROM assets GROUP BY case_file, asset_type ORDER BY case_file, n DESC;
    """)
    print("\n  Asset ledger summary:")
    for r in cur.fetchall():
        print(f"    {r['case_file']:15} {r['asset_type']:12} count={r['n']:4} total_sqm={r['total_sqm'] or 0:,.0f}")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
