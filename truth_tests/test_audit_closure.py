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
    # deploy_255 additions — Donata King cascade
    (406, "MWK-CV26360", "Gloria HANSOL Balane Toronto Consulate acknowledgement"),
    (411, "MWK-CV26360", "Gloria H. Balane RPA Form — TCT 079-202100212 (contested defendant title)"),
    (568, "MWK-TCT4497", "1913 SC Decision G.R. 8678 Marciana Moreno De Worrick chain primary"),
    (586, "MWK-CV26360", "Civil Case 8563 RTC Daet Br.41 — Juntilla/Torralba v. Donata King/Mabeza"),
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


def donata_king_consolidated(cur):
    """deploy_255: #8365 Donata M. King → canonical = #3155 Donata Mabeza King."""
    cur.execute("SELECT canonical_id FROM entities WHERE id = 8365")
    r = cur.fetchone()
    if not r:
        raise TruthFailure("#8365 Donata M. King missing")
    if r["canonical_id"] != 3155:
        raise TruthFailure(
            f"#8365 canonical_id={r['canonical_id']}, expected 3155 (Donata Mabeza King). "
            "Deploy_255 was supposed to consolidate."
        )


def donata_and_joel_in_registry(cur):
    """deploy_255: Donata King + Joel Mabeza added to MWK keystones."""
    sys.path.insert(0, "/root/landtek")
    from case_theories._clients import get
    mwk = get("MWK")
    ks = mwk.get("keystone_entities", {})
    if ks.get("donata_mabeza_king") != 3155:
        raise TruthFailure(
            f"keystone 'donata_mabeza_king' = {ks.get('donata_mabeza_king')}, expected 3155"
        )
    if ks.get("joel_i_mabeza") != 8367:
        raise TruthFailure(
            f"keystone 'joel_i_mabeza' = {ks.get('joel_i_mabeza')}, expected 8367"
        )


TESTS = (
    [(f"audit_closure.doc{did}.{exp}", make_doc_assertion(did, exp, why))
     for did, exp, why in PINNED_ASSIGNMENTS]
    + [
        ("audit_closure.transferee_keystones_resolved", transferee_keystones_resolved),
        ("audit_closure.donata_king_consolidated", donata_king_consolidated),
        ("audit_closure.donata_and_joel_in_registry", donata_and_joel_in_registry),
    ]
)


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
