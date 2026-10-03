#!/usr/bin/env python3
"""test_leo_core_answers.py — the first questions a client asks must be answered from the record,
correctly scoped. Locks the two defects /ops/console exposed on 2026-10-03:

  1. Title questions ("who holds / registered owner of / status of TCT …") fell through to the
     composer (client-wide status dump) or the inquiry stack, which read "the registered owner of
     title …" as an ENTITY NAME and attached another party's profile WITH citations — a confident
     false answer. Now: the client-scoped title_brief card.
  2. "When is the next hearing in <matter>?" returned the client-wide list, overdue-first, and never
     named the actual next date. Now: the named matter, upcoming dates first.

Data-relative (expected values are read from the DB, not hard-coded) so the tests stay valid as
dates pass. Every probe runs in a transaction that is rolled back.
"""
import os
import re
import sys
from datetime import date

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "leo_tools"))
from _harness import run, TruthFailure, DSN
import leo_service as LS

CLIENT = "MWK-001"
OTHER_CLIENT = "Paracale-001"


def _rb():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _ask(client, q):
    conn, tc = _rb()
    try:
        return LS.try_purpose_route(tc, client, q, dry_run=True) or {}
    finally:
        conn.rollback(); conn.close()


def _flagship_title(cur):
    """A clear, client-owned title card with a registrant (the test subject, read not hard-coded)."""
    cur.execute("""SELECT display_no, registrant_name,
                          COALESCE(NULLIF(lifecycle_status,''), status) AS st
                     FROM title_brief
                    WHERE client_code = %s AND clarity_status = 'clear'
                      AND COALESCE(registrant_name,'') <> '' AND display_no ~ '^[0-9]{3}-[0-9]{10}$'
                    ORDER BY n_source_docs DESC NULLS LAST LIMIT 1""", (CLIENT,))
    row = cur.fetchone()
    if not row:
        raise TruthFailure("no clear client-owned e-title card to test against")
    return row


def owner_question_uses_title_card(cur):
    t = _flagship_title(cur)
    for q in (f"Who holds TCT {t['display_no']}?",
              f"Who is the registered owner of title {t['display_no']}?"):
        r = _ask(CLIENT, q)
        if r.get("via") != "title_card":
            raise TruthFailure(f"{q!r} did not route to the title card: via={r.get('via')} "
                               f"text={(r.get('text') or '')[:120]!r}")
        if t["registrant_name"] not in (r.get("text") or ""):
            raise TruthFailure(f"{q!r} did not name the registered owner {t['registrant_name']!r}: "
                               f"{r.get('text')!r}")


def status_question_is_title_scoped(cur):
    t = _flagship_title(cur)
    r = _ask(CLIENT, f"What is the status of TCT {t['display_no']}?")
    if r.get("via") != "title_card":
        raise TruthFailure(f"title status ask answered client-wide: via={r.get('via')}")
    if t["st"] and t["st"] not in (r.get("text") or ""):
        raise TruthFailure(f"title status {t['st']!r} missing from reply: {r.get('text')!r}")


def title_card_is_client_scoped(cur):
    """A5: another client's title must never be described to this client."""
    t = _flagship_title(cur)
    r = _ask(OTHER_CLIENT, f"Who holds TCT {t['display_no']}?")
    if t["registrant_name"] in (r.get("text") or ""):
        raise TruthFailure(f"CROSS-CLIENT LEAK: {OTHER_CLIENT} was told the owner of {CLIENT}'s "
                           f"title {t['display_no']}: {r.get('text')!r}")


def next_hearing_names_the_matter_date(cur):
    cur.execute("""SELECT matter_code, title, next_deadline FROM matters
                    WHERE client_code = %s AND matter_code NOT LIKE 'AUTO-%%'
                      AND COALESCE(status,'') NOT IN ('closed','archived')
                      AND next_deadline >= CURRENT_DATE
                    ORDER BY next_deadline LIMIT 1""", (CLIENT,))
    m = cur.fetchone()
    if not m:
        return                                    # nothing upcoming to assert against — vacuous pass
    r = _ask(CLIENT, f"When is the next hearing in {m['matter_code']}?")
    if m["next_deadline"].isoformat() not in (r.get("text") or ""):
        raise TruthFailure(f"next-hearing ask for {m['matter_code']} did not give its date "
                           f"{m['next_deadline']}: via={r.get('via')} text={(r.get('text') or '')[:160]!r}")


def next_deadline_is_upcoming_first(cur):
    cur.execute("""SELECT 1 FROM matters WHERE client_code = %s AND next_deadline >= CURRENT_DATE
                     AND matter_code NOT LIKE 'AUTO-%%' LIMIT 1""", (CLIENT,))
    if not cur.fetchone():
        return
    r = _ask(CLIENT, "What is the next deadline?")
    dates = re.findall(r"\b(20\d\d-\d\d-\d\d)\b", r.get("text") or "")
    if not dates:
        raise TruthFailure(f"next-deadline reply carries no date: {r.get('text')!r}")
    if dates[0] < date.today().isoformat():
        raise TruthFailure(f"next-deadline reply leads with a PAST date {dates[0]}: {r.get('text')!r}")


TESTS = [
    ("leo_core.owner_uses_title_card", owner_question_uses_title_card),
    ("leo_core.title_status_scoped", status_question_is_title_scoped),
    ("leo_core.title_card_client_scoped", title_card_is_client_scoped),
    ("leo_core.next_hearing_named_matter", next_hearing_names_the_matter_date),
    ("leo_core.next_deadline_upcoming_first", next_deadline_is_upcoming_first),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
