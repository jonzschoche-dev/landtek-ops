#!/usr/bin/env python3
"""test_petition_membership.py — mention ≠ membership (the 1210/0747 CTN overcount fix, 2026-07-18).

A CTN "on the OP petition" is a MEMBERSHIP claim and must come from the petition instrument's own
extracted fields (document_fields on the petition docs) — never from matter-aggregate mentions
(fact_fields across every doc linked to the matter). Grounded: the instrument carries 0690 + 0792;
'0747' appears nowhere in the petition text; 1210 is mention-only (CART minutes / dialogue docs).
"""
import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from _harness import run, TruthFailure, DSN
import corpus_answer as CA
import leo_service as LS


def _rb():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def membership_comes_from_instrument(cur):
    """_petition_member_ctns returns exactly the instrument-extracted set — and it is verifiable:
    every member CTN's short code must appear in the petition doc's own extracted_text."""
    conn, tc = _rb()
    try:
        member = CA._petition_member_ctns(tc)
        if not member:
            raise TruthFailure("no petition-member CTNs found — instrument extraction is dark "
                               "(document_fields on the petition docs lost their ctn rows?).")
        tc.execute("""SELECT string_agg(extracted_text,' ') AS t FROM documents d
                       WHERE (coalesce(d.document_title,'')||' '||coalesce(d.original_filename,''))
                             ~* 'petition'
                         AND (coalesce(d.document_title,'')||' '||coalesce(d.original_filename,''))
                             ~* '\\yop\\y|office of the president'""")
        txt = (tc.fetchone() or {}).get("t") or ""
        for c in member:
            if c not in txt:
                raise TruthFailure(f"member CTN {c} does not appear in the petition instrument text "
                                   "— membership must be instrument-grounded.")
    finally:
        conn.rollback(); conn.close()


def mention_only_ctns_are_not_members(cur):
    """1210 is mentioned in matter-linked docs but is NOT on the petition face — it must never be
    a member. Same for any CTN absent from the instrument text (0747 as of 2026-07-18)."""
    conn, tc = _rb()
    try:
        member = set(CA._petition_member_ctns(tc))
        if "1210" in member:
            raise TruthFailure("1210 graded as petition MEMBER — mention/membership conflation is back.")
        tc.execute("SELECT (string_agg(extracted_text,' ') ILIKE '%0747%') AS has FROM documents d "
                   "WHERE (coalesce(d.document_title,'')||' '||coalesce(d.original_filename,'')) "
                   "~* 'petition' AND (coalesce(d.document_title,'')||' '||coalesce(d.original_filename,'')) "
                   "~* '\\yop\\y|office of the president'")
        has_0747 = bool((tc.fetchone() or {}).get("has"))
        if not has_0747 and "0747" in member:
            raise TruthFailure("0747 graded as member but is absent from the instrument text — "
                               "the old hardcoded belief resurfaced.")
    finally:
        conn.rollback(); conn.close()


def op_answer_states_membership_honestly(cur):
    """The routed OP/CTN answer lists members as 'on the petition' and never counts a non-member in
    that claim; ≤280; no LLM involved (routed, preformed)."""
    conn, tc = _rb()
    try:
        member = set(CA._petition_member_ctns(tc))
        route = LS.try_purpose_route(tc, "MWK-001", "how many ARTA CTNs went to the OP petition?")
        if not route or not route.get("text"):
            raise TruthFailure("membership question did not route to a preformed answer.")
        text = route["text"]
        if len(text) > 300:
            raise TruthFailure(f"membership answer over dose ({len(text)} chars).")
        head = text.split(".")[0]   # the membership CLAIM = the first sentence ("N CTNs on the petition: …")
        for bad in ({"1210", "0747"} - member):
            if bad in head:
                raise TruthFailure(f"non-member CTN {bad} asserted in the membership claim: {text!r}")
        if "tied by verified record" not in text and "0747" in text:
            raise TruthFailure(f"0747 present without its not-on-the-petition label: {text!r}")
        if member and not any(c in text for c in member):
            raise TruthFailure(f"no instrument member CTN present in the answer: {text!r}")
    finally:
        conn.rollback(); conn.close()


TESTS = [
    ("petition_membership.from_instrument", membership_comes_from_instrument),
    ("petition_membership.mentions_not_members", mention_only_ctns_are_not_members),
    ("petition_membership.answer_states_membership", op_answer_states_membership_honestly),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
