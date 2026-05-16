#!/usr/bin/env python3
"""Resolve TCT ↔ ARP linkage from tax-doc corpus (deploy_115).

For each Tax Document with extracted text:
  1. Find ARP/Tax Dec number (we already have it in asset_valuations)
  2. Find ALL TCT/OCT references in the body
  3. Insert title_tax_links row(s)

Also backfills titles.lifecycle_status from title_chain + title_transfers:
  - 'superseded' if cancelled_by another title (per cancelled_by_title)
  - 'active' if no cancellation record
  - 'contested' if title appears in active matter as subject
"""
import re
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# TCT/OCT number patterns
TCT_RX = re.compile(r"\b((?:TCT|OCT)[\.\-\s]*(?:No\.?\s*)?:?\s*T?[\-\s]?\d{3,7}(?:[\-\s]\d{4,7})?)\b", re.IGNORECASE)
PIN_RX = re.compile(r"\b(\d{3}-\d{2}-\d{3}-\d{2}-\d{3,4})\b")
ARP_RX = re.compile(r"\b(GR-\d{4}-[A-Z]{2}-\d{2}-\d{3}-\d{5}|\d{3}-\d{5}|ARP-\d{4,})\b", re.IGNORECASE)

def normalize_tct(s):
    """Normalize a TCT reference to canonical 'T-XXXXX' or 'T-XXX-XXXXXXX' form."""
    s = re.sub(r"^(TCT|OCT)[\.\-\s]*(No\.?)?[:\s]*", "", s.strip(), flags=re.IGNORECASE)
    s = re.sub(r"\s+", "", s)
    if not s.upper().startswith("T-"):
        # Try to add T- prefix if missing
        if re.match(r"^\d", s):
            s = "T-" + s
    return s.upper()


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # 1. Resolve ARP → TCT links from tax docs
    cur.execute("""
        SELECT av.asset_title AS arp_no, av.source_docs[1] AS doc_id, av.tax_dec_no,
               d.extracted_text, d.smart_filename
          FROM asset_valuations av
          JOIN documents d ON d.id = av.source_docs[1]
         WHERE av.notes LIKE 'extracted from tax doc%'
           AND d.extracted_text IS NOT NULL
    """)
    rows = cur.fetchall()
    print(f"  scanning {len(rows)} tax-doc records for TCT refs …")

    new_links = 0
    for r in rows:
        arp = r["arp_no"]
        doc_id = r["doc_id"]
        text = r["extracted_text"][:30000]
        # Find TCT references
        tct_matches = set()
        for m in TCT_RX.finditer(text):
            raw = m.group(1)
            norm = normalize_tct(raw)
            # Filter obvious noise — must look like a real TCT
            if re.match(r"^T-\d{4,7}", norm) or re.match(r"^T-\d{3}-\d{4,7}", norm):
                tct_matches.add(norm)
        if not tct_matches:
            continue
        for tct in tct_matches:
            try:
                cur.execute("""
                    INSERT INTO title_tax_links
                      (title_no, arp_no, link_source, source_doc_id, confidence, notes)
                    VALUES (%s, %s, 'regex_scan_v1', %s, 0.85,
                            %s)
                    ON CONFLICT (title_no, arp_no) DO NOTHING
                    RETURNING id
                """, (tct, arp, doc_id, f"Found TCT '{tct}' alongside ARP '{arp}' in tax doc #{doc_id}"))
                if cur.fetchone():
                    new_links += 1
            except Exception as e:
                print(f"  ⚠ doc#{doc_id} {arp}↔{tct}: {e}")

    print(f"  + {new_links} new title↔ARP links")

    # Show distribution
    cur.execute("SELECT count(DISTINCT title_no) AS titles, count(DISTINCT arp_no) AS arps, count(*) AS links FROM title_tax_links")
    s = cur.fetchone()
    print(f"  total: {s['links']} links across {s['titles']} TCTs ↔ {s['arps']} ARPs")

    # 2. Backfill titles.lifecycle_status
    cur.execute("""
        UPDATE titles t
           SET lifecycle_status =
                 CASE
                   WHEN t.cancelled_by_title IS NOT NULL AND t.cancelled_by_title <> '' THEN 'superseded'
                   WHEN EXISTS (
                     SELECT 1 FROM title_chain tc WHERE tc.parent_title = t.tct_number
                   ) THEN 'superseded'
                   ELSE 'active'
                 END,
               lifecycle_updated_at = now()
         WHERE lifecycle_status IS NULL OR lifecycle_status = 'unknown'
    """)
    print(f"  ✓ titles.lifecycle_status backfilled: {cur.rowcount} rows updated")

    # 3. Seed title_matter_links for known case-26-360 titles
    cur.execute("""
        INSERT INTO title_matter_links (title_no, matter_code, relationship, notes)
        VALUES
          ('T-52540', 'MWK-CV26360', 'subject',
           'Mother title cancelled in 2021 by Deed of Sale to Balane — subject of accion reinvindicatoria'),
          ('T-079-2021002126', 'MWK-CV26360', 'subject',
           'Derivative TCT issued to Gloria Balane after cancelled T-52540 — primary target for cancellation in 26-360'),
          ('T-32917', 'MWK-CV26360', 'evidence',
           'Sister TCT to T-52540 under same Lot 2-X-6; contains the encumbrances and instrument trail'),
          ('T-4497', 'MWK-CV26360', 'evidence',
           'Mother title for entire Worrick-Keesey estate; T-52540 derives from this'),
          ('T-4497', 'MWK-ARTA-DILG', 'subject',
           'Property subject of road-donation dispute + Mayor Pajarillo intransigence ARTA complaint'),
          ('T-4497', 'MWK-TCT4497', 'subject',
           'Mother title — focus of chain-verification matter'),
          ('T-4497', 'MWK-ESTATE', 'subject',
           'Mother title — focus of estate administration')
        ON CONFLICT (title_no, matter_code, relationship) DO NOTHING
        RETURNING title_no, matter_code, relationship
    """)
    seeded = cur.fetchall()
    print(f"  + {len(seeded)} title_matter_links seeded:")
    for s in seeded:
        print(f"    {s['title_no']:25s} → {s['matter_code']:18s} ({s['relationship']})")

    # 4. For contested titles (subject in active matter), upgrade lifecycle_status
    cur.execute("""
        UPDATE titles t
           SET lifecycle_status = 'contested',
               lifecycle_updated_at = now(),
               lifecycle_notes = COALESCE(t.lifecycle_notes,'') ||
                                 ' | Contested in: ' || (
                                   SELECT string_agg(matter_code, ', ')
                                     FROM title_matter_links
                                    WHERE title_no = t.tct_number AND relationship='subject'
                                 )
         WHERE EXISTS (
           SELECT 1 FROM title_matter_links tml
             JOIN matters m ON m.matter_code = tml.matter_code
            WHERE tml.title_no = t.tct_number
              AND tml.relationship = 'subject'
              AND m.status = 'active'
         )
    """)
    print(f"  ✓ marked {cur.rowcount} titles as 'contested'")

    # 5. Summary
    cur.execute("""
        SELECT lifecycle_status, count(*) FROM titles GROUP BY lifecycle_status ORDER BY count(*) DESC
    """)
    for r in cur.fetchall():
        print(f"    {r['lifecycle_status']:20s}  {r['count']}")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
