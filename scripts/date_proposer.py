#!/usr/bin/env python3
"""date_proposer.py — light the dark items on the pulse (calendar-is-the-pulse).

The front-end of the pulse. `timeline_coverage.py` counts what's dark; this agent tries
to attach a TIMELINE to each dark goal-bearing object — DETERMINISTICALLY and WITHOUT
FABRICATION. A proposed date is a PROPOSAL, written to the spine only on operator
approval (confirm-before-write). Where no rule grounds a date, it says so honestly
(OPERATOR_INPUT, proposed_date = NULL) — it never invents one.

Rules (most-grounded first):
  DERIVE_FROM_SPINE  a dark matter whose own spine already holds a future date
                     (surfaced_deadlines / case_actions / a resolved calendar_event) →
                     propose the nearest. GROUNDED (the date already exists; just not on
                     matters.next_deadline).
  LINKED_MATTER      an obligation/goal tied to a matter that HAS a date → inherit it
                     (cite the matter). Cascades: approve matter dates, re-scan, the
                     dependents light up.
  RECURRING          an obligation whose text names a cadence (monthly/weekly/quarterly)
                     → propose the next occurrence (clearly labelled).
  OPERATOR_INPUT     no rule fires → surfaced as a worklist with NULL date. Honest.

Matter_plays are NOT proposed here — a ready play inherits its matter's date, so fixing
the matter fixes the play transitively.

Usage:
  python3 scripts/date_proposer.py --scan             # dry: classify + print (no writes)
  python3 scripts/date_proposer.py --scan --apply     # upsert proposal rows
  python3 scripts/date_proposer.py --review           # list pending proposals
  python3 scripts/date_proposer.py --approve <id>     # write the date to the spine
  python3 scripts/date_proposer.py --approve --rule DERIVE_FROM_SPINE   # batch the grounded ones
  python3 scripts/date_proposer.py --reject <id>
"""
import argparse
import calendar
import re
import sys
from datetime import date, timedelta

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
from timeline_coverage import LEGIT_DARK_STATUS, LEGIT_DARK_STAGE_PAT  # noqa: E402

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# target_kind → (table, date_field, key_column)
FIELD_MAP = {
    "matters": ("matters", "next_deadline", "matter_code"),
    "client_goals": ("client_goals", "target_date", "id"),
    "landtek_obligations": ("landtek_obligations", "due_by", "id"),
}


def db():
    return psycopg2.connect(DSN, cursor_factory=psycopg2.extras.DictCursor)


def ensure_schema(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS date_proposals (
            id            SERIAL PRIMARY KEY,
            target_kind   TEXT NOT NULL,
            target_ref    TEXT NOT NULL,
            target_field  TEXT NOT NULL,
            label         TEXT,
            proposed_date DATE,
            basis_rule    TEXT NOT NULL,
            basis_detail  TEXT,
            status        TEXT DEFAULT 'pending',   -- pending|approved|rejected|needs_operator
            created_at    TIMESTAMPTZ DEFAULT now(),
            resolved_at   TIMESTAMPTZ,
            UNIQUE (target_kind, target_ref, target_field)
        )""")


def month_end(d):
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def next_weekday(d, wd):  # wd 0=Mon
    return d + timedelta(days=((wd - d.weekday()) % 7) or 7)


def is_dark_matter(status, stage):
    if any(p in (stage or "") for p in LEGIT_DARK_STAGE_PAT):
        return False
    if (status or "") in LEGIT_DARK_STATUS:
        return False
    return True


# ── rule engines ───────────────────────────────────────────────────────────
def derive_matter_date(cur, mc, docket, case_file):
    """Nearest future date already present in this matter's spine. GROUNDED."""
    cands = []
    cur.execute("SELECT min(due_date) FROM surfaced_deadlines WHERE matter_code=%s AND due_date>=CURRENT_DATE", (mc,))
    r = cur.fetchone()[0]
    if r:
        cands.append((r, "surfaced_deadlines"))
    cur.execute("SELECT min(due_date) FROM case_actions WHERE matter_code=%s AND due_date>=CURRENT_DATE AND status<>'confirmed'", (mc,))
    r = cur.fetchone()[0]
    if r:
        cands.append((r, "case_actions"))
    cur.execute(
        "SELECT min(start_at::date) FROM calendar_events "
        "WHERE related_case IN (%s,%s,%s) AND start_at::date>=CURRENT_DATE "
        "AND COALESCE(status,'')<>'cancelled'", (mc, docket or mc, case_file or mc))
    r = cur.fetchone()[0]
    if r:
        cands.append((r, "calendar_events"))
    if not cands:
        return None, None
    cands.sort()
    return cands[0][0], f"nearest spine date via {cands[0][1]}"


RECUR = [(r"\bmonthly\b|\beach month\b|\bevery month\b", "monthly"),
         (r"\bweekly\b|\beach week\b|\bevery week\b", "weekly"),
         (r"\bquarterly\b|\beach quarter\b", "quarterly")]


def recurrence_date(text, today):
    t = (text or "").lower()
    for pat, kind in RECUR:
        if re.search(pat, t):
            if kind == "monthly":
                me = month_end(today)
                return (me if me >= today else month_end(me + timedelta(days=1))), "monthly cadence → month-end"
            if kind == "weekly":
                return next_weekday(today, 4), "weekly cadence → next Friday"
            if kind == "quarterly":
                q_end_month = ((today.month - 1) // 3 + 1) * 3
                return month_end(date(today.year, q_end_month, 1)), "quarterly cadence → quarter-end"
    return None, None


def strict_goal_match(gtext, dm):
    """Return the single matter whose FULL code or docket (>=5 chars) appears verbatim in
    the goal text, else None. STRICT full-substring match — never loose numeric tokens,
    which false-matched YEARS ("1979 deed") to dockets. Locked by truth_test."""
    gt = (gtext or "").lower()
    hits = [mc for mc, (dl, dk) in dm.items()
            if mc.lower() in gt or (len(dk) >= 5 and dk.lower() in gt)]
    return hits[0] if len(hits) == 1 else None


def dated_matters(cur):
    """matter_code → (next_deadline, docket) for matters with a FUTURE date only.
    Future-only: inheriting a matter's OVERDUE deadline would attach a stale date — a
    dependent of a stale matter is treated as needing operator input, not back-dated."""
    cur.execute("SELECT matter_code, next_deadline, COALESCE(docket_number,'') "
                "FROM matters WHERE next_deadline IS NOT NULL AND next_deadline >= CURRENT_DATE")
    return {mc: (dl, dk) for mc, dl, dk in cur.fetchall()}


# ── scan ───────────────────────────────────────────────────────────────────
def upsert(cur, apply, kind, ref, field, label, pdate, rule, detail, out):
    status = "needs_operator" if rule == "OPERATOR_INPUT" else "pending"
    out.append((rule, ref, pdate, label, detail))
    if not apply:
        return
    cur.execute("""
        INSERT INTO date_proposals (target_kind, target_ref, target_field, label,
            proposed_date, basis_rule, basis_detail, status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (target_kind, target_ref, target_field) DO UPDATE SET
            proposed_date=EXCLUDED.proposed_date, basis_rule=EXCLUDED.basis_rule,
            basis_detail=EXCLUDED.basis_detail, label=EXCLUDED.label,
            status=CASE WHEN date_proposals.status IN ('approved','rejected')
                        THEN date_proposals.status ELSE EXCLUDED.status END
        """, (kind, str(ref), field, label, pdate, rule, detail, status))


def scan(cur, apply):
    today = date.today()
    dm = dated_matters(cur)
    proposals = []

    # 1. dark matters → DERIVE_FROM_SPINE else OPERATOR_INPUT
    cur.execute("""SELECT matter_code, COALESCE(docket_number,''), COALESCE(case_file,''),
        COALESCE(current_stage,''), COALESCE(status,'') FROM matters
        WHERE next_deadline IS NULL AND matter_code NOT LIKE 'AUTO-%'
        ORDER BY matter_code""")
    for mc, dk, cf, stage, status in cur.fetchall():
        if not is_dark_matter(status, stage):
            continue
        d, why = derive_matter_date(cur, mc, dk, cf)
        if d:
            upsert(cur, apply, "matters", mc, "next_deadline", mc, d, "DERIVE_FROM_SPINE", why, proposals)
        else:
            upsert(cur, apply, "matters", mc, "next_deadline", mc, None, "OPERATOR_INPUT",
                   f"no dated child in spine (stage: {stage or status or '?'})", proposals)

    # 2. obligations → RECURRING / LINKED_MATTER / OPERATOR_INPUT
    cur.execute("""SELECT id, COALESCE(matter_code,''), COALESCE(short_label,description,'')
        FROM landtek_obligations WHERE due_by IS NULL
        AND COALESCE(status,'open') NOT IN ('done','fulfilled','closed')""")
    for oid, mc, label in cur.fetchall():
        rd, rwhy = recurrence_date(label, today)
        if rd:
            upsert(cur, apply, "landtek_obligations", oid, "due_by", label, rd, "RECURRING", rwhy, proposals)
        elif mc in dm:  # dm holds future-dated matters only
            upsert(cur, apply, "landtek_obligations", oid, "due_by", label, dm[mc][0],
                   "LINKED_MATTER", f"inherit {mc}.next_deadline", proposals)
        else:
            upsert(cur, apply, "landtek_obligations", oid, "due_by", label, None, "OPERATOR_INPUT",
                   f"standing/ongoing duty or dark matter ({mc or 'no matter'})", proposals)

    # 3. client_goals → LINKED_MATTER (docket token) else OPERATOR_INPUT
    cur.execute("""SELECT id, COALESCE(goal_text,'') FROM client_goals
        WHERE target_date IS NULL AND COALESCE(status,'open') NOT IN ('done','achieved','closed')""")
    for gid, gtext in cur.fetchall():
        hit = strict_goal_match(gtext, dm)  # full-substring only; year-as-docket can't match
        if hit:
            upsert(cur, apply, "client_goals", gid, "target_date", gtext[:60], dm[hit][0],
                   "LINKED_MATTER", f"docket/code match → {hit}", proposals)
        else:
            upsert(cur, apply, "client_goals", gid, "target_date", gtext[:60], None, "OPERATOR_INPUT",
                   "no unambiguous dated matter link", proposals)

    return proposals


def print_scan(proposals, apply):
    order = ["DERIVE_FROM_SPINE", "LINKED_MATTER", "RECURRING", "OPERATOR_INPUT"]
    by = {r: [] for r in order}
    for rule, ref, pdate, label, detail in proposals:
        by.setdefault(rule, []).append((ref, pdate, label, detail))
    grounded = sum(len(by[r]) for r in ("DERIVE_FROM_SPINE", "LINKED_MATTER", "RECURRING"))
    print(f"=== DATE PROPOSER — {len(proposals)} dark item(s) · {grounded} groundable · "
          f"{len(by['OPERATOR_INPUT'])} need you ===\n")
    for rule in order:
        rows = by[rule]
        if not rows:
            continue
        print(f"── {rule} ({len(rows)}) ──")
        for ref, pdate, label, detail in rows:
            ds = pdate.strftime("%b %-d, %Y") if pdate else "—— (you decide)"
            print(f"  {str(ref)[:24]:24} {ds:16} {str(label)[:44]:44} [{detail}]")
        print()
    print("DRY-RUN — pass --apply to write proposal rows." if not apply
          else "Proposals upserted → review with --review, approve with --approve <id>.")


# ── approve / reject ─────────────────────────────────────────────────────────
def cmd_review(cur):
    cur.execute("""SELECT id, target_kind, target_ref, proposed_date, basis_rule, label
        FROM date_proposals WHERE status='pending' ORDER BY basis_rule, id""")
    rows = cur.fetchall()
    if not rows:
        print("No pending proposals (run --scan --apply first).")
        return
    print(f"=== {len(rows)} PENDING date proposals ===")
    for r in rows:
        print(f"  #{r['id']:<4} {r['basis_rule']:18} {r['target_kind']}:{r['target_ref']:<18} "
              f"{r['proposed_date']}  {str(r['label'])[:40]}")
    cur.execute("SELECT count(*) FROM date_proposals WHERE status='needs_operator'")
    print(f"\n(+ {cur.fetchone()[0]} needs_operator items with no proposed date — supply dates to light them)")


def apply_one(cur, row):
    table, field, key = FIELD_MAP[row["target_kind"]]
    if row["proposed_date"] is None:
        return False, "no proposed_date"
    keyval = row["target_ref"]
    if key == "id":
        keyval = int(keyval)
    cur.execute(f"UPDATE {table} SET {field}=%s, updated_at=now() WHERE {key}=%s",
                (row["proposed_date"], keyval))
    n = cur.rowcount
    cur.execute("UPDATE date_proposals SET status='approved', resolved_at=now() WHERE id=%s", (row["id"],))
    return n > 0, f"{table}.{field} set on {n} row(s)"


def cmd_approve(cur, pid, rule):
    if rule:
        cur.execute("SELECT * FROM date_proposals WHERE status='pending' AND basis_rule=%s "
                    "AND proposed_date IS NOT NULL", (rule,))
    else:
        cur.execute("SELECT * FROM date_proposals WHERE id=%s AND status='pending'", (pid,))
    rows = cur.fetchall()
    if not rows:
        print("Nothing matching to approve.")
        return
    for r in rows:
        ok, msg = apply_one(cur, r)
        print(f"  #{r['id']} {'✓' if ok else '✗'} {r['target_kind']}:{r['target_ref']} "
              f"→ {r['proposed_date']} ({msg})")
    print(f"\nApproved {len(rows)}. Re-run --scan to cascade to dependents (linked obligations/goals).")


def main():
    ap = argparse.ArgumentParser(description="date proposer — light the dark items")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--apply", action="store_true", help="with --scan: write proposal rows")
    ap.add_argument("--review", action="store_true")
    ap.add_argument("--approve", nargs="?", const="__RULE__", help="proposal id, or with --rule a batch")
    ap.add_argument("--rule", help="batch-approve a basis_rule (e.g. DERIVE_FROM_SPINE)")
    ap.add_argument("--reject", type=int)
    args = ap.parse_args()

    conn = db()
    cur = conn.cursor()
    ensure_schema(cur)
    conn.commit()

    if args.scan:
        props = scan(cur, args.apply)
        conn.commit()
        print_scan(props, args.apply)
    elif args.review:
        cmd_review(cur)
    elif args.approve is not None:
        pid = None if args.approve == "__RULE__" else int(args.approve)
        cmd_approve(cur, pid, args.rule)
        conn.commit()
    elif args.reject:
        cur.execute("UPDATE date_proposals SET status='rejected', resolved_at=now() WHERE id=%s", (args.reject,))
        conn.commit()
        print(f"rejected #{args.reject}")
    else:
        ap.print_help()
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
