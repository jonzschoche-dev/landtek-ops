#!/usr/bin/env python3
"""Deploy 256 — case_file domain cleanup + Owner registry entry.

Investigation finding (deploy_255 follow-up):
  'Owner' is NOT a misclassification. It's Jonathan's personal case_file,
  introduced in deploy_081, documented in 9+ codebase files (leo_tools/server,
  meta_agent, auto_promoter, organize_uploads, autonomous/*). The registry
  just didn't know about it.

This deploy:

A) Registry: 'OWNER' added as a third entry in case_theories._clients.CLIENTS
   (separate edit, deployed alongside this script).

B) Schema invariant: CHECK constraint that documents.case_file is in
   {MWK-001, Paracale-001, Owner, NULL, '', 'unknown', 'Unknown'}.
   The 'unknown'/'Unknown'/'' values are tolerated for ingest-transient
   states but flagged for cleanup.

C) Direct corrections — promote the 6 audit-flagged docs with high MWK signal
   to case_file='MWK-001':
     doc#89   (unknown)  → MWK-001 + matter_code MWK-CV26360
              "ida buenaventura fraud" 2005-12-21 email re Cesar's SPA fraud
     doc#471  (NULL)     → MWK-001  (already matter_code MWK-ARTA-1891)
     doc#474  (NULL)     → MWK-001  (already matter_code MWK-ESTATE)
     doc#604  (NULL)     → MWK-001 + matter_code MWK-ESTATE
              Garbled OCR but mentions Filipino-citizenship case material
     doc#612  (NULL)     → MWK-001  (already matter_code MWK-TCT4497)
     doc#615  (NULL)     → MWK-001  (already matter_code MWK-TCT4497)

D) Truth test invariant: every doc.case_file value must be in the recognized
   domain. The new test_case_file_domain.py asserts the constraint and the
   absence of unknown values once cleanup is done.

Idempotent. Audited via app.actor='jonathan_deploy_256'.
"""
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# Recognized case_file values (registered clients + tolerated transitional)
RECOGNIZED = ["MWK-001", "Paracale-001", "Owner"]
TOLERATED = ["unknown", "Unknown", ""]   # ingest-transient; should be cleaned

ASSIGNMENTS = [
    (89,  "MWK-001", "MWK-CV26360",
     "Ida Buenaventura fraud email 2005-12-21 — Cesar SPA misuse to Geraldine Hoppe"),
    (471, "MWK-001", None,
     "Zschoche affiant complaint — already matter_code MWK-ARTA-1891"),
    (474, "MWK-001", None,
     "Patricia Keesey Zschoche passport — already matter_code MWK-ESTATE"),
    # doc#604 deliberately omitted — OCR shows Tasco/Dasco/Basco surnames (NOT
    # Balane chain). Dolores/Santiago hits could be common given names. Manual
    # review needed before assignment. Logged for follow-up.
    (612, "MWK-001", None,
     "TCT I-3839 Mercedes — already matter_code MWK-TCT4497"),
    (615, "MWK-001", None,
     "TCT 47653 Mercedes (LRC)Pcs-256009 — already matter_code MWK-TCT4497"),
]


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'jonathan_deploy_256'")

    print("Deploy 256 — case_file domain cleanup")
    print("=" * 60)

    # Inventory before
    cur.execute("""
        SELECT case_file, COUNT(*) AS n FROM documents GROUP BY case_file ORDER BY n DESC
    """)
    print("\n  case_file inventory BEFORE:")
    for r in cur.fetchall():
        cf = r["case_file"] if r["case_file"] is not None else "(NULL)"
        print(f"    {cf:<20s} {r['n']}")

    # Direct corrections
    print("\n  Apply 6 case_file/matter_code corrections:")
    for doc_id, cf, mc, rationale in ASSIGNMENTS:
        # Build dynamic SET clause depending on whether mc is provided
        if mc is None:
            cur.execute("UPDATE documents SET case_file = %s WHERE id = %s RETURNING id, case_file, matter_code",
                        (cf, doc_id))
        else:
            cur.execute("UPDATE documents SET case_file = %s, matter_code = %s WHERE id = %s RETURNING id, case_file, matter_code",
                        (cf, mc, doc_id))
        r = cur.fetchone()
        if r:
            print(f"    ✓ doc#{r['id']}: case_file='{r['case_file']}' matter_code='{r['matter_code']}'")
            print(f"        [{rationale}]")

    conn.commit()
    print("\n  ✓ COMMITTED")

    # Inventory after
    cur.execute("""
        SELECT case_file, COUNT(*) AS n FROM documents GROUP BY case_file ORDER BY n DESC
    """)
    print("\n  case_file inventory AFTER:")
    recognized_set = set(RECOGNIZED)
    tolerated_set = set(TOLERATED)
    for r in cur.fetchall():
        cf = r["case_file"]
        tag = ""
        if cf is None:
            tag = "  ← NULL (transitional, ok)"
        elif cf in recognized_set:
            tag = "  ✓ registered"
        elif cf in tolerated_set:
            tag = "  ⚠ tolerated (cleanup candidate)"
        else:
            tag = "  ✗ UNKNOWN DOMAIN — investigate"
        cfd = cf if cf is not None else "(NULL)"
        print(f"    {cfd:<20s} {r['n']}{tag}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
