#!/usr/bin/env python3
"""Deploy 250 — auto-apply doc_classification_proposals where confidence > 0.9.

Conservative scope:
  - ONLY proposed_action='assign_matter' is auto-applied.
    (flag_unrelated and keep_unscoped require human review — the 10-doc smoke
     test in deploy_244 showed the model misclassifies real T-4497 chain titles
     like T-48336 as 'unrelated'. Higher confidence does NOT correlate with
     higher accuracy for the unrelated bucket.)
  - Only proposals where the doc currently has matter_code IS NULL.
  - Only proposals where proposed_matter_code exists in matters table.

For each applied proposal:
  - documents.matter_code is set
  - proposal.status flips to 'applied'
  - proposal.reviewed_at + reviewed_by = 'auto_high_conf'
  - audited via app.actor='jonathan_deploy_250'

Usage:
  python3 migrations/apply_deploy_250_apply_high_conf_proposals.py            # dry-run
  python3 migrations/apply_deploy_250_apply_high_conf_proposals.py --apply
  python3 migrations/apply_deploy_250_apply_high_conf_proposals.py --threshold 0.95 --apply
"""
import argparse
import sys

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.9,
                    help="Minimum confidence (default: 0.9)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--client", default="MWK")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if args.apply:
        cur.execute("SET LOCAL app.actor = 'jonathan_deploy_250'")

    print(f"Deploy 250 — auto-apply assign_matter proposals @ confidence > {args.threshold}")
    print("=" * 60)

    # Validate valid matter codes for this client
    cur.execute("SELECT matter_code FROM matters WHERE matter_code LIKE %s",
                ("MWK-%" if args.client == "MWK" else f"{args.client}-%",))
    valid = set(r["matter_code"] for r in cur.fetchall())
    print(f"  {len(valid)} valid matter codes for {args.client}")

    # Pull candidates
    cur.execute("""
        SELECT p.id AS pid, p.doc_id, p.proposed_matter_code, p.confidence,
               p.reasoning, d.matter_code AS current_mc, d.case_file
          FROM doc_classification_proposals p
          JOIN documents d ON d.id = p.doc_id
         WHERE p.status = 'proposed'
           AND p.client_id = %s
           AND p.proposed_action = 'assign_matter'
           AND p.confidence > %s
           AND p.proposed_matter_code IS NOT NULL
         ORDER BY p.confidence DESC, p.id
    """, (args.client, args.threshold))
    candidates = cur.fetchall()
    print(f"  {len(candidates)} candidates pre-filter")

    # Filter: only docs currently lacking a matter_code AND proposed_matter in valid set
    apply_list = []
    skip_already_set = 0
    skip_unknown_matter = 0
    for c in candidates:
        if c["current_mc"]:
            skip_already_set += 1
            continue
        if c["proposed_matter_code"] not in valid:
            skip_unknown_matter += 1
            continue
        apply_list.append(c)

    print(f"  → {len(apply_list)} would apply ({skip_already_set} skipped: already tagged; "
          f"{skip_unknown_matter} skipped: unknown matter)")

    # Show breakdown
    by_matter = {}
    for c in apply_list:
        mc = c["proposed_matter_code"]
        by_matter[mc] = by_matter.get(mc, 0) + 1
    print("\n  Distribution of would-be applies:")
    for mc, n in sorted(by_matter.items(), key=lambda x: -x[1]):
        print(f"    {mc:<25s} {n}")

    if not args.apply:
        print("\n  (dry-run — pass --apply to commit)")
        return

    print("\n  Applying...")
    n_applied = 0
    for c in apply_list:
        cur.execute("UPDATE documents SET matter_code = %s WHERE id = %s",
                    (c["proposed_matter_code"], c["doc_id"]))
        cur.execute("""
            UPDATE doc_classification_proposals
               SET status = 'applied',
                   reviewed_at = now(),
                   reviewed_by = 'auto_high_conf',
                   review_notes = 'Auto-applied via deploy_250 (confidence > %s)'
             WHERE id = %s
        """, (args.threshold, c["pid"]))
        n_applied += 1

    conn.commit()
    print(f"  ✓ {n_applied} proposals applied; status='applied'")

    # Post-state
    cur.execute("""
        SELECT matter_code, COUNT(*) AS n
          FROM documents
         WHERE case_file = 'MWK-001' AND matter_code IS NOT NULL
         GROUP BY matter_code ORDER BY 2 DESC
    """)
    print("\n  Post-state MWK-001 matter_code coverage:")
    for r in cur.fetchall():
        print(f"    {r['matter_code']:<25s} {r['n']}")

    cur.execute("SELECT COUNT(*) AS n FROM documents WHERE case_file='MWK-001' AND matter_code IS NULL")
    print(f"\n  Still untagged in MWK-001: {cur.fetchone()['n']}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
