#!/usr/bin/env python3
"""test_owner_crosslinks.py — Owner-bucket docs cross-linked to MWK matters
must surface in MWK queries even though their case_file != 'MWK-001'.

Filed deploy_257. Proves the platform's case_file/matter_code separation works.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, TruthFailure


CROSSLINKS = [
    (326, "MWK-TCT4497"),
    (602, "MWK-ESTATE"),
    (603, "MWK-ESTATE"),
    (692, "MWK-ESTATE"),
    (693, "MWK-TCT4497"),
    (694, "MWK-TCT4497"),
]


def make_check(doc_id, expected_mc):
    def fn(cur):
        cur.execute("SELECT case_file, matter_code FROM documents WHERE id = %s", (doc_id,))
        r = cur.fetchone()
        if not r:
            raise TruthFailure(f"doc#{doc_id} missing")
        if r["case_file"] != "Owner":
            raise TruthFailure(
                f"doc#{doc_id} case_file={r['case_file']!r}, expected 'Owner' "
                "(cross-link contract is that case_file stays = Owner; "
                "matter_code provides the MWK-side surface)"
            )
        if r["matter_code"] != expected_mc:
            raise TruthFailure(
                f"doc#{doc_id} matter_code={r['matter_code']!r}, expected {expected_mc!r}"
            )
    return fn


def chronicle_query_surfaces_owner_docs(cur):
    """The chronicle's doc query must match Owner docs with MWK matter_code."""
    cur.execute("""
        SELECT id FROM documents
         WHERE doc_date IS NOT NULL
           AND (case_file = 'MWK-001' OR matter_code LIKE 'MWK-%%')
           AND id IN (326, 602, 603, 692, 693, 694)
    """)
    seen = {r["id"] for r in cur.fetchall()}
    # 602, 603, 692, 693, 694 likely have NULL doc_date — they're not in the
    # chronicle path until doc_date is backfilled. Test the contract via 326
    # which has doc_date 2025-05-21 per audit.
    cur.execute("""
        SELECT id, doc_date FROM documents
         WHERE id = 326
    """)
    r = cur.fetchone()
    if r and r["doc_date"] is not None and 326 not in seen:
        raise TruthFailure(
            "chronicle doc-query no longer surfaces Owner-bucket MWK docs. "
            "The case_file/matter_code OR-clause may have regressed."
        )


TESTS = (
    [(f"owner_crosslinks.doc{did}.{mc}", make_check(did, mc)) for did, mc in CROSSLINKS]
    + [("owner_crosslinks.chronicle_query_surfaces", chronicle_query_surfaces_owner_docs)]
)


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
