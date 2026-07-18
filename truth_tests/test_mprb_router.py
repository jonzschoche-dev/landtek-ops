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


def op_count_oracle_membership(cur):
    """ORACLE CORRECTED 2026-07-18 (mention ≠ membership, deploy_963): the petition instrument
    (docs 702/703) carries CTNs 0690 + 0792 ONLY — '0747' appears nowhere in its text; the old
    'want 3 incl. 0747' was an unsupported hardcoded belief. The answer must state membership (2)
    and may report 0747 ONLY with its tied-not-named label."""
    import corpus_answer as ca
    ans, p = ca.try_corpus_answer(cur, "MWK-001",
                                  "how many cases have been referred from ARTA to the OP?")
    if not ans or p != "arta_op_referrals":
        raise TruthFailure(f"expected arta_op_referrals pack, got {p}")
    head = ans.split(".")[0]                      # the membership CLAIM sentence
    if "2" not in head or "0690" not in head or "0792" not in head:
        raise TruthFailure(f"membership claim must be 2 CTNs (0690, 0792):\n{ans[:300]}")
    if "0747" in head:
        raise TruthFailure(f"0747 asserted as ON the petition (membership breach):\n{ans[:300]}")
    if "0747" in ans and "not named on the petition" not in ans:
        raise TruthFailure(f"0747 present without its tied-not-named label:\n{ans[:300]}")
    if "MWK-ARTA-1378" in ans:
        raise TruthFailure("soft 1378 must not be counted as OP send")
    if "Hello" in ans:
        raise TruthFailure("cold brief must not greet")
    # Short by construction — one dose authority (S14 / EMISSION_CAP = 280)
    if len(ans) > 280:
        raise TruthFailure(f"OP brief over emission cap: {len(ans)} chars (want ≤280 by construction)")


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
    if "active" not in text.lower():
        raise TruthFailure("status brief must state active/closed")
    # distilled: human-tolerable
    if len(text) > 600 or text.count("\n") > 6:
        raise TruthFailure(f"status brief too long: {len(text)} chars")
    ang = brief["angles_by_matter"]["MWK-ARTA-0747"]["parties"]
    if ang.get("status") not in ("data", "empty", "not_instrumented"):
        raise TruthFailure(f"parties status missing: {ang}")


def mprb_never_launder_provisional_in_structured(cur):
    import matter_brief as mb
    brief = mb.assemble(cur, client_code="MWK-001", matter_codes=["MWK-OP-PETITION"],
                        message="status MWK-OP-PETITION")
    text = mb.answer_structured(brief, "matter_status") or ""
    if "inferred_strong" in text and "unconfirmed" not in text.lower():
        raise TruthFailure("provisional must not appear untagged")
    if "PROVISIONAL" in text and "unconfirmed" not in text.lower():
        raise TruthFailure("provisional must be tagged if present")
    # distilled structured answer is short; full basis lives internal
    if len(text) > 600:
        raise TruthFailure("structured emission too long")
    if "MWK-OP-PETITION" not in text:
        raise TruthFailure("must name the matter")


TESTS = [
    ("mprb.try_purpose_route_exists", try_purpose_route_exists),
    ("mprb.op_count_oracle_membership", op_count_oracle_membership),
    ("mprb.purpose_route_preformed", purpose_route_returns_preformed),
    ("mprb.status_structured", mprb_status_structured),
    ("mprb.provenance_structured_basis", mprb_never_launder_provisional_in_structured),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
