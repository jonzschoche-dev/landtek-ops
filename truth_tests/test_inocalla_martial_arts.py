#!/usr/bin/env python3
"""test_inocalla_martial_arts.py — Arnis/martial-arts docs belong to Paracale.

Filed deploy_258 after Jonathan's correction that all arnis / martial arts
files relate to Allan Inocalla / Paracale client. Pins the routing.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, TruthFailure


PINNED = [
    (481, "PAR-MARTIAL-ARTS",  "Philippines-USA Cultural Exchange (Datu Shishir)"),
    (486, "PAR-MARTIAL-ARTS",  "Sport Arnis Canada Handbook"),
    (487, "PAR-MARTIAL-ARTS",  "Master Shishir Sport Arnis Canada"),
    (488, "PAR-MARTIAL-ARTS",  "Arnis Chi Golf (Master Shishir Inocalla)"),
    (489, "PAR-MARTIAL-ARTS",  "Sport Arnis Canada purpose statement"),
    (491, "PAR-MARTIAL-ARTS",  "Sport Arnis Camarines Norte Barangay Tanod"),
    (492, "PAR-MARTIAL-ARTS",  "Camarines Norte Sports Arnis Tourism (GM Shishir)"),
    (493, "PAR-MARTIAL-ARTS",  "Brgy Tanod Arnis Defensive Training (GM Shishir + GM Jesus)"),
    (536, "PAR-MARTIAL-ARTS",  "Kalisteniks syllabus"),
    (514, "PAR-CV13-131220",   "Inocalla family civil case 13-131220"),
]


def make_check(doc_id, expected_mc, label):
    def fn(cur):
        cur.execute("SELECT case_file, matter_code FROM documents WHERE id = %s", (doc_id,))
        r = cur.fetchone()
        if not r:
            raise TruthFailure(f"doc#{doc_id} ({label}) missing")
        if r["case_file"] != "Paracale-001":
            raise TruthFailure(
                f"doc#{doc_id} ({label}) case_file={r['case_file']!r}, expected 'Paracale-001'"
            )
        if r["matter_code"] != expected_mc:
            raise TruthFailure(
                f"doc#{doc_id} ({label}) matter_code={r['matter_code']!r}, "
                f"expected {expected_mc!r}. See memory/feedback_inocalla_martial_arts_linkage.md"
            )
    return fn


def par_martial_arts_matter_exists(cur):
    cur.execute("SELECT matter_code FROM matters WHERE matter_code = 'PAR-MARTIAL-ARTS'")
    if not cur.fetchone():
        raise TruthFailure(
            "matter 'PAR-MARTIAL-ARTS' missing — deploy_258 was supposed to create it"
        )


def allan_inocalla_in_par_keystones(cur):
    sys.path.insert(0, "/root/landtek")
    from case_theories._clients import get
    par = get("PAR")
    if par["keystone_entities"].get("allan_inocalla") != 7983:
        raise TruthFailure(
            f"PAR keystone allan_inocalla={par['keystone_entities'].get('allan_inocalla')}, "
            "expected 7983"
        )


def inocalla_aliases_consolidated(cur):
    """The 6 Inocalla alias entities point to their canonical roots."""
    expected = {
        8091: 7983, 8147: 7983, 8320: 7983,  # → Allan V. Inocalla
        8062: 8708, 8776: 8708,              # → Shishir Allan Inocalla
        8158: 8120,                          # → Jesus V. Inocalla
    }
    cur.execute("SELECT id, canonical_id FROM entities WHERE id = ANY(%s)",
                (list(expected.keys()),))
    bad = []
    for r in cur.fetchall():
        if r["canonical_id"] != expected[r["id"]]:
            bad.append(f"#{r['id']} → canonical_id={r['canonical_id']} (expected {expected[r['id']]})")
    if bad:
        raise TruthFailure(f"Inocalla aliases not consolidated: {bad}")


TESTS = (
    [(f"inocalla.{label}", make_check(did, mc, label)) for did, mc, label in PINNED]
    + [
        ("inocalla.matter_par_martial_arts_exists", par_martial_arts_matter_exists),
        ("inocalla.allan_in_par_keystones", allan_inocalla_in_par_keystones),
        ("inocalla.aliases_consolidated", inocalla_aliases_consolidated),
    ]
)


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
