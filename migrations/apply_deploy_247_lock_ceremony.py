#!/usr/bin/env python3
"""Deploy 247 — Phase 222 lock ceremony (STAGED — requires user go).

Flip verification_lock='hard' on the load-bearing keystone facts that the
truth_tests suite asserts. Once locked:
  - app.actor must be set + app.truth_override='on' (with reason + valid actor)
    to mutate the row
  - content_hash is computed and recorded
  - all writes audited to truth_audit_log (append-only)

Targets (MWK keystone — the ones we can least afford drift on):

  ENTITIES:
    - #25   Mary Worrick Keesey (root estate principal)
    - #400  Patricia Keesey Zschoche (plaintiff, MWK heir)
    - #1348 Cesar de La Fuente (deceased 2017 — the adversary canon)
    - #15   Gloria Balane (defendant in CV26360)

  TITLES:
    - T-4497 (mother title — 17 derivatives chain off this)

  TITLE_CHAIN:
    - All edges where parent='T-111' (operative root → 6 verified children)
    - All edges where parent='T-4497' (mother → derivatives)
    - The OCT T-106 → T-111 edge (ghost-parent → operative root, provenance=inferred_weak)
      *** NOT LOCKED — inferred_weak doesn't qualify for hard lock ***

Default mode = DRY RUN. Re-run with --apply ONLY after user explicitly approves.

Usage:
  python3 migrations/apply_deploy_247_lock_ceremony.py            # dry-run, list targets
  python3 migrations/apply_deploy_247_lock_ceremony.py --apply    # commit (user-gated)
"""
import argparse
import json
import sys

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# Each target: (table, where-clause, params, rationale)
TARGETS = [
    ("entities", "id = %s", (25,),
     "Mary Worrick Keesey — root estate principal; all chain provenance flows from her name"),
    ("entities", "id = %s", (400,),
     "Patricia Keesey Zschoche — plaintiff in CV26360; appears in 307 corpus occurrences"),
    ("entities", "id = %s", (1348,),
     "Cesar de La Fuente — deceased 2017-06-21; the void-SPA + 2016 deed adversary"),
    ("entities", "id = %s", (15,),
     "Gloria Balane — defendant in CV26360, holds contested T-079-2021002127"),
    ("titles", "tct_number = %s", ("T-4497",),
     "TCT T-4497 — the mother title; canonical_parent=T-111; 17 derivatives chain"),
    ("title_chain", "parent_title = %s AND provenance_level = 'verified'", ("T-111",),
     "T-111 → verified children (6 edges)"),
    ("title_chain", "parent_title = %s AND provenance_level = 'verified'", ("T-4497",),
     "T-4497 → verified derivatives"),
]


def show_target(cur, table, where, params, rationale, apply=False):
    cur.execute(f"""
        SELECT id, verification_lock, content_hash, locked_at, locked_by
          FROM {table}
         WHERE {where}
    """, params)
    rows = cur.fetchall()
    print(f"\n  {table} WHERE {where % params}")
    print(f"    rationale: {rationale}")
    print(f"    rows matched: {len(rows)}")
    for r in rows:
        already = (r["verification_lock"] == "hard")
        marker = "🔒 ALREADY LOCKED" if already else "🔓 will lock"
        print(f"      id={r['id']}  {marker}  (current_lock={r['verification_lock']!r})")
    if not apply:
        return 0
    locked = 0
    for r in rows:
        if r["verification_lock"] == "hard":
            continue
        # Locking flips the column. The lockdown trigger will:
        #  - require app.actor (we set it below)
        #  - compute content_hash
        #  - audit-log the change
        cur.execute(f"""
            UPDATE {table}
               SET verification_lock = 'hard',
                   locked_at = now(),
                   locked_by = 'jonathan',
                   lock_reason = %s
             WHERE id = %s
        """, (rationale, r["id"]))
        locked += 1
    print(f"    ✓ locked: {locked}")
    return locked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="Actually flip locks. Without this, dry-run only.")
    ap.add_argument("--reason", default="Phase 222 lock ceremony — keystone facts (deploy_247)",
                    help="Reason recorded with each lock")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = False  # Phase 222 ceremony is transactional
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("Deploy 247 — Phase 222 lock ceremony")
    print("=" * 60)
    if not args.apply:
        print("MODE: DRY RUN (no changes will be made)")
        print("      Re-run with --apply to commit (user approval required)")
    else:
        print("MODE: APPLY — locks will be flipped permanently.")
        print(f"REASON: {args.reason}")

    # The lockdown triggers require app.actor for write authorization.
    # 'jonathan' is in the allowed enum.
    if args.apply:
        cur.execute("SET LOCAL app.actor = 'jonathan'")
        # We're flipping FROM unlocked TO locked. The reject_locked_write trigger
        # only fires when verification_lock IS already 'hard' — initial lock-flip
        # is allowed.
        # However, on subsequent re-runs, hard rows will reject without
        # truth_override. That's expected: the ceremony is one-way.

    total_locked = 0
    for table, where, params, rationale in TARGETS:
        n = show_target(cur, table, where, params, rationale, apply=args.apply)
        total_locked += n

    if args.apply:
        try:
            conn.commit()
            print(f"\n  ✓ COMMITTED — {total_locked} rows newly locked")
        except Exception as e:
            conn.rollback()
            print(f"\n  ✗ ROLLED BACK: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        conn.rollback()
        print("\n  (dry-run — no changes committed)")

    # Final state recap
    cur.execute("""
        SELECT 'titles' AS t, COUNT(*) FILTER (WHERE verification_lock='hard') AS hard FROM titles
        UNION ALL SELECT 'title_chain', COUNT(*) FILTER (WHERE verification_lock='hard') FROM title_chain
        UNION ALL SELECT 'entities', COUNT(*) FILTER (WHERE verification_lock='hard') FROM entities
        UNION ALL SELECT 'instruments_on_title', COUNT(*) FILTER (WHERE verification_lock='hard') FROM instruments_on_title
    """)
    print("\n  Hard-lock coverage:")
    for r in cur.fetchall():
        print(f"    {r['t']:<25s} {r['hard']}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
