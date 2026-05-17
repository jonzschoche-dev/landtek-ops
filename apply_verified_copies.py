#!/usr/bin/env python3
"""apply_verified_copies — link 14 reviewed duplicate clusters to canonicals.

Per Jonathan 2026-05-17:
  - Auto-select the 14 clusters with specific filenames (TCT-XXXXX, Reply-CV-26-360,
    SPAs/Deeds, specific ARTA codes). Skip generic LGU tax-doc batches.
  - NO deletions from documents or client_history.
  - For each cluster, canonical = document with LONGEST extracted_text.
  - Link others via documents.related_to_doc_id + relationship_kind='verified_copy'.

Reads from drafts/consolidation_candidates_MWK-001_2026-05-17.csv (the prior scan
output). Cluster IDs reference that scan.
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, "/root/landtek")
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
CSV_PATH = "/root/landtek/drafts/consolidation_candidates_MWK-001_2026-05-17.csv"

# The 14 reviewed-and-safe clusters from the prior analysis + cluster 5
# (TIER3 Cesar→Balane deed, added 2026-05-17 per Jonathan).
# Identified by specific filename signatures, NOT generic LGU batch patterns.
TARGET_CLUSTERS = {
    5:  "Cesar→Balane Deed of Absolute Sale (5 ingest paths, TIER3)",
    12: "intestate_estate_of_mary_worrick (2023-02-22 letter)",
    13: "Reply - Civil Case No. 26-360 (2026-04-06)",
    14: "2005-08-15 special_power_of_attorney",
    15: "Road_Donation_Received_by_the_mayors_office (2025-05-22)",
    16: "2023-07-27 Deed (TIER5 same date + type + party)",
    17: "2026-05-04 arta-referral-notice",
    19: "1991 power_of_attorney_Mary_Worrick_Keesey",
    25: "2025-01-08 TCT-52539",
    26: "2025-01-09 TCT-32916_Mary_Worrick_Keesey",
    27: "2023-10-01 information_request_form",
    28: "2025-01-08 TCT_52538",
    29: "2025-03-13 special_power_of_attorney",
    30: "2025-04-28 request_for_property_records",
    31: "CTN SL-2026-0423-1891 (2026-01-01 complaint)",
}


def main():
    # Load CSV
    print(f"Reading {CSV_PATH}")
    cluster_members = defaultdict(list)
    with open(CSV_PATH) as f:
        for row in csv.DictReader(f):
            try:
                cid = int(row["cluster_id"])
            except (ValueError, KeyError):
                continue
            if cid not in TARGET_CLUSTERS:
                continue
            cluster_members[cid].append(row)

    print(f"Loaded {sum(len(m) for m in cluster_members.values())} member rows "
          f"across {len(cluster_members)} target clusters\n")

    # Verify all 14 targets found
    missing = set(TARGET_CLUSTERS) - set(cluster_members)
    if missing:
        print(f"⚠ Target clusters not found in CSV: {sorted(missing)}")
        return

    conn = psycopg2.connect(DSN); conn.autocommit = False
    cur = conn.cursor()

    total_linked = 0
    cluster_results = []

    for cid in sorted(cluster_members):
        members = cluster_members[cid]
        # Canonical = longest extracted_text (per user spec)
        def text_len(r):
            try: return int(r["text_len"])
            except (ValueError, TypeError): return 0
        canonical = max(members, key=text_len)
        canonical_id = int(canonical["doc_id"])
        canonical_text_len = text_len(canonical)

        linked_in_cluster = 0
        for m in members:
            doc_id = int(m["doc_id"])
            if doc_id == canonical_id:
                continue
            cur.execute("""
                UPDATE documents
                   SET related_to_doc_id  = %s,
                       relationship_kind  = 'verified_copy',
                       updated_at         = NOW()
                 WHERE id = %s
                   AND (related_to_doc_id IS NULL OR related_to_doc_id <> %s
                        OR relationship_kind IS DISTINCT FROM 'verified_copy')
            """, (canonical_id, doc_id, canonical_id))
            if cur.rowcount > 0:
                linked_in_cluster += 1
                total_linked += 1

        cluster_results.append({
            "cluster_id": cid,
            "description": TARGET_CLUSTERS[cid],
            "canonical_id": canonical_id,
            "canonical_text_len": canonical_text_len,
            "members_total": len(members),
            "newly_linked": linked_in_cluster,
        })

    conn.commit()

    # Report
    print("="*80)
    print("CONSOLIDATION RESULTS — 14 reviewed clusters")
    print("="*80)
    print(f"{'Cluster':<8}{'Canon doc#':<12}{'Members':<10}{'Linked':<8}{'Description'}")
    print("-"*80)
    for r in cluster_results:
        print(f"{r['cluster_id']:<8}{r['canonical_id']:<12}"
              f"{r['members_total']:<10}{r['newly_linked']:<8}"
              f"{r['description'][:50]}")
    print("-"*80)
    print(f"TOTAL: {total_linked} duplicate documents linked to canonical parents")
    print(f"       across {len(cluster_results)} clusters.")
    print()
    print("NO rows deleted. NO data loss. Every doc remains queryable.")
    print(f"Field set: documents.related_to_doc_id, relationship_kind='verified_copy'")

    # Verify in DB
    cur.execute("""
        SELECT COUNT(*) FROM documents
         WHERE case_file = 'MWK-001'
           AND relationship_kind = 'verified_copy'
    """)
    db_count = cur.fetchone()[0]
    print(f"\nDB verification: {db_count} MWK-001 docs now tagged 'verified_copy'")


if __name__ == "__main__":
    main()
