#!/usr/bin/env python3
"""Deploy 262 — Phase 222 lock ceremony (STAGED, USER-GATED).

This deploy DOES NOT auto-lock anything. It stages 3 batches; each requires
explicit `--batch=N --apply` to actually flip verification_lock='hard'.

Once a row is hard-locked, the reject_locked_write trigger blocks any
UPDATE/DELETE that doesn't carry a valid app.truth_override session var.
Locked rows also write to truth_audit_log on any write attempt.

The 3 batches, in escalating risk:

BATCH 1 — MWK CANONICAL FOUNDATION (LOW RISK)
  * titles: T-4497 (mother), T-32916, T-32917 (main derivatives)
  * entities: the 8 most-cited MWK keystones
    - Mary Worrick Keesey #25
    - Patricia Keesey Zschoche #400
    - Cesar de La Fuente #1348
    - Atty. Bonifacio Jr. Barandon #3061
    - Gloria Balane #15
    - Geraldine K. Hoppe #16
    - Engr. Erwin Balane #3060
    - Atty. Rodolfo Del Rosario Jr. #8877
  Rationale: these facts are independently verified (birth certs,
  RTC docs, official records). Locking prevents accidental drift.

BATCH 2 — MWK CHAIN DERIVATIVES (MEDIUM RISK)
  * titles: T-31298, T-38838, T-47655, T-47656, T-47657, T-48335,
    T-48336, T-49037, T-49060-62, T-52354, T-52536-T-52540
  * title_chain: edges connecting batch-1 titles to batch-2 titles
  Rationale: documented in CLAUDE.md as the 17 sub-subdivisions of
  T-32917. Lock after batch 1 succeeds.

BATCH 3 — DEFENDANT TITLE + INSTRUMENTS (HIGHER RISK)
  * titles: T-079-2021002127 (Balane defendant title)
  * instruments_on_title rows for the void-SPA chain
  * title_transfers for the verified 15 transfer events
  Rationale: these are the load-bearing assertions for CV26360. Lock
  only after Jonathan + Barandon have verified each in court filing.

Usage:
  python3 migrations/apply_deploy_262_phase_222_lock_ceremony.py             # show all 3 batches dry-run
  python3 migrations/apply_deploy_262_phase_222_lock_ceremony.py --batch 1   # dry-run batch 1 only
  python3 migrations/apply_deploy_262_phase_222_lock_ceremony.py --batch 1 --apply
"""
import argparse
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

BATCH_1 = {
    "titles": {
        "where": "tct_number IN ('T-4497', 'T-32916', 'T-32917')",
        "rationale": "Mother + 2 main derivatives — independently verified",
    },
    "entities": {
        "where": "id IN (25, 400, 1348, 3061, 15, 16, 3060, 8877)",
        "rationale": "8 most-cited MWK keystones",
    },
}

BATCH_2 = {
    "titles": {
        "where": """tct_number IN ('T-31298','T-38838','T-47655','T-47656','T-47657',
                                    'T-48335','T-48336','T-49037','T-49060','T-49061','T-49062',
                                    'T-52354','T-52536','T-52537','T-52538','T-52539','T-52540')""",
        "rationale": "17 documented sub-subdivisions of T-32917 (per CLAUDE.md)",
    },
    "title_chain": {
        "where": """parent_title IN ('T-4497','T-32916','T-32917')
                    OR child_title IN ('T-4497','T-32916','T-32917',
                       'T-31298','T-38838','T-47655','T-47656','T-47657',
                       'T-48335','T-48336','T-49037','T-49060','T-49061','T-49062',
                       'T-52354','T-52536','T-52537','T-52538','T-52539','T-52540')""",
        "rationale": "Edges between locked batch-1 + batch-2 titles",
    },
}

BATCH_3 = {
    "titles": {
        "where": "tct_number = 'T-079-2021002127'",
        "rationale": "Balane defendant title (load-bearing CV26360 assertion)",
    },
    "instruments_on_title": {
        "where": "provenance_level = 'verified'",
        "rationale": "Verified instruments only (manual cert)",
    },
    "title_transfers": {
        "where": "provenance_level = 'verified'",
        "rationale": "15 verified transfer events",
    },
}

BATCHES = {1: BATCH_1, 2: BATCH_2, 3: BATCH_3}


def show_batch(cur, batch_num, batch_spec, apply=False):
    print(f"\n## Batch {batch_num}")
    print("-" * 60)
    grand_total = 0
    for table, spec in batch_spec.items():
        cur.execute(f"""
            SELECT COUNT(*) AS already_locked
              FROM {table}
             WHERE ({spec['where']}) AND verification_lock = 'hard'
        """)
        already = cur.fetchone()["already_locked"]
        cur.execute(f"""
            SELECT COUNT(*) AS would_lock
              FROM {table}
             WHERE ({spec['where']}) AND (verification_lock IS NULL OR verification_lock != 'hard')
        """)
        would = cur.fetchone()["would_lock"]
        grand_total += would
        print(f"  {table:<24s} would lock: {would:>3d}  (already locked: {already})")
        print(f"  {'':<24s} rationale: {spec['rationale']}")

        if apply and would > 0:
            cur.execute(f"""
                UPDATE {table}
                   SET verification_lock = 'hard',
                       locked_at = now(),
                       locked_by = 'jonathan_phase_222_batch{batch_num}',
                       lock_reason = %s,
                       content_hash = compute_content_hash({table}.*::text)
                 WHERE ({spec['where']})
                   AND (verification_lock IS NULL OR verification_lock != 'hard')
            """, (f"phase_222_batch{batch_num}: {spec['rationale']}",))
            print(f"  {'':<24s} ✓ locked {cur.rowcount} rows")
    print(f"\n  Batch total: {grand_total} rows would lock")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, choices=[1, 2, 3], help="Show/apply specific batch")
    ap.add_argument("--apply", action="store_true",
                    help="Actually lock the rows. REQUIRES --batch=N. Once locked, "
                         "rows are append-only and require app.truth_override to change.")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    if args.apply:
        conn.autocommit = False
    else:
        conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if args.apply:
        cur.execute("SET LOCAL app.actor = 'jonathan_phase_222'")

    print("Deploy 262 — Phase 222 LOCK CEREMONY (staged)")
    print("=" * 60)

    if args.apply and not args.batch:
        print("  ✗ --apply requires --batch=N. Aborting (lock ops must be explicit).")
        return

    if args.batch:
        show_batch(cur, args.batch, BATCHES[args.batch], apply=args.apply)
    else:
        for n, spec in BATCHES.items():
            show_batch(cur, n, spec, apply=False)
        print("\n  (overview dry-run — pass --batch=N to focus, then --batch=N --apply to lock)")

    if args.apply:
        conn.commit()
        print("\n  ✓ COMMITTED")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
