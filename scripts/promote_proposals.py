#!/usr/bin/env python3
"""promote_proposals.py — Interactive review + promotion of proposed changes.

Per design sign-off (Q3): per-row default, --batch flag for lockdown ceremony
(still requires single final 'YES LOCK ALL' confirmation).

Per design Q1: actor must be one of: jonathan, barandon, manual_review.

Promotion path:
  1. Authenticate actor (CLI prompt)
  2. List pending proposals
  3. For each: display + ask approve/reject/skip
  4. On approve: SET LOCAL session vars + apply proposed change + lock if requested
  5. truth_audit trigger captures OVERRIDE entry

Usage:
  python3 promote_proposals.py review                       # interactive per-row
  python3 promote_proposals.py review --batch \\
      --reason "Phase 222 initial lockdown ceremony"        # batch
  python3 promote_proposals.py review --table titles        # filter
  python3 promote_proposals.py list                         # just list, no action

The script does NOT bypass triggers. It uses the same SET LOCAL override flow
that any caller would.
"""
import argparse
import json
import sys

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
VALID_ACTORS = ("jonathan", "barandon", "manual_review")


def prompt(msg, valid=None, default=None):
    """Prompt user; validate against `valid` list if given."""
    while True:
        suffix = f" [{default}]" if default else ""
        ans = input(f"{msg}{suffix}: ").strip()
        if not ans and default:
            ans = default
        if not valid or ans in valid:
            return ans
        print(f"  → must be one of: {valid}")


def authenticate_actor():
    actor = prompt(f"Actor (one of {VALID_ACTORS})", valid=VALID_ACTORS)
    print(f"  authenticated as: {actor}")
    return actor


def list_pending(cur, filter_table=None):
    sql = """
        SELECT id, target_table, target_row_id, operation, proposed_at,
               proposed_by, rationale, proposed_state
          FROM proposed_changes
         WHERE review_status = 'pending'
    """
    params = []
    if filter_table:
        sql += " AND target_table = %s"
        params.append(filter_table)
    sql += " ORDER BY proposed_at"
    cur.execute(sql, params)
    return cur.fetchall()


def render_proposal(p):
    """Compact textual rendering of a proposal for the reviewer."""
    lines = []
    lines.append(f"┌─ proposal #{p['id']} — {p['operation']} on {p['target_table']}")
    if p['target_row_id']:
        lines.append(f"│  target row id: {p['target_row_id']}")
    lines.append(f"│  proposed by:   {p['proposed_by']}  at {p['proposed_at']}")
    if p.get('rationale'):
        lines.append(f"│  rationale:     {p['rationale'][:200]}")
    lines.append(f"│  proposed state:")
    state = p['proposed_state']
    for k, v in (state.items() if isinstance(state, dict) else []):
        v_str = repr(v)[:80]
        lines.append(f"│    {k}: {v_str}")
    lines.append(f"└─")
    return "\n".join(lines)


def apply_proposal(cur, proposal, actor, reason, lock_after=False):
    """Apply a single approved proposal. Uses SET LOCAL override session vars."""
    target = proposal['target_table']
    op = proposal['operation']
    state = proposal['proposed_state']

    # Set override session vars BEFORE any write (transaction-scoped)
    cur.execute("SET LOCAL app.actor = %s", (actor,))
    cur.execute("SET LOCAL app.truth_override = 'on'")
    cur.execute("SET LOCAL app.truth_override_actor = %s", (actor,))
    cur.execute("SET LOCAL app.truth_override_reason = %s",
                (f"promote proposal #{proposal['id']}: {reason}",))

    if op == 'INSERT':
        cols = list(state.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_list = ", ".join(f'"{c}"' for c in cols)
        cur.execute(
            f'INSERT INTO "{target}" ({col_list}) VALUES ({placeholders}) RETURNING id',
            list(state.values()),
        )
        if cur.description:
            r = cur.fetchone()
            new_id = r['id'] if isinstance(r, dict) else r[0]
        else:
            new_id = None
    elif op == 'UPDATE':
        if not proposal['target_row_id']:
            raise ValueError(f"UPDATE proposal #{proposal['id']} missing target_row_id")
        set_clauses = ", ".join(f'"{c}" = %s' for c in state.keys())
        cur.execute(
            f'UPDATE "{target}" SET {set_clauses} WHERE id = %s',
            list(state.values()) + [proposal['target_row_id']],
        )
        new_id = proposal['target_row_id']
    elif op == 'DELETE':
        if not proposal['target_row_id']:
            raise ValueError(f"DELETE proposal #{proposal['id']} missing target_row_id")
        cur.execute(f'DELETE FROM "{target}" WHERE id = %s', (proposal['target_row_id'],))
        new_id = None
    else:
        raise ValueError(f"Unknown operation: {op}")

    # Lock if requested (separate UPDATE; trigger logs as OVERRIDE)
    if lock_after and new_id and op != 'DELETE':
        # Compute content_hash for the just-written row
        cur.execute(
            f'''UPDATE "{target}"
                  SET verification_lock = 'hard',
                      locked_at = NOW(),
                      locked_by = %s,
                      lock_reason = %s,
                      content_hash = compute_content_hash(
                          to_jsonb({target}.*)
                          - 'verification_lock' - 'locked_at' - 'locked_by'
                          - 'lock_reason' - 'content_hash' - 'created_at'
                          - 'updated_at' - 'cited_by_compound_claims'
                          - 'external_state_last_verified'
                      )
                WHERE id = %s''',
            (actor, f"promoted via proposal #{proposal['id']}: {reason}", new_id),
        )

    # Mark proposal as approved + promoted
    cur.execute("""
        UPDATE proposed_changes
           SET review_status = 'approved',
               reviewed_by = %s,
               reviewed_at = NOW(),
               promoted_at = NOW(),
               promoted_with_lock = %s
         WHERE id = %s
    """, (actor, 'hard' if lock_after else None, proposal['id']))

    return new_id


def reject_proposal(cur, proposal, actor, reason):
    cur.execute("""
        UPDATE proposed_changes
           SET review_status = 'rejected',
               reviewed_by = %s,
               reviewed_at = NOW(),
               rejection_reason = %s
         WHERE id = %s
    """, (actor, reason, proposal['id']))


def cmd_list(args):
    conn = psycopg2.connect(DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    proposals = list_pending(cur, args.table)
    if not proposals:
        print("No pending proposals.")
    else:
        print(f"{len(proposals)} pending proposal(s):")
        for p in proposals:
            print(render_proposal(p))
            print()
    cur.close()
    conn.close()


def cmd_review(args):
    actor = authenticate_actor()

    if args.batch and not args.reason:
        print("--batch requires --reason")
        sys.exit(2)
    batch_reason = args.reason

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    proposals = list_pending(cur, args.table)
    if not proposals:
        print("No pending proposals.")
        return
    print(f"\n{len(proposals)} pending proposal(s).\n")

    if args.batch:
        # Show all + final single confirmation
        for p in proposals:
            print(render_proposal(p))
            print()
        confirm = prompt(
            "Type 'YES LOCK ALL' to promote ALL above proposals (with lock=hard) "
            "under the given reason. Anything else aborts",
        )
        if confirm != "YES LOCK ALL":
            print("Aborted.")
            return
        approved = 0
        for p in proposals:
            try:
                with conn:  # transaction per proposal
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                        apply_proposal(c, p, actor, batch_reason, lock_after=True)
                approved += 1
                print(f"  ✓ promoted #{p['id']}")
            except Exception as e:
                print(f"  ✗ FAILED #{p['id']}: {e}")
        print(f"\n→ {approved}/{len(proposals)} promoted with lock=hard.")
    else:
        # Per-row interactive
        for p in proposals:
            print(render_proposal(p))
            action = prompt("approve / reject / skip", valid=("approve", "reject", "skip"),
                            default="skip")
            if action == "skip":
                print("  ↳ skipped\n")
                continue
            try:
                with conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                        if action == "approve":
                            reason = prompt("Reason for approval")
                            lock_q = prompt("Lock after promotion? (yes/no)",
                                            valid=("yes", "no"), default="no")
                            apply_proposal(c, p, actor, reason,
                                           lock_after=(lock_q == "yes"))
                            print(f"  ✓ promoted #{p['id']}"
                                  f" (lock={'hard' if lock_q == 'yes' else 'none'})\n")
                        elif action == "reject":
                            reason = prompt("Reason for rejection")
                            reject_proposal(c, p, actor, reason)
                            print(f"  ↳ rejected #{p['id']}\n")
            except Exception as e:
                print(f"  ✗ FAILED #{p['id']}: {e}\n")

    cur.close()
    conn.close()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp_list = sub.add_parser("list", help="List pending proposals (no action)")
    sp_list.add_argument("--table", help="Filter by target_table")
    sp_list.set_defaults(func=cmd_list)

    sp_rev = sub.add_parser("review", help="Interactively review and promote")
    sp_rev.add_argument("--table", help="Filter by target_table")
    sp_rev.add_argument("--batch", action="store_true",
                        help="Batch-promote all pending (requires single YES LOCK ALL)")
    sp_rev.add_argument("--reason", help="Batch mode: shared reason for promotion")
    sp_rev.set_defaults(func=cmd_review)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
