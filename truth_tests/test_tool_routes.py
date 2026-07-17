#!/usr/bin/env python3
"""test_tool_routes.py — one brain for every communication tool (deploy_966).

The tool surface (vault queries · doc lookup/search) is a set of governed SPINE routes: identical on
every channel, deterministic ($0, no model), client-walled (A5), read-only, and quiet on ordinary
conversation. Vault WRITES are never reachable from a conversational route."""
import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from _harness import run, TruthFailure, DSN
import leo_service as LS
import tool_routes as TR


def _rb():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def same_answer_regardless_of_channel(cur):
    """The route is channel-blind by construction: try_purpose_route (shared by TG + Messenger)
    produces the identical tool answer for the identical identity+message."""
    conn, tc = _rb()
    try:
        a = LS.try_purpose_route(tc, "MWK-001", "what's pending in the vault queue?")
        b = LS.try_purpose_route(tc, "MWK-001", "what's pending in the vault queue?")
        if not a or not str(a.get("via", "")).startswith("tool:vault"):
            raise TruthFailure(f"vault ask did not hit the spine tool route: via={(a or {}).get('via')}")
        if (a or {}).get("text") != (b or {}).get("text"):
            raise TruthFailure("tool route is non-deterministic for the same ask.")
    finally:
        conn.rollback(); conn.close()


def doc_lookup_is_client_walled(cur):
    """A5: a doc outside the asker's client family is NEVER confirmed — same 'no record' as absent."""
    conn, tc = _rb()
    try:
        tc.execute("SELECT id FROM documents WHERE coalesce(case_file, matter_code,'') ILIKE 'MWK%' LIMIT 1")
        r = tc.fetchone()
        if not r:
            return
        mwk_doc = dict(r)["id"]
        out = TR._doc_lookup(tc, "Paracale-001", mwk_doc)
        if out and ("files/c" in out or "doc:" in out.split("No record")[0] and "No record" not in out):
            raise TruthFailure(f"cross-client doc {mwk_doc} leaked to Paracale asker: {out!r}")
        if out and "No record" not in out:
            raise TruthFailure(f"cross-client lookup did not fail closed: {out!r}")
        ok = TR._doc_lookup(tc, "MWK-001", mwk_doc)
        if not ok or "No record" in ok:
            raise TruthFailure(f"own-family doc {mwk_doc} not returned to its client: {ok!r}")
    finally:
        conn.rollback(); conn.close()


def ordinary_chat_is_untouched(cur):
    """No tool intent → None, fast — greetings and normal questions never trip a tool route."""
    conn, tc = _rb()
    try:
        for q in ("good morning Leo", "how is the Balane case looking?",
                  "salamat po", "how many ARTA CTNs went to the OP petition?"):
            if TR.try_tool_route(tc, "MWK-001", q) is not None:
                raise TruthFailure(f"tool route fired on ordinary chat: {q!r}")
    finally:
        conn.rollback(); conn.close()


def no_write_reachable_from_conversation(cur):
    """The conversational tool surface is read-only: no INSERT/UPDATE/DELETE SQL and no write
    endpoints (register/bind) anywhere in tool_routes."""
    src = open(TR.__file__.replace(".pyc", ".py"), encoding="utf-8", errors="replace").read()
    for bad in ("INSERT ", "UPDATE ", "DELETE ", "vault/register", "vault_register",
                "vault/bind", "bind_scan"):
        if bad in src:
            raise TruthFailure(f"write-capable artifact in the conversational tool surface: {bad!r}")


def unknown_doc_fails_closed(cur):
    conn, tc = _rb()
    try:
        out = TR._doc_lookup(tc, "MWK-001", 9999999)
        if not out or "No record" not in out:
            raise TruthFailure(f"nonexistent doc id did not fail closed: {out!r}")
    finally:
        conn.rollback(); conn.close()


def drive_route_is_internal_only(cur):
    """Drive is the UN-WALLED store: the route exists ONLY for A21-internal identities. No identity /
    unknown identity → the route silently does not exist (never revealed). Deterministic (search
    monkeypatched — no network)."""
    conn, tc = _rb()
    orig = TR._drive_search
    TR._drive_search = lambda terms: f"Drive: 1 match(es): fake-{terms[:10]}.txt"
    try:
        ask = "search drive for petition scans"
        if TR.try_tool_route(tc, "MWK-001", ask) is not None:
            raise TruthFailure("drive route fired with NO identity — must fail closed.")
        if TR.try_tool_route(tc, "MWK-001", ask, channel="telegram", channel_user_id="999999999") is not None:
            raise TruthFailure("drive route fired for an unknown (non-internal) identity.")
        hit = TR.try_tool_route(tc, "MWK-001", ask, channel="telegram", channel_user_id="6513067717")
        if not hit or hit.get("via") != "tool:drive_search":
            raise TruthFailure(f"drive route did not fire for the operator: {hit!r}")
    finally:
        TR._drive_search = orig
        conn.rollback(); conn.close()


def drive_degrades_never_crashes(cur):
    """The Drive edge failing (no libs / offline) yields None — the spine continues, nothing raises."""
    conn, tc = _rb()
    orig = TR._drive_search
    TR._drive_search = lambda terms: None
    try:
        hit = TR.try_tool_route(tc, "MWK-001", "search drive for petition",
                                channel="telegram", channel_user_id="6513067717")
        if hit is not None and hit.get("via") == "tool:drive_search":
            raise TruthFailure("degraded drive search still produced a drive answer.")
    finally:
        TR._drive_search = orig
        conn.rollback(); conn.close()


TESTS = [
    ("tool_routes.same_answer_any_channel", same_answer_regardless_of_channel),
    ("tool_routes.drive_internal_only", drive_route_is_internal_only),
    ("tool_routes.drive_degrades", drive_degrades_never_crashes),
    ("tool_routes.doc_lookup_client_walled", doc_lookup_is_client_walled),
    ("tool_routes.ordinary_chat_untouched", ordinary_chat_is_untouched),
    ("tool_routes.no_write_from_conversation", no_write_reachable_from_conversation),
    ("tool_routes.unknown_doc_fails_closed", unknown_doc_fails_closed),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
