#!/usr/bin/env python3
"""test_deadline_totality.py — corpus-wide assertion for A57 (deadline totality — Principle 2 as an axiom).

**What A57 requires.** "Never miss a deadline" (MASTER_PLAN §4 principle 2) was doctrine with no invariant —
the operator's worst recorded failure ("the stack is missing every important date", §6A) had no regression
detector. A57 makes the affirmative side mechanical: the deadline SURFACE (`surfaced_deadlines`, written daily
by `scripts/deadlines.py::digest`) must be (a) FRESH — the proactive layer is actually running, not silently
dead — and (b) COMPLETE — every active matter's structured `next_deadline` inside the 90-day window appears in
the latest surface. A dated obligation the surface dropped is exactly a "missed important date" in the making.

**Deliberately NOT asserted:** `needs_date = 0`. Per §6A, ~17 matters genuinely need a date — that is an honest
operator gap to be worked, not a pipeline defect; asserting 0 would punish honesty (the deploy_642/644 lesson:
never fabricate a date to silence a gap). The dateless classification (needs_date / watch / orphan, mirroring
`deadlines.py::classify_gap`) is REPORTED on every run so the gap stays visible, threshold-free.

Symmetric to `test_matter_law_is_embedded.py` (A53, the law side) and `test_connected_document_count.py`
(A41, the doc side): count-independent, deterministic, read-only, creditless. Grounded 2026-07-09:
surface fresh (as_of=today, 11 rows/day), 9 active matters dated <=90d, 0 dropped. Negative-tested to bite.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure

_ACTIVE = "(status IS NULL OR status NOT IN ('closed','archived'))"
# mirrors scripts/deadlines.py::WATCH_RE — stages that legitimately carry no deadline
_WATCH_RE = ("observation_only|advisory|tracking|no_immediate_deadline|"
             "asset_development|declared_unrelated|under_review")


def deadline_surface_fresh(cur):
    """A57(a): the proactive deadline surface was written within the last 2 days — the layer is ALIVE."""
    cur.execute("SELECT max(as_of) AS latest, count(*) AS n FROM surfaced_deadlines")
    r = cur.fetchone()
    if r is None or r["latest"] is None:
        raise TruthFailure(
            "surfaced_deadlines is EMPTY — the proactive deadline layer has never written (A57: the stack "
            "must tell Jonathan what is due unprompted). Run `python3 scripts/deadlines.py --write`.")
    cur.execute("SELECT (current_date - max(as_of)) AS age_days FROM surfaced_deadlines")
    age = cur.fetchone()["age_days"]
    if age > 2:
        raise TruthFailure(
            f"deadline surface is STALE — last written {age} days ago (max as_of). The daily digest/deadline "
            f"timer died silently; a deadline could pass unsurfaced. Check landtek-deadline-* timers + "
            f"`python3 scripts/deadlines.py --write`.")


def deadline_surface_complete(cur):
    """A57(b): every active matter's structured next_deadline (<=90d out) appears in the LATEST surface."""
    cur.execute(f"""
      SELECT m.matter_code, m.next_deadline
      FROM matters m
      WHERE {_ACTIVE}
        AND m.next_deadline IS NOT NULL AND m.next_deadline <= current_date + 90
        AND NOT EXISTS (SELECT 1 FROM surfaced_deadlines s
                        WHERE s.as_of = (SELECT max(as_of) FROM surfaced_deadlines)
                          AND s.matter_code = m.matter_code AND s.due_date = m.next_deadline)
      ORDER BY m.next_deadline LIMIT 25""")
    dropped = [f"{r['matter_code']}={r['next_deadline']}" for r in cur.fetchall()]
    if dropped:
        raise TruthFailure(
            f"{len(dropped)} dated active matter(s) MISSING from the latest deadline surface (A57: a dated "
            f"obligation the surface dropped is a missed-date in the making): {dropped}. The digest write and "
            f"matters.next_deadline diverged — re-run `scripts/deadlines.py --write` and diff.")


def deadline_gap_reported(cur):
    """Non-threshold visibility: dated vs dateless classification on every run (the honest A57 headline)."""
    cur.execute(f"""
      SELECT count(*) FILTER (WHERE next_deadline IS NOT NULL) AS dated,
             count(*) FILTER (WHERE next_deadline IS NULL AND matter_code LIKE 'AUTO-%%') AS orphan,
             count(*) FILTER (WHERE next_deadline IS NULL AND matter_code NOT LIKE 'AUTO-%%'
                              AND coalesce(current_stage, status, '') ~* '{_WATCH_RE}') AS watch,
             count(*) FILTER (WHERE next_deadline IS NULL AND matter_code NOT LIKE 'AUTO-%%'
                              AND NOT coalesce(current_stage, status, '') ~* '{_WATCH_RE}') AS needs_date
      FROM matters WHERE {_ACTIVE}""")
    r = cur.fetchone()
    if r is None:
        raise TruthFailure("deadline-gap classification query returned no rows — schema/read problem")
    print(f"      [deadlines] active matters: {r['dated']} dated · {r['needs_date']} NEED-A-DATE · "
          f"{r['watch']} watch-only · {r['orphan']} AUTO-orphan (A57 — gap reported, never fabricated)")


TESTS = [
    ("deadlines.surface_fresh", deadline_surface_fresh),
    ("deadlines.surface_complete", deadline_surface_complete),
    ("deadlines.gap_reported", deadline_gap_reported),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
