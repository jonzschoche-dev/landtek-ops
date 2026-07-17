#!/usr/bin/env python3
"""geometry_collect.py — the RESOURCEFUL collector: gather every coordinate-witness for a parcel
from across the whole stack, and DISPATCH work to the other engines to fill the gaps.

The geometry engine must not work from one source. The same metes-and-bounds appear in several
places — the survey PLAN's lot table, every certified copy of the TITLE, the DENR cadastral
projection, and any pleading that quotes the technical description. This collector:

  1. SCANS the corpus for every doc that carries this title's (or its correlates') courses/area.
  2. CLASSIFIES each witness: clean_courses (parses + closes) · garbled (has calls but won't
     parse — an OCR job) · area_only (states the area — an affirmation).
  3. RECONCILES the clean witnesses (defers to geometry_consensus) and reports the corroboration.
  4. DISPATCHES the garbled witnesses to the OCR engine — enqueues them in geometry_priority so
     the re-OCR drip cleans them — i.e. it talks to the other engine to COLLECT the data, instead
     of stopping at "the text is garbled."
  5. SURFACES the correlations (plan lot -> title -> cadastral lot) so a coordinate proven in one
     is known to corroborate the others.

  python3 geometry_collect.py --title T-32911 [--matter MWK-001] [--dispatch]

--dispatch actually enqueues the garbled witnesses for re-OCR (the cross-engine action);
without it the run is a read-only inventory + collection plan.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import survey_geometry as sg
import strip_plot_info as SP

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _witness_class(text):
    """Best segment of a doc: (klass, n_courses, closure, area_sqm). klass in
    clean_courses | garbled | area_only | none."""
    best = ("none", 0, None, None)
    for _sno, seg in SP._segments(text or ""):
        ring, _tie = SP._strip_tie(seg)
        a = sg.analyze(ring)
        n = a.get("calls") or 0
        if a.get("ok") and n >= 3:
            clo = a.get("closure_error_m")
            comp = SP._compactness(a)
            klass = "clean_courses" if (clo is not None and clo <= 8 and comp >= SP.COMPACT_MIN) else "garbled"
            if n > best[1]:
                best = (klass, n, clo, a.get("area_sqm"))
    if best[0] == "none":
        am = SP._AREA_TXT.search(text or "")
        if am:
            try:
                return ("area_only", 0, None, float(am.group(1).replace(",", "")))
            except ValueError:
                pass
    return best


def collect(title_no, matter, dispatch=False):
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    tnorm = re.sub(r"[^0-9A-Za-z]", "", title_no.upper())
    digits = re.sub(r"[^0-9]", "", title_no)[-5:]

    # 1. RESOURCEFUL SCAN — every corpus doc that mentions this title and carries survey content.
    cur.execute(
        "SELECT id, coalesce(document_title,original_filename,'?') AS name, extracted_text "
        "FROM documents WHERE (case_file ILIKE %s OR matter_code ILIKE %s) "
        "AND extracted_text ~* %s "
        "AND extracted_text ~* '([NSns][.[:space:]]{0,3}[0-9]{1,3}[[:space:]]*(deg|dog|d|°)|area)'",
        (f"%{matter}%", f"%{matter}%", r"T[- ]?0?" + digits + r"\b"))
    docs = cur.fetchall()

    witnesses = {"clean_courses": [], "garbled": [], "area_only": []}
    for d in docs:
        klass, n, clo, area = _witness_class(d["extracted_text"])
        if klass == "none":
            continue
        witnesses.setdefault(klass, []).append(
            {"doc": d["id"], "name": d["name"][:42], "courses": n, "closure": clo, "area": area})

    # 2. what geometry we already hold (the plan-verified shape etc.)
    cur.execute("SELECT id, area_sqm, closure_error_m, calls, provenance_level, source_doc_id "
                "FROM parcels WHERE title_no=%s", (title_no,))
    have = cur.fetchall()

    # 3. REPORT
    print(f"=== coordinate-witness collection — {title_no} ===\n")
    if have:
        for h in have:
            print(f"HELD geometry: parcels id={h['id']} · {float(h['area_sqm'] or 0):,.0f} m² · "
                  f"closure {h['closure_error_m']} m · {h['calls']} courses · {h['provenance_level']} "
                  f"(from doc {h['source_doc_id']})")
    else:
        print("HELD geometry: none yet.")
    for k, lbl in [("clean_courses", "✅ CLEAN course witnesses (feed consensus)"),
                   ("garbled", "⚠  GARBLED course witnesses (OCR needed → dispatch to re-OCR)"),
                   ("area_only", "○ AREA-only witnesses (affirm the area)")]:
        ws = witnesses.get(k, [])
        print(f"\n{lbl}: {len(ws)}")
        for w in ws[:12]:
            extra = (f"{w['courses']}c closure={w['closure']}m" if k != "area_only"
                     else f"area={w['area']:,.0f}")
            print(f"    doc {w['doc']:>4}  {w['name']:<42} {extra}")

    # 4. DISPATCH — communicate to the OCR engine: enqueue garbled witnesses for re-OCR.
    garbled_ids = [w["doc"] for w in witnesses.get("garbled", [])]
    if garbled_ids:
        print(f"\nCROSS-ENGINE DISPATCH → re-OCR queue (geometry_priority): {garbled_ids}")
        if dispatch:
            n = 0
            for did in garbled_ids:
                cur.execute(
                    "INSERT INTO geometry_priority (doc_id, title_no, matter_code, rank, note) "
                    "SELECT %s,%s,%s,55,'garbled coordinate-witness collected for %s — clean to corroborate' "
                    "WHERE EXISTS (SELECT 1 FROM documents WHERE id=%s) "
                    "ON CONFLICT (doc_id) DO NOTHING",
                    (did, title_no, matter, title_no, did))
                n += cur.rowcount
            print(f"  enqueued {n} doc(s) for the re-OCR drip to clean.")
        else:
            print("  (--dispatch to actually enqueue them for the OCR engine)")

    # 5. verdict
    nclean = len(witnesses.get("clean_courses", []))
    print(f"\nverdict: {nclean} clean course-witness(es), {len(garbled_ids)} recoverable via OCR, "
          f"{len(witnesses.get('area_only', []))} area affirmations. "
          + ("Multi-source corroboration available now — run geometry_consensus." if nclean >= 2 else
             "Need OCR/LDC to unlock a corroborating witness." if nclean < 2 else ""))
    cur.close(); conn.close()


def main():
    ap = argparse.ArgumentParser(description="Resourceful coordinate-witness collector")
    ap.add_argument("--title", required=True)
    ap.add_argument("--matter", default="MWK-001")
    ap.add_argument("--dispatch", action="store_true", help="enqueue garbled witnesses for re-OCR")
    a = ap.parse_args()
    collect(a.title, a.matter, dispatch=a.dispatch)


if __name__ == "__main__":
    main()
