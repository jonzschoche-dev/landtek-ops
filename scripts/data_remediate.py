#!/usr/bin/env python3
"""data_remediate.py — apply the high-confidence data-layer noise unlink (reviewable + reversible). OPERATOR-RUN.

The autonomous agent is (correctly) blocked from mass-DELETE on the shared production DB, so this is the
clean way to apply it yourself. It only touches CLEAR, high-confidence noise:
  • image files with ZERO verified facts anywhere (and not named annex/exhibit) — e.g. image.png, Outlook-*.png
  • relevance-engine OFF-PROFILE links (confirmed conflations, e.g. the doc-776 Torralba contamination)
It does NOT touch the murky 'foreign' heuristic or the over-dropping LLM triage.

Every removed row is backed up to document_matter_links_unlinked_bak first, so --relink fully undoes it.

  python3 scripts/data_remediate.py            # PLAN — show what would be unlinked (read-only, default)
  python3 scripts/data_remediate.py --unlink   # back up + DELETE the noise links
  python3 scripts/data_remediate.py --relink    # UNDO — restore every backed-up link
"""
import os
import sys

import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

NOISE_CTE = """
WITH noise AS (
  SELECT l.doc_id, l.matter_code, 'image-noise'::text reason
  FROM document_matter_links l JOIN documents d ON d.id=l.doc_id
  WHERE coalesce(d.original_filename,d.smart_filename,'') ~* '\\.(png|jpe?g|gif|bmp|tiff?|webp)$'
    AND coalesce(d.original_filename,d.smart_filename,'') !~* 'annex|exhibit'
    AND NOT EXISTS (SELECT 1 FROM matter_facts f WHERE f.source_kind='doc' AND f.source_id=d.id::text
                    AND f.provenance_level='verified')
  UNION
  SELECT l.doc_id, l.matter_code, 'off-profile'
  FROM document_matter_links l JOIN matter_relevance mr ON mr.doc_id=l.doc_id AND mr.focal_matter=l.matter_code
  WHERE mr.tier='OFF-PROFILE'
)
"""


def main():
    c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS document_matter_links_unlinked_bak
                   (doc_id int, matter_code text, reason text, removed_at timestamptz DEFAULT now())""")

    if "--relink" in sys.argv:
        cur.execute("""INSERT INTO document_matter_links (doc_id, matter_code)
                       SELECT doc_id, matter_code FROM document_matter_links_unlinked_bak
                       ON CONFLICT DO NOTHING""")
        n = cur.rowcount
        cur.execute("DELETE FROM document_matter_links_unlinked_bak")
        print(f"[remediate] RELINKED {n} rows from backup (undo complete).")
        return

    cur.execute(NOISE_CTE + "SELECT reason, count(*) FROM noise GROUP BY reason ORDER BY 2 DESC")
    rows = cur.fetchall()
    total = sum(n for _, n in rows)
    print("Noise links identified:")
    for reason, n in rows:
        print(f"  {reason:14} {n}")
    print(f"  TOTAL          {total}")

    if "--unlink" not in sys.argv:
        cur.execute(NOISE_CTE + """SELECT n.doc_id, n.matter_code, n.reason,
                    left(coalesce(d.original_filename,d.smart_filename,'?'),40)
                    FROM noise n JOIN documents d ON d.id=n.doc_id ORDER BY n.reason, n.doc_id LIMIT 20""")
        print("\nsample:")
        for did, mc, reason, fn in cur.fetchall():
            print(f"  doc:{did:>5} [{reason:11}] {mc:16} {fn}")
        print("\n(PLAN only — re-run with --unlink to apply, --relink to undo afterward)")
        return

    cur.execute("DELETE FROM document_matter_links_unlinked_bak")   # clear any stale/partial backup
    cur.execute(NOISE_CTE + """INSERT INTO document_matter_links_unlinked_bak (doc_id, matter_code, reason)
                SELECT doc_id, matter_code, reason FROM noise""")
    cur.execute(NOISE_CTE + """DELETE FROM document_matter_links l USING noise n
                WHERE l.doc_id=n.doc_id AND l.matter_code=n.matter_code""")
    print(f"\n[remediate] UNLINKED {cur.rowcount} noise links (backed up to document_matter_links_unlinked_bak).")
    print("  undo with: python3 scripts/data_remediate.py --relink")


if __name__ == "__main__":
    main()
