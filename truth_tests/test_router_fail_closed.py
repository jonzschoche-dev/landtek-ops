#!/usr/bin/env python3
"""test_router_fail_closed.py — an ask about an identifier the corpus doesn't hold gets an honest
"no record", never the nearest-match answer (the 'docket 99999 → ARTA 0690' failure, 2026-07-18)."""
import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from _harness import run, TruthFailure, DSN
import leo_service as LS


def _rb():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def unknown_docket_fails_closed(cur):
    conn, tc = _rb()
    try:
        r = LS.try_purpose_route(tc, "MWK-001", "what deadlines exist for docket 99999?")
        if not r or r.get("via") != "unknown_identifier":
            raise TruthFailure(f"unknown docket did not fail closed: via={(r or {}).get('via')} "
                               f"text={((r or {}).get('text') or '')[:90]!r}")
        if "99999" not in r["text"] or "No record" not in r["text"]:
            raise TruthFailure(f"fail-closed text does not name the unknown identifier: {r['text']!r}")
    finally:
        conn.rollback(); conn.close()


def unknown_title_fails_closed(cur):
    conn, tc = _rb()
    try:
        r = LS.try_purpose_route(tc, "MWK-001", "show me the history of TCT T-99999")
        if not r or r.get("via") != "unknown_identifier":
            raise TruthFailure(f"unknown title did not fail closed: via={(r or {}).get('via')}")
    finally:
        conn.rollback(); conn.close()


def known_identifier_passes_through(cur):
    """A real docket/title must NOT be blocked by the gate (route proceeds to a real answerer)."""
    conn, tc = _rb()
    try:
        if LS._unknown_identifier_gate(tc, "what is the status of docket 0690?") is not None:
            raise TruthFailure("known docket 0690 was blocked by the unknown-identifier gate.")
        if LS._unknown_identifier_gate(tc, "history of TCT T-4497") is not None:
            raise TruthFailure("known title T-4497 was blocked by the unknown-identifier gate.")
    finally:
        conn.rollback(); conn.close()


def no_identifier_ask_is_untouched(cur):
    """Questions without an explicit identifier never trip the gate (incl. the membership oracle)."""
    conn, tc = _rb()
    try:
        for q in ("how many ARTA CTNs went to the OP petition?", "good morning Leo",
                  "what is the status of the Balane case?"):
            if LS._unknown_identifier_gate(tc, q) is not None:
                raise TruthFailure(f"identifier gate fired on a no-identifier ask: {q!r}")
    finally:
        conn.rollback(); conn.close()


def mixed_known_unknown_passes(cur):
    """v1 policy: if ANY asked identifier resolves, the route proceeds (specific answerers scope it)."""
    conn, tc = _rb()
    try:
        if LS._unknown_identifier_gate(tc, "compare docket 0690 and docket 99999") is not None:
            raise TruthFailure("mixed known+unknown ask was fully blocked — should pass through in v1.")
    finally:
        conn.rollback(); conn.close()


def year_is_not_an_identifier(cur):
    """'2026' near 'case' must not resolve-or-block via date fields — dates are excluded kinds."""
    conn, tc = _rb()
    try:
        r = LS._unknown_identifier_gate(tc, "any case updates from 2026?")
        # either no identifier extracted (preferred) or, if extracted, it must not fail-closed
        # purely because dates were excluded AND nothing else matched — accept None or a pass-through.
        if r is not None and "2026" in (r.get("text") or ""):
            # 2026 may legitimately match a docket/ctn field; only a false BLOCK is a failure
            raise TruthFailure(f"year 2026 tripped the fail-closed gate: {r['text']!r}")
    finally:
        conn.rollback(); conn.close()


TESTS = [
    ("router_fail_closed.unknown_docket", unknown_docket_fails_closed),
    ("router_fail_closed.unknown_title", unknown_title_fails_closed),
    ("router_fail_closed.known_passes", known_identifier_passes_through),
    ("router_fail_closed.no_identifier_untouched", no_identifier_ask_is_untouched),
    ("router_fail_closed.mixed_passes", mixed_known_unknown_passes),
    ("router_fail_closed.year_not_identifier", year_is_not_an_identifier),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
