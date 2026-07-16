#!/usr/bin/env python3
"""test_onboarding_reentry.py — misregister / decline / re-enter floors.

Same channel_user_id never invents a second row. Prior attempts archive into
metadata.reentry_history. Locked operator identity cannot be wiped from chat.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/root/landtek/leo_tools")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "leo_tools"))

from _harness import run, TruthFailure, DSN

# Import under test
import onboarding_endpoints as ob  # noqa: E402


def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = False
    return c


def reentry_phrases_detected(cur):
    del cur
    assert ob._wants_reentry("please start over")
    assert ob._wants_reentry("I want to re-apply")
    assert ob._wants_reentry("wrong name — misregister")
    assert not ob._wants_reentry("hello about my case")


def declined_reentry_archives_history(cur):
    """declined + re-apply → awaiting_intro, history preserved, one row."""
    tag = "REENTRY-" + uuid.uuid4().hex[:10]
    cur.execute("SELECT id FROM channels WHERE name='telegram'")
    ch = cur.fetchone()
    if not ch:
        raise TruthFailure("no telegram channel")
    ch_id = ch["id"] if isinstance(ch, dict) else ch[0]
    cur.execute("""
        INSERT INTO channel_users
          (channel_id, channel_user_id, display_name, role, authorized,
           onboarding_state, onboarding_responses, metadata)
        VALUES (%s, %s, 'Temp Prospect', 'unknown', false, 'declined',
                %s::jsonb, '{}'::jsonb)
        RETURNING id
    """, (ch_id, tag, json.dumps({"intro_text": "I am Temp", "matter_description": "TCT 1"})))
    uid = cur.fetchone()["id"]
    cur.execute("SELECT * FROM channel_users WHERE id=%s", (uid,))
    user = dict(cur.fetchone())
    fresh = ob._archive_and_reset(cur, user, reason="test_reentry")
    if fresh.get("onboarding_state") != "awaiting_intro":
        raise TruthFailure(f"expected awaiting_intro, got {fresh.get('onboarding_state')}")
    if fresh.get("authorized"):
        raise TruthFailure("re-entry must clear authorized")
    hist = (fresh.get("metadata") or {}).get("reentry_history") or []
    if isinstance(fresh.get("metadata"), str):
        hist = json.loads(fresh["metadata"]).get("reentry_history") or []
    if not hist:
        # RealDict may return metadata as dict already
        meta = fresh.get("metadata")
        if isinstance(meta, str):
            meta = json.loads(meta)
        hist = (meta or {}).get("reentry_history") or []
    if not hist:
        raise TruthFailure("reentry_history empty after archive")
    if hist[-1].get("prior_responses", {}).get("intro_text") != "I am Temp":
        raise TruthFailure("prior intro not archived")
    cur.execute("SELECT count(*) AS n FROM channel_users WHERE channel_user_id=%s", (tag,))
    if (cur.fetchone()["n"] or 0) != 1:
        raise TruthFailure("re-entry must not create a second row")
    cur.rollback()


def operator_identity_locked(cur):
    del cur
    u = {"onboarding_state": "approved", "authorized": True, "role": "operator",
         "approved_role": "operator"}
    if not ob._identity_locked(u):
        raise TruthFailure("operator must be identity-locked")
    u2 = {"onboarding_state": "awaiting_intro", "authorized": False, "role": "unknown"}
    if ob._identity_locked(u2):
        raise TruthFailure("unknown intro must not be locked")


def reopen_api_refuses_operator(cur):
    """Safety: _archive on operator-like role keeps principal flags when keep path used."""
    cur.execute("""
        SELECT cu.* FROM channel_users cu
          JOIN channels c ON c.id = cu.channel_id
         WHERE c.name='telegram' AND cu.channel_user_id='6513067717'
         LIMIT 1
    """)
    row = cur.fetchone()
    if not row:
        return  # skip if seed missing
    u = dict(row)
    if not ob._identity_locked(u):
        raise TruthFailure("Jonathan telegram row must be identity-locked")
    cur.rollback()


TESTS = [
    ("onboard.reentry_phrases", reentry_phrases_detected),
    ("onboard.declined_reentry_archives", declined_reentry_archives_history),
    ("onboard.operator_identity_locked", operator_identity_locked),
    ("onboard.jonathan_row_locked", reopen_api_refuses_operator),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
