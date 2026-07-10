#!/usr/bin/env python3
"""test_law_corpus_intact.py — the law corpus must stay PRESENT + INTACT for the stack.

Companion to test_matter_law_is_embedded.py (which asserts the law a MATTER relies on is offline-available).
That test is scoped to matter-linked authorities; it would stay green even if the broader library were
truncated, or if an authority's embeddings vanished, as long as no *currently-linked* piece was missing.

This asserts the corpus as a WHOLE is healthy, so degradation fails the deploy gate LOUDLY instead of
silently starving retrieval:
  - present   — legal_chunks / legal_authorities above a disaster-floor (catches a wipe or mass truncation)
  - intact    — no authority row backed by NEITHER local full_text NOR embedded chunks (no orphaned authority)
  - queryable — no embedded chunk with a NULL embedding vector (nulled embeddings break semantic retrieval
                even when the text survives — the exact failure a plain row-count check would miss)

The floors are DISASTER thresholds (well below the live corpus), not targets — the corpus only grows, so a
reading below them means loss, not normal variation. Deterministic, read-only, creditless.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure

# Disaster-floors: the live corpus is ~60 authorities / ~6,600 chunks and only grows. A reading below these
# means the library was wiped or mass-truncated (e.g. a bad migration or a restore that didn't complete).
FLOOR_CHUNKS = 1000
FLOOR_AUTHORITIES = 25


def corpus_present_above_floor(cur):
    cur.execute("SELECT (SELECT count(*) FROM legal_chunks) AS chunks, "
                "(SELECT count(*) FROM legal_authorities) AS auths")
    r = cur.fetchone()
    if r["chunks"] < FLOOR_CHUNKS or r["auths"] < FLOOR_AUTHORITIES:
        raise TruthFailure(
            f"law corpus below disaster-floor — {r['chunks']} legal_chunks (floor {FLOOR_CHUNKS}) / "
            f"{r['auths']} legal_authorities (floor {FLOOR_AUTHORITIES}). The library was wiped or mass-"
            f"truncated; restore from the latest pg_dump (Google Drive: LANDTEK/08 - Internal/Backups) — "
            f"the dump holds the embeddings, so recovery does NOT require re-fetching lawphil or re-embedding.")


def no_orphaned_authority(cur):
    """Every authority must be backed offline by its own full_text OR embedded chunks — else it is a dead row
    the stack cannot reason from (its chunks were deleted but the row remained)."""
    cur.execute("""SELECT count(*) AS n FROM legal_authorities la
        WHERE coalesce(length(la.full_text), 0) < 200
          AND NOT EXISTS (SELECT 1 FROM legal_chunks lc WHERE lc.citation = la.citation)""")
    n = cur.fetchone()["n"]
    if n:
        raise TruthFailure(
            f"{n} legal_authorities have NEITHER local full_text NOR embedded chunks — orphaned rows the "
            f"stack cannot read. Re-ingest them (scripts/ingest_jurisprudence.py --file <manifest> or "
            f"corpus_ingest.py); the ingest is idempotent and skips anything already present.")


def embeddings_not_null(cur):
    """A chunk with a NULL embedding is invisible to semantic retrieval even though its text survives — the
    silent-degradation case a row-count check would pass right over."""
    cur.execute("SELECT count(*) AS n FROM legal_chunks WHERE embedding IS NULL")
    n = cur.fetchone()["n"]
    if n:
        raise TruthFailure(
            f"{n} legal_chunks have a NULL embedding — present as text but unreachable by semantic search. "
            f"Re-embed with scripts/ingest_jurisprudence.py --force <manifest> (or corpus_ingest.py --force).")


def corpus_health_reported(cur):
    """Non-threshold visibility: print the corpus headline on every run."""
    cur.execute("""SELECT (SELECT count(*) FROM legal_authorities) AS auths,
                          (SELECT count(*) FROM legal_authorities WHERE authority_type='case') AS cases,
                          (SELECT count(*) FROM legal_chunks) AS chunks,
                          (SELECT count(*) FROM legal_chunks WHERE embedding IS NOT NULL) AS embedded""")
    r = cur.fetchone()
    print(f"      [law-corpus] {r['auths']} authorities ({r['cases']} cases) · "
          f"{r['embedded']}/{r['chunks']} chunks embedded")


TESTS = [
    ("law_corpus.present_above_floor", corpus_present_above_floor),
    ("law_corpus.no_orphaned_authority", no_orphaned_authority),
    ("law_corpus.embeddings_not_null", embeddings_not_null),
    ("law_corpus.health_reported", corpus_health_reported),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
