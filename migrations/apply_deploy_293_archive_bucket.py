#!/usr/bin/env python3
"""Deploy 293 — Archive bucket for out-of-scope documents.

Jonathan: 'Fortunato is not part of any of our files it should be put in a
separate folder.'

This deploy:

  A. Registers an 'Archive' client with sub-matters in the matters table so
     out-of-scope documents get a real home (not just NULL) and stop showing
     up in the orphan-triage queue:

       - Archive / ARCHIVE-FORTUNATO-TABCO  (the original Fortunato/Tabco/Basco
                                              land record that prompted this)
       - Archive / ARCHIVE-NOT-CASE-RELEVANT  (catch-all for future archives)

  B. Moves doc#604 (Fortunato.pdf) to Archive/ARCHIVE-FORTUNATO-TABCO.
     The autolink trigger fires → document_matter_links gets a primary row →
     doc exits the orphan triage queue automatically.

  C. Updates doc_triage.py to also exclude any doc whose case_file = 'Archive'
     belt-and-suspenders, in case the autolink junction misses an archive entry.

  D. Adds scripts/archive_doc.py helper so future archiving is one command:
       archive_doc.py 604               # → ARCHIVE-NOT-CASE-RELEVANT
       archive_doc.py 604 fortunato     # → ARCHIVE-FORTUNATO-TABCO

Idempotent."""
from __future__ import annotations
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ACTOR = "jonathan_deploy_293"

ARCHIVE_MATTERS = [
    ("ARCHIVE-FORTUNATO-TABCO", "Archive", "land_record",
     "Fortunato / Tabco / Basco land record (Fortunato.pdf doc#604) — old typewritten "
     "tax declaration from Daet, Camarines Norte. Not part of MWK / Paracale / Owner. "
     "Archived 2026-05-30 by Jonathan."),
    ("ARCHIVE-NOT-CASE-RELEVANT", "Archive", "out_of_scope",
     "Default bucket for documents identified as not part of any active matter."),
]


def main() -> int:
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = %s", (ACTOR,))

    print("Deploy 293 — Archive bucket")
    print("=" * 32)

    # A0) Register Archive client row first (FK target for matters.client_code)
    # NB: matters.client_code FK targets clients.client_code (NOT case_file),
    # which is a separate column on the clients table. Both must equal 'Archive'.
    print("\n  A0) Register 'Archive' client row")
    cur.execute(
        """
        INSERT INTO clients (name, case_file, client_code, status, source, instructions)
        VALUES ('Archive (out-of-scope documents)', 'Archive', 'Archive', 'Archived', 'system',
                'System-level bucket for documents not part of any active client matter. '
                'Routed here via scripts/archive_doc.py or direct UPDATE.')
        ON CONFLICT (client_code) DO UPDATE SET status = 'Archived'
        RETURNING id, client_code, case_file
        """
    )
    r = cur.fetchone()
    print(f"    ✓ clients.id={r['id']} case_file={r['case_file']} client_code={r['client_code']}")

    # A) Register archive matters
    print("\n  A) Register archive matters in matters table")
    for code, client, mtype, desc in ARCHIVE_MATTERS:
        cur.execute(
            """
            INSERT INTO matters (matter_code, client_code, matter_type, title, description, status, date_opened)
            VALUES (%s, %s, %s, %s, %s, 'archived', CURRENT_DATE)
            ON CONFLICT (matter_code) DO NOTHING
            RETURNING id, matter_code
            """,
            (code, client, mtype, code.replace("ARCHIVE-", "Archive: ").replace("-", " ").title(), desc),
        )
        row = cur.fetchone()
        if row:
            print(f"    ✓ created matter#{row['id']}  {row['matter_code']}")
        else:
            print(f"    · matter exists: {code}")

    # B) Move doc#604 (Fortunato.pdf)
    print("\n  B) Move doc#604 (Fortunato.pdf) to Archive/ARCHIVE-FORTUNATO-TABCO")
    cur.execute(
        """
        UPDATE documents
           SET case_file = 'Archive', matter_code = 'ARCHIVE-FORTUNATO-TABCO'
         WHERE id = 604
        RETURNING id, case_file, matter_code
        """
    )
    r = cur.fetchone()
    if r:
        print(f"    ✓ doc#{r['id']} now case_file={r['case_file']} matter={r['matter_code']}")
    else:
        print("    · doc#604 not found")

    # Verify autolink fired (document_matter_links should now have a primary row)
    cur.execute(
        "SELECT relation_kind, matter_code, linked_by FROM document_matter_links WHERE doc_id = 604"
    )
    links = cur.fetchall()
    print(f"    document_matter_links for doc#604: {len(links)} row(s)")
    for l in links:
        print(f"      {l['relation_kind']:>10}  {l['matter_code']:<28}  by={l['linked_by']}")

    # C) Confirm doc#604 leaves the triage queue
    cur.execute(
        """
        SELECT 1 FROM documents d
         WHERE d.id = 604
           AND NOT EXISTS (SELECT 1 FROM document_matter_links l WHERE l.doc_id = d.id)
        """
    )
    in_triage = cur.fetchone() is not None
    print(f"\n  C) doc#604 still in triage queue? {'YES (bug)' if in_triage else 'NO ✓'}")

    conn.commit()
    print("\n  ✓ COMMITTED")

    # D) Recap: how many archive docs now exist
    cur.execute(
        "SELECT case_file, matter_code, COUNT(*) AS n FROM documents WHERE case_file = 'Archive' GROUP BY 1, 2 ORDER BY 2"
    )
    print("\n  D) Archive bucket contents:")
    for r in cur.fetchall():
        print(f"    {r['case_file']}/{r['matter_code']}: {r['n']} doc(s)")

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
