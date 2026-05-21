#!/usr/bin/env python3
"""test_audit_closure.py — pins the deploy_254 manual audit closures.

Filed 2026-05-21 after the user's "Torralba are linked to Balane" correction
exposed a class of LLM 'flag_unrelated' false positives. The platform-level
fix (entity-graph guard + text-level fallback in 252/253) caught the misses;
deploy_254 manually assigned the right matter_codes. This test prevents
silent regression.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, TruthFailure


# (doc_id, expected_matter_code, why_it_matters)
PINNED_ASSIGNMENTS = [
    (474, "MWK-ESTATE",  "Patricia Keesey Zschoche's passport"),
    (412, "MWK-CV26360", "TCT T-50192 → Rosalina Hansol transferee"),
    (677, "MWK-CV26360", "Cesar de la Fuente 2016 petition"),
    (580, "MWK-CV26360", "Torralba CA-G.R. SP No. 181607"),
    (584, "MWK-CV26360", "Juntilla/Torralba/Cantor Civil Case 8563"),
    (527, "MWK-CV26360", "Mercedes Lot 403 CAD 1186-D"),
]


def make_doc_assertion(doc_id, expected, why):
    def fn(cur):
        cur.execute("SELECT matter_code FROM documents WHERE id = %s", (doc_id,))
        r = cur.fetchone()
        if not r:
            raise TruthFailure(f"doc#{doc_id} ({why}) missing from documents")
        if r["matter_code"] != expected:
            raise TruthFailure(
                f"doc#{doc_id} ({why}): expected matter_code={expected!r}, "
                f"got {r['matter_code']!r}. See memory/feedback_torralba_balane_linkage.md "
                f"+ holes/finding_resolutions_misclassified.md for context."
            )
    return fn


def transferee_keystones_resolved(cur):
    """The 6 formerly-TBD transferee IDs should now be set in the registry.
    Test enforces the registry-vs-DB alignment."""
    sys.path.insert(0, "/root/landtek")
    from case_theories._clients import get
    mwk = get("MWK")
    formerly_tbd = [
        "alberto_victa", "ananias_apor", "rosalina_hansol",
        "roscoe_leano", "ruben_ocan", "severino_tenorio_jr",
    ]
    unresolved = []
    for k in formerly_tbd:
        eid = mwk["keystone_entities"].get(k)
        if eid is None:
            unresolved.append(k)
            continue
        cur.execute("SELECT canonical_name FROM entities WHERE id = %s", (eid,))
        r = cur.fetchone()
        if not r:
            raise TruthFailure(f"keystone {k!r}=#{eid} does not resolve in entities")
    if unresolved:
        raise TruthFailure(
            f"keystones still unresolved (None in registry): {unresolved}"
        )


TESTS = (
    [(f"audit_closure.doc{did}.{exp}", make_doc_assertion(did, exp, why))
     for did, exp, why in PINNED_ASSIGNMENTS]
    + [("audit_closure.transferee_keystones_resolved", transferee_keystones_resolved)]
)


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
