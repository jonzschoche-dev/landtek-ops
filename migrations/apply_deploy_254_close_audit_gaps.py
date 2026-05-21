#!/usr/bin/env python3
"""Deploy 254 — close the gaps surfaced by the manual audit of 252/253.

Two pieces:

A) Assign correct matter_codes to the 9 confirmed misses found in audit.
   Each was an LLM 'flag_unrelated' verdict at ≥0.85 that the user-corrected
   investigation showed is actually MWK litigation.

B) Mark the 9 corresponding proposals as 'superseded' (status flips from
   needs_manual_review).

Doc-level decisions (verified against extracted_text):
  doc#474  → MWK-ESTATE       — U.S. passport for Patricia Keesey Zschoche
  doc#412  → MWK-CV26360      — TCT T-50192 to Rosalina M. Hansol (transferee)
  doc#677  → MWK-CV26360      — 2016 petition filed by Cesar M. de la Fuente
  doc#580  → MWK-CV26360      — Torralba/Juntilla CA case (cluster with 581-585)
  doc#776  → MWK-CV26360      — Torralba/Juntilla petition
  doc#584  → MWK-CV26360      — Juntilla, Torralba, Cantor et al. v. (Civil 8563)
  doc#527  → MWK-CV26360      — Mercedes Lot 403 CAD 1186-D (disputed municipal property)
  doc#528  → MWK-CV26360      — same property declaration (duplicate copy)
  doc#599  → MWK-ESTATE       — Concepcion Garrido (Manuel Garrido lineage) neg death cert

Idempotent. Audited via app.actor='jonathan_deploy_254'.
"""
import sys

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

ASSIGNMENTS = [
    # (doc_id, matter_code, rationale)
    (474, "MWK-ESTATE",  "U.S. passport for Patricia Keesey Zschoche (plaintiff #400) — identity evidence"),
    (412, "MWK-CV26360", "TCT T-50192 registered to Rosalina M. Hansol (#3411) — Balane-chain transferee"),
    (677, "MWK-CV26360", "2016 petition by Cesar de la Fuente (#1348) — void-SPA adversary"),
    (580, "MWK-CV26360", "CA-G.R. SP No. 181607 — Torralba/Juntilla, same case-cluster as 581-585"),
    (776, "MWK-CV26360", "Torralba/Juntilla petition — same case-cluster"),
    (584, "MWK-CV26360", "Civil Case 8563 — Juntilla, Torralba, Cantor et al. (predecessor of CA-181607)"),
    (527, "MWK-CV26360", "Mercedes Lot 403 CAD 1186-D — disputed municipal property"),
    (528, "MWK-CV26360", "Mercedes Lot 403 (duplicate of 527)"),
    (599, "MWK-ESTATE",  "Concepcion Garrido (daughter of Manuel Garrido) — estate genealogy"),
]


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'jonathan_deploy_254'")

    print("Deploy 254 — close audit gaps (9 confirmed misses)")
    print("=" * 60)

    for doc_id, matter_code, rationale in ASSIGNMENTS:
        cur.execute("""
            UPDATE documents
               SET matter_code = %s
             WHERE id = %s AND (matter_code IS NULL OR matter_code != %s)
             RETURNING id, matter_code
        """, (matter_code, doc_id, matter_code))
        r = cur.fetchone()
        if r:
            print(f"  ✓ doc#{doc_id} → matter_code={matter_code}  [{rationale}]")
        else:
            print(f"  · doc#{doc_id} already at {matter_code} (no-op)")

        # Flip the proposal to superseded
        cur.execute("""
            UPDATE doc_classification_proposals
               SET status = 'superseded',
                   reviewed_at = now(),
                   reviewed_by = 'jonathan_deploy_254',
                   review_notes = %s
             WHERE doc_id = %s AND status IN ('proposed', 'needs_manual_review')
        """, (f"[deploy_254] manual review: {rationale} → matter_code={matter_code}", doc_id))

    conn.commit()
    print("\n  ✓ COMMITTED")

    # Recap
    cur.execute("""
        SELECT id, matter_code, case_file
          FROM documents WHERE id = ANY(%s) ORDER BY id
    """, ([a[0] for a in ASSIGNMENTS],))
    print("\n  Final doc state:")
    for r in cur.fetchall():
        print(f"    doc#{r['id']}  case_file={r['case_file']!r}  matter_code={r['matter_code']!r}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
