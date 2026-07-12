#!/usr/bin/env python3
"""test_matter_disambig.py — the chat matter-disambiguation resolver (deploy_… design stub).

Proves resolve_chat_matter picks the SPECIFIC matter a message references (via keyword) rather than
defaulting to the client's biggest matter — the precision the post-soak increment will wire into the
graph anchor. Pure-function tests (no writes, no graph mutation)."""
import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "leo_tools"))
from _harness import run, TruthFailure
import equilibrium_propagate as EP
import comm_agent_max as CAM


def tokens_extract_docket(cur):
    t = CAM._matter_tokens("MWK-ARTA-1891")
    if "ARTA-1891" not in t or "1891" not in t:
        raise TruthFailure(f"_matter_tokens('MWK-ARTA-1891')={t} — must yield the docket tokens.")
    if "MWK" in t:
        raise TruthFailure("_matter_tokens leaked the client prefix MWK — would false-match every MWK chat.")


def keyword_beats_biggest(cur):
    """A message naming a specific matter resolves to THAT matter via keyword, not the fallback biggest."""
    conn = psycopg2.connect(EP.DSN); conn.autocommit = False
    tc = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # pick a real MWK matter that has a docket-like token, and confirm keyword resolution targets it
        tc.execute("""SELECT matter_code FROM matters WHERE client_code='MWK-001'
                       AND matter_code ~ '[0-9]{3,}' ORDER BY matter_code LIMIT 1""")
        row = tc.fetchone()
        if not row:
            return  # no docketed MWK matter — nothing to disambiguate
        target = row["matter_code"]
        tok = sorted(CAM._matter_tokens(target), key=len, reverse=True)[0]
        # inject a synthetic message referencing that token, resolve, expect the keyword hit
        tc.execute("""INSERT INTO channel_messages (channel_id, channel_user_id, direction, text_content, status)
                      VALUES (4, 'disambig-test', 'inbound', %s, 'received') RETURNING id""",
                   (f"Following up on {tok} please advise",))
        mid = tc.fetchone()["id"]
        mc, method = CAM.resolve_chat_matter(tc, mid, "MWK-001")
        if method != "keyword" or mc != target:
            raise TruthFailure(f"resolve_chat_matter for a message naming {tok} returned ({mc},{method}) "
                               f"— expected ({target},keyword). Disambiguation not selecting the named matter.")
    finally:
        conn.rollback(); conn.close()


def fallback_when_generic(cur):
    """A generic message with no matter reference falls back to the biggest matter (never errors)."""
    conn = psycopg2.connect(EP.DSN); conn.autocommit = False
    tc = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        tc.execute("""INSERT INTO channel_messages (channel_id, channel_user_id, direction, text_content, status)
                      VALUES (4, 'disambig-test2', 'inbound', 'good morning, any updates?', 'received') RETURNING id""")
        mid = tc.fetchone()["id"]
        mc, method = CAM.resolve_chat_matter(tc, mid, "MWK-001")
        if method != "fallback_biggest" or not mc:
            raise TruthFailure(f"generic message resolved ({mc},{method}) — expected a fallback_biggest matter.")
    finally:
        conn.rollback(); conn.close()


TESTS = [
    ("matter_disambig.tokens_extract_docket", tokens_extract_docket),
    ("matter_disambig.keyword_beats_biggest", keyword_beats_biggest),
    ("matter_disambig.fallback_when_generic", fallback_when_generic),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
