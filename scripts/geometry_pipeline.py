#!/usr/bin/env python3
"""geometry_pipeline.py — drip-drain the geometry_priority queue into plottable parcels.

Two-stage, per doc, reusing the mature machinery already in the stack:

  1. CLEAN  — reocr_gemini.reocr(doc_id, go=True): re-OCR the page with Gemini vision
              (Drive-fetch fallback, key×model ladder, backs up old text). This replaces the
              GARBLED technical description (Tesseract turned `269.35 m` into noise) with a
              faithful transcription that preserves bearings exactly.
  2. STRIP  — strip_plot_info: parse the now-clean metes-and-bounds → survey_geometry →
              `parcels` (relative shape + area + closure error, area cross-checked vs the title).

Designed to DRIP within the Gemini free tier, never crash:
  * Bounded per run (--max, default 6 docs) so a run is cheap.
  * Skips docs already re-OCR'd (reocr_log) — resumable.
  * On QuotaExhausted (all keys/models 429) it STOPS CLEANLY and exits 0 — the remaining
    docs wait for the next daily reset. That is the intended degrade, not a failure.

Usage:
  python3 geometry_pipeline.py                 # drip the next --max priority docs, then strip
  python3 geometry_pipeline.py --max 3
  python3 geometry_pipeline.py --docs 96,21    # force specific docs
  python3 geometry_pipeline.py --strip-only    # skip re-OCR; just re-parse clean text -> parcels
  python3 geometry_pipeline.py --matter MWK-001

Run daily via landtek-geometry-drip.timer.
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reocr_gemini as R
import strip_plot_info as S

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _pending(limit, docs=None):
    """Priority doc_ids not yet re-OCR'd, worst-rank first."""
    c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS reocr_log (doc_id int PRIMARY KEY,
                   ts timestamptz DEFAULT now(), chars_before int, chars_after int, note text)""")
    if docs:
        cur.execute("SELECT doc_id, title_no, matter_code FROM geometry_priority "
                    "WHERE doc_id = ANY(%s) ORDER BY rank", (docs,))
    else:
        cur.execute("""SELECT doc_id, title_no, matter_code FROM geometry_priority
                       WHERE doc_id NOT IN (SELECT doc_id FROM reocr_log)
                       ORDER BY rank LIMIT %s""", (limit,))
    rows = cur.fetchall(); cur.close(); c.close()
    return rows


def run(max_docs=6, docs=None, strip_only=False, matter="MWK-001", rpm=8, write_weak=True):
    matters = set()
    if not strip_only:
        pending = _pending(max_docs, docs)
        if not pending:
            print("[geometry] no pending priority docs to re-OCR.")
        else:
            R._RPM = max(0, rpm)  # throttle to be a good free-tier citizen
            print(f"[geometry] re-OCR {len(pending)} priority doc(s): "
                  f"{[d[0] for d in pending]}", flush=True)
            for doc_id, title_no, mcode in pending:
                matters.add(mcode or matter)
                try:
                    r = R.reocr(doc_id, go=True)
                except R.QuotaExhausted:
                    print(f"[geometry] Gemini quota exhausted — stopping cleanly at doc {doc_id}; "
                          f"remaining docs drain after the next daily reset.", flush=True)
                    break
                if r.get("error"):
                    print(f"  doc {doc_id} ({title_no}): re-OCR error: {r['error']}", flush=True)
                else:
                    print(f"  doc {doc_id} ({title_no}): re-OCR ok "
                          f"{r.get('chars_before')}→{r.get('chars_after')} chars"
                          f"{' [written]' if r.get('written') else ''}", flush=True)
    else:
        matters.add(matter)

    # STRIP: parse whatever is now clean into parcels (idempotent; only good/weak written).
    for m in (matters or {matter}):
        print(f"\n[geometry] strip_plot_info --matter {m} --write:", flush=True)
        S.sweep(matter=m, write=True, write_weak=write_weak)


def main():
    ap = argparse.ArgumentParser(description="Drip corpus geometry into parcels")
    ap.add_argument("--max", type=int, default=6, help="max docs to re-OCR this run")
    ap.add_argument("--docs", help="comma-separated doc_ids to force")
    ap.add_argument("--strip-only", action="store_true", help="skip re-OCR; just parse clean text")
    ap.add_argument("--matter", default="MWK-001")
    ap.add_argument("--rpm", type=int, default=8)
    args = ap.parse_args()
    docs = [int(x) for x in args.docs.split(",")] if args.docs else None
    run(max_docs=args.max, docs=docs, strip_only=args.strip_only,
        matter=args.matter, rpm=args.rpm)


if __name__ == "__main__":
    main()
