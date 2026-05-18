#!/usr/bin/env python3
"""audit_transaction_completeness — per-transaction operative-instrument audit.

For each row in title_transfers + title_chain (the ~40 transactions referenced
in our case), determine if the OPERATIVE INSTRUMENT (deed / SPA / donation /
cancellation order) is actually in the documents corpus. Output a checklist.

Match strategies, in order:
  1. Direct FK match: title_transfers.cnr_received_doc_id /
     title_transfers.cancelled_by_doc_id
  2. transfer_documents join table (transfer_id → doc_id with role='primary')
  3. Metadata search: documents.extracted_text contains both titles AND a
     party-name token + classification matches instrument_type
  4. Filename heuristic: filename matches a transfer-bearing pattern
     (e.g., 'deed_of_sale', 'donation', 'SPA') near the transfer_date

For each transaction:
  - present:  >=1 strong match (FK or transfer_documents row)
  - probable: only metadata-search match
  - MISSING:  zero matches → flagged for evidence-collection

Output:
  - CSV: /root/landtek/drafts/transaction_completeness_<date>.csv
  - Terminal summary by completeness band
"""
import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
sys.path.insert(0, "/root/landtek")
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def name_token(s):
    if not s: return set()
    return set(re.findall(r'[a-z]{4,}', s.lower()))


def audit():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Pull all transactions from BOTH title_transfers and title_chain.
    # title_chain has more rows (94 verified-only); title_transfers is richer
    # in instrument_type + transferor/transferee fields.
    cur.execute("""
        SELECT 'title_transfers' AS source,
               tt.id AS transfer_id,
               tt.parent_title, tt.derivative_title,
               tt.transferor, tt.transferee_name,
               tt.transfer_date, tt.instrument_type,
               tt.cnr_received_doc_id, tt.cancelled_by_doc_id,
               (SELECT array_agg(td.doc_id ORDER BY (td.role='primary') DESC, td.confidence DESC NULLS LAST)
                  FROM transfer_documents td WHERE td.transfer_id = tt.id) AS linked_doc_ids
          FROM title_transfers tt
         WHERE tt.case_file = 'MWK-001'
         ORDER BY tt.transfer_date NULLS LAST
    """)
    transfers = cur.fetchall()

    cur.execute("""
        SELECT 'title_chain' AS source,
               (tc.parent_title || '→' || tc.child_title) AS transfer_id,
               tc.parent_title, tc.child_title AS derivative_title,
               NULL AS transferor, NULL AS transferee_name,
               NULL::date AS transfer_date, tc.relationship AS instrument_type,
               tc.source_doc_id AS cnr_received_doc_id, NULL::int AS cancelled_by_doc_id,
               ARRAY[tc.source_doc_id] AS linked_doc_ids
          FROM title_chain tc
         WHERE tc.case_file = 'MWK-001'
           AND NOT EXISTS (
             SELECT 1 FROM title_transfers tt2
              WHERE tt2.case_file = 'MWK-001'
                AND tt2.parent_title = tc.parent_title
                AND tt2.derivative_title = tc.child_title
           )
    """)
    chain_only = cur.fetchall()

    all_txns = transfers + chain_only
    print(f"Auditing {len(transfers)} title_transfers + {len(chain_only)} title_chain-only edges = {len(all_txns)} total transactions")

    # Pull all MWK docs for metadata search
    cur.execute("""
        SELECT id, classification, smart_filename, original_filename,
               document_title, doc_date_norm,
               LEFT(extracted_text, 8000) AS text_head
          FROM documents
         WHERE case_file = 'MWK-001'
           AND related_to_doc_id IS NULL
           AND length(coalesce(extracted_text,'')) >= 200
    """)
    docs = cur.fetchall()
    docs_by_id = {d["id"]: d for d in docs}

    rows = []
    for t in all_txns:
        # ── Strategy 1: direct FK ─────────────────────────────────────────
        primary_doc_id = None
        primary_source = None
        if t.get("cnr_received_doc_id") and t["cnr_received_doc_id"] in docs_by_id:
            primary_doc_id = t["cnr_received_doc_id"]
            primary_source = "FK_cnr_received_doc_id"
        elif t.get("cancelled_by_doc_id") and t["cancelled_by_doc_id"] in docs_by_id:
            primary_doc_id = t["cancelled_by_doc_id"]
            primary_source = "FK_cancelled_by_doc_id"
        # ── Strategy 2: transfer_documents join ──────────────────────────
        elif t.get("linked_doc_ids"):
            for did in t["linked_doc_ids"]:
                if did and did in docs_by_id:
                    primary_doc_id = did
                    primary_source = "transfer_documents_join"
                    break

        # ── Strategy 3: metadata search ──────────────────────────────────
        metadata_candidates = []
        if not primary_doc_id and t.get("parent_title") and t.get("derivative_title"):
            parent = t["parent_title"].replace("T-", "").strip()
            derivative = t["derivative_title"].replace("T-", "").strip()
            transferee_tokens = name_token(t.get("transferee_name"))
            transferor_tokens = name_token(t.get("transferor"))
            for d in docs:
                blob = " ".join(filter(None, [d.get("smart_filename"),
                                                d.get("original_filename"),
                                                d.get("document_title"),
                                                d.get("text_head")])).lower()
                hit_parent = parent.lower() in blob if parent else False
                hit_deriv  = derivative.lower() in blob if derivative else False
                hit_transferee = bool(transferee_tokens & name_token(blob)) if transferee_tokens else False
                hit_transferor = bool(transferor_tokens & name_token(blob)) if transferor_tokens else False
                # Require both titles to appear AND at least one party token
                if hit_parent and hit_deriv and (hit_transferee or hit_transferor):
                    metadata_candidates.append(d["id"])
            if metadata_candidates and not primary_doc_id:
                primary_doc_id = metadata_candidates[0]
                primary_source = "metadata_search"

        # ── Completeness classification ──────────────────────────────────
        if primary_source in ("FK_cnr_received_doc_id", "FK_cancelled_by_doc_id",
                                "transfer_documents_join"):
            completeness = "present"
        elif primary_source == "metadata_search":
            completeness = "probable"
        else:
            completeness = "MISSING"

        # Missing-evidence list — only meaningful if MISSING
        missing = []
        if completeness == "MISSING":
            if not t.get("transfer_date"):
                missing.append("no_transfer_date")
            if not t.get("transferor"):
                missing.append("no_transferor")
            if not t.get("transferee_name"):
                missing.append("no_transferee")
            if not t.get("instrument_type"):
                missing.append("no_instrument_type")
            missing.append("no_primary_doc")

        rows.append({
            "source_table": t["source"],
            "transfer_id": t["transfer_id"],
            "parent_title": t.get("parent_title"),
            "derivative_title": t.get("derivative_title"),
            "transferor": (t.get("transferor") or "")[:60],
            "transferee": (t.get("transferee_name") or "")[:60],
            "transfer_date": t.get("transfer_date"),
            "instrument_type": t.get("instrument_type"),
            "completeness": completeness,
            "primary_doc_id": primary_doc_id,
            "primary_source": primary_source,
            "missing_fields": ",".join(missing) if missing else "",
            "metadata_candidates_extra": ",".join(str(x) for x in metadata_candidates[1:6]) if len(metadata_candidates) > 1 else "",
        })

    # Write CSV
    out_dir = Path("/root/landtek/drafts"); out_dir.mkdir(exist_ok=True)
    csv_path = out_dir / f"transaction_completeness_{date.today().isoformat()}.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # Summary
    band_counts = Counter(r["completeness"] for r in rows)
    print()
    print("═" * 75)
    print("PER-TRANSACTION COMPLETENESS")
    print("═" * 75)
    print(f"  ✅ present (strong primary-doc link):       {band_counts['present']:>3d}")
    print(f"  🟡 probable (metadata-search match only):   {band_counts['probable']:>3d}")
    print(f"  🔴 MISSING (no operative instrument found): {band_counts['MISSING']:>3d}")
    print(f"  ─────────────────────────────────────────────")
    print(f"  Total:                                       {len(rows):>3d}")
    print()
    print(f"Wrote: {csv_path}")
    print()
    print("═" * 75)
    print("MISSING-INSTRUMENT TRANSACTIONS (research priority list)")
    print("═" * 75)
    missing_rows = [r for r in rows if r["completeness"] == "MISSING"]
    for r in missing_rows[:25]:
        d = r.get("transfer_date") or "—"
        title_str = f"{r['parent_title']} → {r['derivative_title']}"
        parties = f"{r['transferor'] or '?'} → {r['transferee'] or '?'}"
        print(f"  [{r['source_table'][:5]} #{str(r['transfer_id']):>10}] {str(d):12s} "
              f"{(r['instrument_type'] or '?')[:25]:25s}  {title_str[:30]:30s}  {parties[:60]}")
    if len(missing_rows) > 25:
        print(f"  ... and {len(missing_rows) - 25} more in CSV")


if __name__ == "__main__":
    audit()
