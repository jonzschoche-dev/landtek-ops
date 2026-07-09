#!/usr/bin/env python3
"""test_email_document_linkage.py — integrity of the CANONICAL email↔doc linker (`email_documents`).

Established 2026-07-09 with the extract_email_attachments build-out (deploy_805/806). `email_documents` is the
canonical many-to-many spine; `gmail_messages.document_id` is only a denormalised 1:1 cache. Two invariants keep
them coherent so an emailed filing never loses its link:

  1. RECONCILE PARITY — every `gmail_messages.document_id` (the cache) has a matching canonical
     `email_documents(message_id, doc_id)` row. A cache link with no canonical row is the drift the deploy_806
     backfill fixed (21 such rows); re-introducing one turns this RED.
  2. NO ORPHAN LINKS — every `email_documents.doc_id` points at a live `documents` row.

Deterministic, read-only, creditless.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure


def cache_has_canonical_row(cur):
    """Every gmail_messages.document_id cache link must have a canonical email_documents row."""
    cur.execute("""
        SELECT g.id, g.message_id, g.document_id
          FROM gmail_messages g
         WHERE g.document_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM email_documents e
                            WHERE e.message_id = g.message_id AND e.doc_id = g.document_id)
         ORDER BY g.id LIMIT 20""")
    bad = cur.fetchall()
    if bad:
        raise TruthFailure(
            f"{len(bad)}+ gmail_messages.document_id cache link(s) missing a canonical email_documents row "
            f"(the deploy_806 reconcile drift): "
            + "; ".join(f"msg{r['id']}→doc{r['document_id']}" for r in bad[:8])
            + ". Run `python3 extract_email_attachments.py --backfill-linker` to repair.")
    print("      [email_documents] every cache link has a canonical row")


def no_orphan_links(cur):
    """Every email_documents.doc_id must reference a live documents row."""
    cur.execute("""
        SELECT e.id, e.message_id, e.doc_id
          FROM email_documents e
          LEFT JOIN documents d ON d.id = e.doc_id
         WHERE d.id IS NULL
         ORDER BY e.id LIMIT 20""")
    bad = cur.fetchall()
    if bad:
        raise TruthFailure(
            f"{len(bad)}+ email_documents row(s) point at a non-existent document: "
            + "; ".join(f"link{r['id']}→doc{r['doc_id']}" for r in bad[:8])
            + ". Delete the dangling links or restore the documents.")
    print("      [email_documents] no orphan links (every doc_id exists)")


TESTS = [
    ("composition.email_document_cache_parity", cache_has_canonical_row),
    ("composition.email_document_no_orphans", no_orphan_links),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
