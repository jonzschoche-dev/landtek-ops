#!/usr/bin/env python3
"""test_date_proposer_guards.py — lock the two bugs found + fixed while building
date_proposer.py (deploy_842), so they can't silently regress.

Doctrine: the proposer must NEVER fabricate a date. Two ways it nearly did, both fixed:
  1. PAST DATES — it inherited a matter's OVERDUE next_deadline, attaching a stale date.
     Guard: dated_matters() is future-only. Asserted here at the DATA level — no live
     proposal row may carry a past date.
  2. YEAR-AS-DOCKET — loose numeric-token matching linked a goal mentioning the year
     "1979" to a docket. Guard: strict_goal_match() requires a FULL code/docket substring.
     Asserted here at the LOGIC level — the shipped matcher rejects the year, keeps the
     real docket.

Deterministic + creditless. Negative-tested to bite (both assertions fail if the guards
are reverted).
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "/root/landtek/scripts")
from _harness import run, TruthFailure  # noqa: E402
import date_proposer  # noqa: E402


def no_year_as_docket_false_match(cur):
    """strict_goal_match must NOT link a goal's year to a docket, but MUST still link a
    real full-docket reference (bug 2 regression lock)."""
    fut = date.today() + timedelta(days=30)
    dm = {"MWK-ARTA-1891": (fut, "CTN SL-2026-0423-1891")}
    false_hit = date_proposer.strict_goal_match(
        "Locate and secure certified copy of the alleged 1979 deed", dm)
    if false_hit is not None:
        raise TruthFailure(
            f"year-as-docket regressed: a goal mentioning '1979' false-matched {false_hit}. "
            "strict_goal_match must require a FULL code/docket substring, not a numeric token.")
    real_hit = date_proposer.strict_goal_match(
        "Resolve ARTA complaint CTN SL-2026-0423-1891 at the Ombudsman", dm)
    if real_hit != "MWK-ARTA-1891":
        raise TruthFailure(
            f"full-docket goal no longer links (got {real_hit!r}) — matcher over-tightened; "
            "the real CTN SL-2026-0423-1891 reference must still resolve to MWK-ARTA-1891.")


def no_past_dated_proposal(cur):
    """No live proposal may carry a past date (bug 1 regression lock, data level)."""
    cur.execute("SELECT count(*) AS n FROM date_proposals "
                "WHERE proposed_date < CURRENT_DATE AND status IN ('pending','needs_operator')")
    n = cur.fetchone()["n"]
    if n:
        raise TruthFailure(
            f"{n} live date_proposal(s) carry a PAST date — the future-only guard "
            "(dated_matters WHERE next_deadline >= CURRENT_DATE) regressed. A proposal must "
            "never back-date; a dependent of a stale matter is OPERATOR_INPUT, not overdue.")


TESTS = [
    ("date_proposer.no_year_as_docket_false_match", no_year_as_docket_false_match),
    ("date_proposer.no_past_dated_proposal", no_past_dated_proposal),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
