#!/usr/bin/env python3
"""test_client_registry.py — Per-client registry assertions.

For every client in case_theories._clients.CLIENTS:
  - case_file value resolves to >=1 row in documents
  - matter_prefix has >=1 row in matters
  - every non-None keystone_entities ID resolves in entities
  - operative_root TCT (if set) exists in titles
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _harness import assert_row_exists, assert_truthy, run, TruthFailure
from case_theories._clients import CLIENTS, all_ids


def make_test(client_id):
    def fn(cur):
        c = CLIENTS[client_id]
        # case_file
        cur.execute("SELECT COUNT(*) AS n FROM documents WHERE case_file = %s", (c["case_file"],))
        n_docs = cur.fetchone()["n"]
        if n_docs == 0 and client_id != "PAR":  # PAR is skeleton-only by design
            raise TruthFailure(f"{client_id}: case_file={c['case_file']!r} has 0 documents")

        # matter_prefix
        cur.execute("SELECT COUNT(*) AS n FROM matters WHERE matter_code LIKE %s",
                    (c["matter_prefix"] + "%",))
        n_matters = cur.fetchone()["n"]
        if n_matters == 0 and client_id != "PAR":
            raise TruthFailure(f"{client_id}: matter_prefix={c['matter_prefix']!r} has 0 matters")

        # keystone entities (skip None placeholders)
        for k, eid in (c.get("keystone_entities") or {}).items():
            if eid is None:
                continue
            cur.execute("SELECT canonical_name FROM entities WHERE id = %s", (eid,))
            r = cur.fetchone()
            if not r:
                raise TruthFailure(f"{client_id}: keystone {k!r}=#{eid} not in entities")

        # operative_root (if set) must exist in titles
        op = c.get("operative_root")
        if op:
            cur.execute("SELECT title_no FROM titles WHERE title_no = %s", (op,))
            r = cur.fetchone()
            if not r:
                raise TruthFailure(f"{client_id}: operative_root={op!r} not in titles")
    return fn


TESTS = [(f"registry.{cid}.coverage", make_test(cid)) for cid in all_ids()]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
