#!/usr/bin/env python3
"""test_agenda_substrate.py — the calendar pulse/brief must READ the full deadline substrate.

Root cause of the "starved / lazy calendar" (2026-09): the agenda gather read only
matters/calendar_events/case_actions, so a deadline landing in any of the dozen other
date-bearing tables (case_deadlines, case_events, arta_cases, case_reports, resolutions,
drip_edition, surfaced_deadlines) was INVISIBLE to the pulse and the brief. deploy fix
added gather_from_deadline_substrate. These floors keep it wired + honest:

  1. WIRED (grep-floor): get_agenda + calendar_sync's push assembly both call
     gather_from_deadline_substrate — it cannot be silently unwired.
  2. COVERAGE (runtime): every FUTURE date present in the deadline substrate appears in
     get_agenda's output. If a populated deadline table goes unread again, this bites.

Runtime test uses its own PLAIN cursor (the gathers index rows positionally; the harness
RealDictCursor would break them).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
sys.path.insert(0, "/root/landtek/scripts")
from _harness import run, TruthFailure, DSN  # noqa: E402


def gather_is_wired(cur):
    """get_agenda (pulse+brief) AND calendar_sync (gcal push) must call the substrate gather."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ac = open(os.path.join(repo, "scripts", "assistant_cadence.py"), errors="ignore").read()
    cs = open(os.path.join(repo, "scripts", "calendar_sync.py"), errors="ignore").read()
    if "gather_from_deadline_substrate(cur, None, index)" not in ac:
        raise TruthFailure(
            "assistant_cadence.get_agenda no longer calls gather_from_deadline_substrate — the "
            "pulse/brief agenda has been UNWIRED from the deadline substrate (starved-calendar "
            "regression). Re-wire before it runs.")
    if "def gather_from_deadline_substrate" not in cs or "gather_from_deadline_substrate(cur, args.client, index)" not in cs:
        raise TruthFailure(
            "calendar_sync no longer defines/calls gather_from_deadline_substrate — the Google "
            "Calendar push has been unwired from the deadline substrate.")


def substrate_dates_reach_agenda(cur):
    """Every FUTURE date in the deadline substrate must appear in the agenda (no populated
    deadline table silently unread). Dates-only comparison → robust to cross-source dedup."""
    import psycopg2
    from calendar_sync import DEADLINE_SOURCES, table_exists
    import assistant_cadence as ac
    c = psycopg2.connect(DSN)          # plain tuple cursor (gathers index positionally)
    pc = c.cursor()
    try:
        sub_dates = set()
        for table, dcol, lbl, kcol, kkind, extra in DEADLINE_SOURCES:
            if not table_exists(pc, table):
                continue
            where = f"{dcol} >= CURRENT_DATE" + (f" AND {extra}" if extra else "")
            try:
                pc.execute(f"SELECT DISTINCT {dcol}::date FROM {table} WHERE {where}")
                sub_dates |= {r[0] for r in pc.fetchall() if r[0]}
            except Exception:
                c.rollback()
        agenda_dates = {ac.item_date(it) for it in ac.get_agenda(pc) if it.start is not None}
        missing = sorted(d for d in sub_dates if d not in agenda_dates)
        if missing:
            raise TruthFailure(
                f"{len(missing)} deadline-substrate future date(s) NOT reaching the agenda — the "
                f"pulse/brief is blind to a populated deadline table (starved-calendar regression): "
                f"{[str(d) for d in missing[:8]]}")
        print(f"      [agenda] {len(sub_dates)} substrate future-date(s) all reach the agenda "
              f"({len(agenda_dates)} agenda dates)")
    finally:
        c.close()


TESTS = [
    ("agenda.substrate_gather_is_wired", gather_is_wired),
    ("agenda.substrate_dates_reach_agenda", substrate_dates_reach_agenda),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
