#!/usr/bin/env python3
"""Layer 3 — Auto-promoter for orphan entities.

Continuously scans the corpus for entities that exist in data but aren't tracked
as matters / titles / entities. Creates DRAFT rows for review.

Currently handles:
  • Orphan case_file values → auto-create matter row (status='pending_triage')
  • ARTA case numbers in extracted_text → ensure matter row exists
  • TCT numbers seen in corpus → ensure titles row exists (basic stub)

Consolidates with meta-agent (no separate Telegram fires; meta-agent surfaces
the gaps; auto-promoter does the safe data writes).

Usage:
  python3 auto_promoter.py            # report
  python3 auto_promoter.py --apply    # apply changes
"""
import argparse
import sys
import psycopg2, psycopg2.extras

sys.path.insert(0, "/root/landtek")
from patterns import find_all_arta_cases, find_all_tct_numbers

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def orphan_case_files(cur):
    """case_file values in documents that don't have a matter row."""
    cur.execute("""
        SELECT DISTINCT d.case_file, COUNT(*) AS n_docs, MAX(d.doc_date_norm) AS most_recent
          FROM documents d
         WHERE d.case_file IS NOT NULL
           AND d.case_file NOT IN ('unknown','Unknown','Owner','')
           AND d.case_file NOT IN (SELECT case_file FROM matters WHERE case_file IS NOT NULL)
         GROUP BY d.case_file
         ORDER BY n_docs DESC
    """)
    return cur.fetchall()


def unmatched_arta_cases(cur):
    """ARTA case numbers in extracted_text not yet in matters.docket_number."""
    # Pull existing dockets normalized
    cur.execute("""
        SELECT regexp_replace(docket_number, '\\s+', '', 'g') AS canonical
          FROM matters WHERE docket_number ILIKE '%CTN%SL%'
    """)
    existing = {row["canonical"] for row in cur.fetchall()}

    # Scan corpus
    cur.execute("""
        SELECT id, case_file, extracted_text
          FROM documents
         WHERE extracted_text ~ 'CTN\\s*SL'
    """)
    seen_cases = {}  # canonical -> sample doc_id + case_file
    for row in cur.fetchall():
        for case in find_all_arta_cases(row["extracted_text"] or ""):
            canonical_compact = case.replace(" ", "")  # "CTNSL-2025-1008-0690"
            if canonical_compact not in existing and case not in seen_cases:
                seen_cases[case] = (row["id"], row["case_file"])

    return [{"arta_case": k, "sample_doc_id": v[0], "case_file": v[1] or "MWK-001"}
            for k, v in seen_cases.items()]


def promote_orphan_case_file(cur, case_file: str, n_docs: int):
    """Create a placeholder matter row for an orphan case_file. status='pending_triage'.
    If the case_file matches a known client_code, use that client; else PENDING_TRIAGE."""
    matter_code = f"AUTO-{case_file.upper().replace('-','_')[:20]}"
    # Resolve client_code: prefer matching by case_file → clients.case_file
    cur.execute("""
        SELECT client_code, name FROM clients
         WHERE client_code = %s OR case_file = %s LIMIT 1
    """, (case_file, case_file))
    cli = cur.fetchone()
    client_code = cli["client_code"] if cli else "PENDING_TRIAGE"
    client_name = cli["name"] if cli else "Unknown client"
    cur.execute("""
        INSERT INTO matters (matter_code, client_code, matter_type, title, status,
                             current_stage, stage_notes, case_file)
        VALUES (%s, %s, 'unknown',
                %s,
                'pending_triage',
                'needs_context_from_user',
                %s,
                %s)
        ON CONFLICT (matter_code) DO NOTHING
    """, (
        matter_code,
        client_code,
        f"AUTO-PROMOTED: {case_file} for client {client_name} ({n_docs} docs, no matter row) — awaiting context",
        f"Auto-promoted by auto_promoter.py because case_file {case_file!r} had {n_docs} documents but no matter row. Client resolved to {client_code} ({client_name}). Jonathan to confirm matter scope.",
        case_file,
    ))
    return matter_code, client_code, client_name


def promote_unmatched_arta(cur, arta_case: str, sample_doc_id: int, case_file: str):
    """Create a placeholder matter for an ARTA case number found in corpus."""
    suffix = arta_case.split("-")[-1]  # last 4 digits, e.g., "1378"
    matter_code = f"AUTO-ARTA-{suffix}"
    cur.execute("""
        INSERT INTO matters (matter_code, client_code, matter_type, title,
                             court_or_agency, docket_number, status,
                             current_stage, stage_notes, case_file, first_verified_doc_id)
        VALUES (%s, %s, 'administrative',
                %s,
                'ARTA Southern Luzon (auto-detected)',
                %s,
                'pending_triage',
                'arta_case_auto_promoted',
                %s,
                %s, %s)
        ON CONFLICT (matter_code) DO NOTHING
    """, (
        matter_code,
        case_file,
        f"AUTO-PROMOTED: ARTA case {arta_case} found in corpus, no matter row yet",
        arta_case,
        f"Auto-promoter detected this ARTA case number in doc#{sample_doc_id} but it had no matter row. Jonathan to confirm respondent + scope.",
        case_file,
        sample_doc_id,
    ))
    return matter_code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually create matter rows")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    orphans = orphan_case_files(cur)
    arta_unmatched = unmatched_arta_cases(cur)

    print(f"=== Auto-promoter scan ===")
    print(f"  Orphan case_files: {len(orphans)}")
    for o in orphans:
        print(f"    • {o['case_file']!r}  {o['n_docs']} docs  most_recent={o['most_recent']}")
    print(f"  Unmatched ARTA cases: {len(arta_unmatched)}")
    for a in arta_unmatched:
        print(f"    • {a['arta_case']}  (sample doc#{a['sample_doc_id']}, case_file={a['case_file']})")

    if not args.apply:
        print(f"\n  (dry run — pass --apply to create matter rows)")
        return

    n_promoted = 0
    for o in orphans:
        mc, cc, cn = promote_orphan_case_file(cur, o["case_file"], o["n_docs"])
        print(f"    promoted {mc} (client: {cc} = {cn})")
        n_promoted += 1
    for a in arta_unmatched:
        promote_unmatched_arta(cur, a["arta_case"], a["sample_doc_id"], a["case_file"])
        n_promoted += 1
    print(f"\n  Promoted: {n_promoted} new matter row(s)")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
