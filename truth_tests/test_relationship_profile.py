#!/usr/bin/env python3
"""test_relationship_profile.py — the first living organ (Increment 2). Proves the per-relationship
profile GROWS from a verified exchange, does so idempotently, and FEEDS the generation prompt."""
import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from _harness import run, TruthFailure
import equilibrium_propagate as EP
import relationship_profile as RPRO


def _rb():
    conn = psycopg2.connect(EP.DSN); conn.autocommit = False
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def profile_grows_and_is_idempotent(cur):
    conn, tc = _rb()
    try:
        tc.execute("""SELECT cm.id, c.name AS channel, cm.channel_user_id, cm.text_content
                        FROM channel_messages cm JOIN channels c ON c.id=cm.channel_id
                       WHERE cm.direction='inbound' AND coalesce(cm.text_content,'')<>''
                       ORDER BY cm.id DESC LIMIT 1""")
        m = tc.fetchone()
        if not m:
            return
        p1 = RPRO.observe(tc, m["channel"], m["channel_user_id"], "MWK-001", None, m["id"],
                          m["text_content"], {})
        if (p1.get("_exchanges") or 0) < 1:
            raise TruthFailure("relationship profile did not grow after a verified exchange.")
        if not (p1.get("lang") or p1.get("themes") or p1.get("detail")):
            raise TruthFailure("profile captured no signals from the exchange.")
        tc.execute("SELECT exchanges FROM relationship_profile WHERE channel=%s AND channel_user_id=%s",
                   (m["channel"], str(m["channel_user_id"])))
        ex1 = tc.fetchone()["exchanges"]
        RPRO.observe(tc, m["channel"], m["channel_user_id"], "MWK-001", None, m["id"], m["text_content"], {})
        tc.execute("SELECT exchanges FROM relationship_profile WHERE channel=%s AND channel_user_id=%s",
                   (m["channel"], str(m["channel_user_id"])))
        ex2 = tc.fetchone()["exchanges"]
        if ex2 != ex1:
            raise TruthFailure(f"re-observing the same message double-counted ({ex1}->{ex2}) — not idempotent.")
    finally:
        conn.rollback(); conn.close()


def signals_extracted_correctly(cur):
    sig = RPRO.extract_signals("Salamat po, kamusta na yung TCT at deadline sa filing?", {})
    if sig["lang"] != "taglish":
        raise TruthFailure(f"Taglish not detected: {sig}")
    if "titles" not in sig["themes"] or "deadlines" not in sig["themes"]:
        raise TruthFailure(f"themes (titles/deadlines) not extracted: {sig}")


def profile_feeds_prompt(cur):
    block = RPRO.to_prompt({"dominant_lang": "taglish", "usual_detail": "terse",
                            "top_themes": ["titles", "deadlines"], "gratitude_hits": 3,
                            "urgency_hits": 0, "_exchanges": 5})
    if "taglish" not in block or "titles" not in block or "5 prior" not in block:
        raise TruthFailure(f"to_prompt did not surface the living profile: {block!r}")


TESTS = [
    ("relationship_profile.grows_and_is_idempotent", profile_grows_and_is_idempotent),
    ("relationship_profile.signals_extracted_correctly", signals_extracted_correctly),
    ("relationship_profile.feeds_prompt", profile_feeds_prompt),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
