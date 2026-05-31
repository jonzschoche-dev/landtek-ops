#!/usr/bin/env python3
"""archive_doc.py — move a document to the Archive bucket.

Usage:
  archive_doc.py 604                    # → Archive / ARCHIVE-NOT-CASE-RELEVANT
  archive_doc.py 604 fortunato          # → Archive / ARCHIVE-FORTUNATO-TABCO
  archive_doc.py 604 --matter ARCHIVE-CUSTOM-CODE   # explicit code

The Archive bucket lives under client_code='Archive' in the matters table
(deploy_293). Once moved, the doc exits the orphan triage queue and shows up
in the Archive folder views."""
from __future__ import annotations
import argparse
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# Short tags users can type instead of the full matter code
TAG_MAP = {
    "fortunato": "ARCHIVE-FORTUNATO-TABCO",
    "tabco": "ARCHIVE-FORTUNATO-TABCO",
    "basco": "ARCHIVE-FORTUNATO-TABCO",
    "default": "ARCHIVE-NOT-CASE-RELEVANT",
    "noise": "ARCHIVE-NOT-CASE-RELEVANT",
    "unrelated": "ARCHIVE-NOT-CASE-RELEVANT",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("doc_id", type=int)
    ap.add_argument("tag_or_matter", nargs="?", default="default",
                    help="short tag or explicit ARCHIVE-* matter code")
    ap.add_argument("--matter", default=None,
                    help="explicit matter code (overrides positional tag)")
    args = ap.parse_args()

    matter = args.matter or TAG_MAP.get(args.tag_or_matter.lower(), args.tag_or_matter)
    if not matter.startswith("ARCHIVE-"):
        print(f"refusing: matter {matter!r} doesn't start with ARCHIVE- — that's "
              f"reserved for the archive bucket. Pass --matter explicitly if you mean it.")
        return 1

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'archive_doc.py'")

    # Verify matter exists
    cur.execute("SELECT 1 FROM matters WHERE matter_code = %s", (matter,))
    if not cur.fetchone():
        print(f"matter {matter!r} not registered in matters table. Register it first or use a known tag.")
        return 1

    cur.execute(
        """
        UPDATE documents
           SET case_file = 'Archive', matter_code = %s
         WHERE id = %s
        RETURNING id, case_file, matter_code,
                  COALESCE(smart_filename, original_filename, '(unnamed)') AS name
        """,
        (matter, args.doc_id),
    )
    r = cur.fetchone()
    if not r:
        print(f"doc#{args.doc_id} not found")
        return 1
    conn.commit()
    print(f"✓ doc#{r['id']} → {r['case_file']}/{r['matter_code']}")
    print(f"  ({r['name']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
