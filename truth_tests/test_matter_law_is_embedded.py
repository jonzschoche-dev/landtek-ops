#!/usr/bin/env python3
"""test_matter_law_is_embedded.py — corpus-wide assertion for A53 (offline sovereignty — the LAW side).

**What A53 requires (law facet).** The stack must REASON with no internet — so the applicable law has to live
IN the corpus, never be fetched. This test makes that provable for the law our MATTERS actually rely on: every
legal authority linked to a matter (`matter_authorities` → `legal_authorities`) must be available OFFLINE —
either its own local `full_text` OR matching embedded `legal_chunks`. An authority a matter's theory depends on
but that isn't local would make that matter un-reasonable offline (LawAsMeasure with nothing to measure against).

**Symmetric to `test_connected_document_count.py` (A41, the document side).** That asserts a document's 5 signals
are local; this asserts the LAW a matter cites is local. It is count-INDEPENDENT — it stays honest as matters
cite more law (a new statute must be ingested before a matter relies on it), and fails only on a real gap.
Verified 2026-07-08: 59 relied-on authorities, all offline-available, **0 gap** — LGC (RA 7160), PD 1529
(property registration), RA 11032 (ARTA), RA 3019/6713 (anti-graft/conduct), Civil Code, RPC, Constitution,
Rules of Court all embedded. Deterministic, read-only, creditless.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure

# Every DISTINCT legal authority a matter relies on, + whether it's available offline (own full_text OR
# matching embedded legal_chunks). legal_authorities.citation and legal_chunks.citation share a format.
_RELIED = """
  SELECT DISTINCT la.id, la.citation,
    (coalesce(length(la.full_text), 0) >= 200
     OR EXISTS (SELECT 1 FROM legal_chunks lc WHERE lc.citation = la.citation)) AS offline_available
  FROM matter_authorities ma
  JOIN legal_authorities la ON la.id = ma.authority_id
"""


def matter_law_is_embedded(cur):
    """A53 (law side): every legal authority a matter relies on must be locally available (full_text or chunks)."""
    cur.execute(f"SELECT citation FROM ({_RELIED}) r WHERE NOT offline_available ORDER BY citation LIMIT 25")
    gaps = [r["citation"] for r in cur.fetchall()]
    if gaps:
        raise TruthFailure(
            f"{len(gaps)} legal authorit(ies) a matter RELIES ON are NOT available offline — neither local "
            f"`full_text` nor embedded `legal_chunks` (A53: the stack must reason unplugged; the applicable law "
            f"must be in the corpus): {gaps}. Ingest the statute/case into `legal_chunks` (or store its "
            f"`full_text`) before a matter's theory depends on it.")


def matter_law_coverage_reported(cur):
    """Non-threshold visibility: surface the offline-law coverage on every run (A53 headline number)."""
    cur.execute(f"SELECT count(*) AS relied, count(*) FILTER (WHERE offline_available) AS avail FROM ({_RELIED}) r")
    r = cur.fetchone()
    if r is None or r["relied"] is None:
        raise TruthFailure("matter-law coverage query returned no rows — schema/read problem")
    print(f"      [offline-law] {r['avail']}/{r['relied']} matter-relied legal authorities available offline (A53)")


TESTS = [
    ("offline.matter_law_is_embedded", matter_law_is_embedded),
    ("offline.matter_law_coverage_reported", matter_law_coverage_reported),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
