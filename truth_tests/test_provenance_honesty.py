#!/usr/bin/env python3
"""test_provenance_honesty.py — the R2/R10 measurement floor: provenance tier must be EARNED, not asserted.

The reasoning-layer audit (deploy_986) found the stack's single most systemic reasoning defect: the provenance
tier is written as a hardcoded string literal decoupled from any confidence signal, so `inferred_strong` /
`verified` do not discriminate quality. Grounded 2026-07-19:
  - doc_populate (27,582 facts) + harvest (8,854): tier-cardinality=1 (only `inferred_strong`), 100% NULL-confidence
    — literal rubber stamps producing ~86% of the KB;
  - 4,879 `verified` facts cite a source doc scoring <0.5 OCR (the doc-34 "in for simple" garbled-verified class);
  - 808 facts cite an owner-unresolvable doc (the doc_populate owner-gate bypass).

This is a MEASUREMENT floor (measure-don't-model doctrine), additive + $0, NO behaviour change: it makes the
dishonesty VISIBLE on every run and turns it into a tracked regression BEFORE any literal-flip or OCR-cap (those
are operator-gated behaviour changes — no silent flips). Design of the one hard assertion:
  - the existing debt (doc_populate/harvest rubber stamps, the 4,879 low-OCR-verified, the 808 NULL-owner) is
    REPORTED loudly, not hard-failed — hard-failing would block the deploy gate on pre-existing debt (and
    doc_populate grows it hourly until it is gated). Reporting keeps it honest without a false gate-block.
  - the hard bite is a NEW rubber-stamp WRITER: a created_by NOT already known to stamp a constant tier that
    starts emitting a meaningful volume at tier-cardinality=1 + ≥90% NULL-confidence. That catches the pattern
    SPREADING to a new writer (a real regression) while the known offenders stay a report line. Negative-tested.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure

# Writers ALREADY known (2026-07-19 baseline) to stamp a constant tier — the existing debt, surfaced not
# gated. A writer here may grow freely; a NEW name joining the rubber-stamp pattern is the regression that bites.
KNOWN_LITERAL_WRITERS = {
    "doc_populate", "harvest", "inquiry_stack", "cowork_comprehend",
    "adjudicate_queue", "contradiction_resolution",
}
NEW_WRITER_MIN = 50          # a new writer must reach this volume before it counts (ignore one-off sessions)


def provenance_calibration_reported(cur):
    """Report-only (threshold-free): per-writer tier-cardinality + NULL-confidence — makes 'always-strong' visible."""
    cur.execute("""
        SELECT created_by, count(*) n, count(DISTINCT provenance_level) tiers,
               round(100.0 * count(*) FILTER (WHERE confidence IS NULL) / count(*)) nullconf
        FROM matter_facts GROUP BY 1 HAVING count(*) >= 20 ORDER BY 2 DESC LIMIT 12""")
    rows = cur.fetchall()
    stamps = [r for r in rows if r["tiers"] == 1 and (r["nullconf"] or 0) >= 90]
    print(f"      [prov-honesty] {len(stamps)} rubber-stamp writer(s) (tier-cardinality=1, ≥90% null-conf) of "
          f"{len(rows)} ≥20-fact writers:")
    for r in rows:
        flag = "  <-- RUBBER STAMP" if (r["tiers"] == 1 and (r["nullconf"] or 0) >= 90) else ""
        print(f"        {r['created_by']:26} n={r['n']:6} tiers={r['tiers']} null_conf={r['nullconf']}%{flag}")


def contamination_signals_reported(cur):
    """Report-only: the two integrity-breach counts (verified-from-low-OCR + NULL-owner). Surfaced, not gated —
    the fixes (cap provenance by OCR score; gate doc_populate) are operator-gated behaviour changes."""
    v = n = None
    try:
        cur.execute("""SELECT count(*) c FROM matter_facts mf JOIN ocr_quality oq ON oq.doc_id = mf.source_id::int
                       WHERE mf.provenance_level='verified' AND mf.source_id ~ '^[0-9]+$' AND oq.score < 0.5""")
        v = cur.fetchone()["c"]
    except Exception:
        pass
    cur.execute("""SELECT count(*) c FROM matter_facts mf WHERE mf.source_id ~ '^[0-9]+$'
                   AND EXISTS (SELECT 1 FROM documents d WHERE d.id = mf.source_id::int
                               AND _client_of(COALESCE(d.matter_code, d.case_file)) IS NULL)""")
    n = cur.fetchone()["c"]
    print(f"      [prov-honesty] verified-from-OCR<0.5 (doc-34 garbled-verified class): {v} "
          f"(provisional 0.5 threshold — calibrate vs the score distribution before enforcing a cap) · "
          f"NULL-owner-cited facts: {n} (operator disposition; wire owner_gate into doc_populate to stop growth)")


def no_new_rubber_stamp_writer(cur):
    """HARD: a created_by NOT in the known baseline emitting ≥NEW_WRITER_MIN facts at tier-cardinality=1 AND
    ≥90% NULL-confidence — the rubber-stamp pattern SPREADING to a new writer. Bites regressions; the known
    offenders (surfaced above) do not trip it."""
    cur.execute("""
        SELECT created_by, count(*) n,
               round(100.0 * count(*) FILTER (WHERE confidence IS NULL) / count(*)) nullconf
        FROM matter_facts
        WHERE provenance_level IS NOT NULL
        GROUP BY 1 HAVING count(DISTINCT provenance_level) = 1 AND count(*) >= %s
        ORDER BY 2 DESC""", (NEW_WRITER_MIN,))
    offenders = [(r["created_by"], r["n"], r["nullconf"]) for r in cur.fetchall()
                 if (r["nullconf"] or 0) >= 90 and r["created_by"] not in KNOWN_LITERAL_WRITERS]
    if offenders:
        raise TruthFailure(
            f"{len(offenders)} NEW rubber-stamp writer(s) — a created_by not in the 2026-07-19 baseline is "
            f"emitting ≥{NEW_WRITER_MIN} facts at a single provenance tier with ≥90% NULL confidence (the "
            f"asserted-not-earned defect spreading): {offenders}. Assign a mechanical confidence signal (source "
            f"ocr_quality.score), or if a rule-writer, use a discriminating tier — never a constant. If this is "
            f"a legitimate new deterministic writer, add it to KNOWN_LITERAL_WRITERS with a why.")


TESTS = [
    ("provenance.calibration_reported", provenance_calibration_reported),
    ("provenance.contamination_signals_reported", contamination_signals_reported),
    ("provenance.no_new_rubber_stamp_writer", no_new_rubber_stamp_writer),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
