#!/usr/bin/env python3
"""timeline_coverage.py — the pulse-coverage auditor (calendar-is-the-pulse doctrine).

North star (operator, 2026-07-08): the calendar sets the pulse for all communications;
timelines and goals must be attached to EVERYTHING agentically. An undated goal is
invisible to the pulse (no briefs, no nudges, no cadence). This auditor measures that
gap mechanically so it can be driven to zero — deterministic, read-only, $0.

What it measures (the primitive date-bearers):
  matters.next_deadline · client_goals.target_date · firm_goals.target_date ·
  landtek_obligations.due_by · case_actions.due_date · action_items.due_date ·
  matter_plays(ready).urgency_days (derived from its matter)
(keystones + matter_objectives inherit their timeline via matter/goal — correct
 design; they are covered transitively, not counted as primitives.)

Classification (avoids nagging about legitimate darkness):
  NEEDS-A-DATE   active row, no timeline — the agentic work queue
  LEGIT-DARK     observation-only / out-of-scope / pending-triage — correctly dateless

Usage:
  python3 scripts/timeline_coverage.py            # human report
  python3 scripts/timeline_coverage.py --summary  # one-line pulse score (digest-able)
Always exits 0 — a report, not a gate.
"""
import argparse
import sys

import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# matters whose datelessness is legitimate (not a pulse gap)
LEGIT_DARK_STATUS = ("out_of_scope", "pending_context", "pending_triage",
                     "closed", "archived")
LEGIT_DARK_STAGE_PAT = ("observation_only", "no_immediate_deadline",
                        "declared_unrelated", "needs_context_from_user")


def q(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true", help="one-line pulse score")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    cur = conn.cursor()

    classes = []  # (name, total, dated, needs_date_rows [(code, why-dark)])

    # 1. matters — NULL next_deadline on an active matter = NEEDS-A-DATE (deadlines.py doctrine)
    rows = q(cur, """
        SELECT matter_code, COALESCE(current_stage,''), COALESCE(status,''),
               (next_deadline IS NOT NULL) AS dated
        FROM matters
        WHERE COALESCE(status,'') NOT IN ('closed','archived')""")
    total = len(rows); dated = sum(1 for r in rows if r[3])
    needs = []
    for code, stage, status, d in rows:
        if d:
            continue
        legit = (status in LEGIT_DARK_STATUS
                 or any(p in stage for p in LEGIT_DARK_STAGE_PAT))
        if not legit:
            needs.append((code, stage or status or "?"))
    classes.append(("matters.next_deadline", total, dated, needs))

    # 2. client_goals
    rows = q(cur, """
        SELECT COALESCE(case_file,'?')||' #'||id, COALESCE(goal_text,''),
               (target_date IS NOT NULL)
        FROM client_goals
        WHERE COALESCE(status,'open') NOT IN ('done','achieved','closed')""")
    classes.append(("client_goals.target_date", len(rows),
                    sum(1 for r in rows if r[2]),
                    [(r[0], r[1][:48]) for r in rows if not r[2]]))

    # 3. firm_goals
    rows = q(cur, """
        SELECT 'firm#'||id, COALESCE(goal_text,''), (target_date IS NOT NULL)
        FROM firm_goals
        WHERE COALESCE(status,'open') NOT IN ('done','achieved','closed')""")
    classes.append(("firm_goals.target_date", len(rows),
                    sum(1 for r in rows if r[2]),
                    [(r[0], r[1][:48]) for r in rows if not r[2]]))

    # 4. landtek_obligations
    rows = q(cur, """
        SELECT COALESCE(matter_code, client_code, 'obl#'||id),
               COALESCE(short_label,''), (due_by IS NOT NULL)
        FROM landtek_obligations
        WHERE COALESCE(status,'open') NOT IN ('done','fulfilled','closed')""")
    classes.append(("landtek_obligations.due_by", len(rows),
                    sum(1 for r in rows if r[2]),
                    [(r[0], r[1][:48]) for r in rows if not r[2]]))

    # 5. case_actions (open)
    rows = q(cur, """
        SELECT COALESCE(matter_code,'?')||' #'||id, COALESCE(description,''),
               (due_date IS NOT NULL)
        FROM case_actions WHERE status <> 'confirmed'""")
    classes.append(("case_actions.due_date", len(rows),
                    sum(1 for r in rows if r[2]),
                    [(r[0], r[1][:48]) for r in rows if not r[2]]))

    # 6. action_items (open)
    rows = q(cur, """
        SELECT 'ai#'||id, COALESCE(description, ''), (due_date IS NOT NULL)
        FROM action_items
        WHERE COALESCE(status,'open') NOT IN ('done','completed','closed')""")
    classes.append(("action_items.due_date", len(rows),
                    sum(1 for r in rows if r[2]),
                    [(r[0], r[1][:48]) for r in rows if not r[2]]))

    # 7. ready plays anchored to a dated matter (derived timeline)
    rows = q(cur, """
        SELECT p.matter_code||':'||p.play_code, COALESCE(p.title,''),
               (m.next_deadline IS NOT NULL)
        FROM matter_plays p LEFT JOIN matters m ON m.matter_code = p.matter_code
        WHERE p.readiness = 'ready'""")
    classes.append(("matter_plays(ready)→matter date", len(rows),
                    sum(1 for r in rows if r[2]),
                    [(r[0], r[1][:48]) for r in rows if not r[2]]))

    grand_total = sum(c[1] for c in classes)
    grand_dated = sum(c[2] for c in classes)
    grand_needs = sum(len(c[3]) for c in classes)
    legit_dark = grand_total - grand_dated - grand_needs
    pct = (100 * grand_dated // grand_total) if grand_total else 100

    if args.summary:
        print(f"pulse-coverage {pct}% ({grand_dated}/{grand_total} dated; "
              f"{grand_needs} NEEDS-A-DATE; {legit_dark} legit-dark)")
        return

    print("=== TIMELINE / PULSE COVERAGE — calendar-is-the-pulse doctrine ===\n")
    for name, total, dated, needs in classes:
        p = (100 * dated // total) if total else 100
        print(f"{name:36} {dated:>4}/{total:<4} dated ({p}%)"
              + (f"  — {len(needs)} NEEDS-A-DATE" if needs else ""))
    print(f"\nPULSE COVERAGE: {pct}%  ({grand_dated}/{grand_total} dated · "
          f"{grand_needs} needs-a-date · {legit_dark} legitimately dark)")

    print("\n--- NEEDS-A-DATE (the agentic work queue) ---")
    for name, _, _, needs in classes:
        for code, why in needs:
            print(f"  {name.split('.')[0]:22} {code:26} {why}")
    if grand_needs == 0:
        print("  (none — every active goal-bearing object is on the pulse)")
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
