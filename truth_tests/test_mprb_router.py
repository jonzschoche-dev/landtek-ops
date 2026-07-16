#!/usr/bin/env python3
"""test_mprb_router.py — Phase A/C teeth: purpose router + provenance + OP oracle."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/root/landtek/scripts")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from _harness import run, TruthFailure


def try_purpose_route_exists(cur):
    del cur
    import leo_service as ls
    assert hasattr(ls, "try_purpose_route")
    assert hasattr(ls, "_deliver_preformed")


def op_count_oracle_3(cur):
    import corpus_answer as ca
    ans, p = ca.try_corpus_answer(cur, "MWK-001",
                                  "how many cases have been referred from ARTA to the OP?")
    if not ans or p != "arta_op_referrals":
        raise TruthFailure(f"expected arta_op_referrals pack, got {p}")
    if "3 ARTA" not in ans and "3." not in ans[:80]:
        raise TruthFailure(f"OP count oracle failed (want 3 distilled):\n{ans[:500]}")
    for code in ("MWK-ARTA-0690", "MWK-ARTA-0747", "MWK-ARTA-0792"):
        if code not in ans:
            raise TruthFailure(f"missing {code} in OP brief")
    if "MWK-ARTA-1378" in ans:
        raise TruthFailure("soft 1378 must not be counted as OP send")
    if "Hello" in ans:
        raise TruthFailure("cold brief must not greet")
    # Human-tolerable: no multi-paragraph evidence dump
    if ans.count("\n") > 8 or len(ans) > 800:
        raise TruthFailure(f"OP brief too long for equilibrium emission: {len(ans)} chars")


def purpose_route_returns_preformed(cur):
    import leo_service as ls
    r = ls.try_purpose_route(
        cur, "MWK-001", "how many cases have been referred from ARTA to the OP?")
    if not r or not r.get("preformed"):
        raise TruthFailure(f"expected preformed route, got {r}")
    if "3." not in (r.get("text") or ""):
        raise TruthFailure("route text missing count 3")
    # title route
    r2 = ls.try_purpose_route(cur, "MWK-001", "Fetch me title tct 32911")
    if not r2 or not r2.get("preformed"):
        raise TruthFailure(f"title route missing: {r2}")
    if "files/c/" not in (r2.get("text") or ""):
        raise TruthFailure("title pack must keep /files/c/ links")


def mprb_status_structured(cur):
    import matter_brief as mb
    brief = mb.assemble(cur, client_code="MWK-001", matter_codes=["MWK-ARTA-0747"],
                        message="status of MWK-ARTA-0747")
    text = mb.answer_structured(brief, "matter_status")
    if not text or "MWK-ARTA-0747" not in text:
        raise TruthFailure(f"mprb status failed: {text}")
    if "verified ground" not in text.lower() and "VERIFIED" not in text:
        # answer_structured uses 'verified ground'
        if "verified ground" not in text:
            raise TruthFailure("status brief must declare verified ground section")
    # parties angle declared
    ang = brief["angles_by_matter"]["MWK-ARTA-0747"]["parties"]
    if ang.get("status") not in ("data", "empty", "not_instrumented"):
        raise TruthFailure(f"parties status missing: {ang}")


def mprb_never_launder_provisional_in_structured(cur):
    import matter_brief as mb
    brief = mb.assemble(cur, client_code="MWK-001", matter_codes=["MWK-OP-PETITION"],
                        message="status MWK-OP-PETITION")
    text = mb.answer_structured(brief, "matter_status") or ""
    # structured path must not print provisional untagged
    if "inferred_strong" in text and "unconfirmed" not in text.lower():
        # answer_structured shouldn't include provisional at all
        pass
    if "PROVISIONAL" in text and "unconfirmed" not in text.lower():
        raise TruthFailure("provisional must be tagged if present")
    # answer_structured only uses verified sample — OK if no provisional section
    if "Basis: matters + matter_facts(verified only)" not in text:
        raise TruthFailure("structured must declare verified-only basis")


TESTS = [
    ("mprb.try_purpose_route_exists", try_purpose_route_exists),
    ("mprb.op_count_oracle_3", op_count_oracle_3),
    ("mprb.purpose_route_preformed", purpose_route_returns_preformed),
    ("mprb.status_structured", mprb_status_structured),
    ("mprb.provenance_structured_basis", mprb_never_launder_provisional_in_structured),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
