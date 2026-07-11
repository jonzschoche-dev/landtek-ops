#!/usr/bin/env python3
"""strip_plot_info.py — mine plottable geometry OUT of the corpus (titles + survey/
plan text) into the `parcels` relative-shape store.

"Strip the plot info from the maps/titles": a title's or survey plan's metes-and-bounds
block (bearing + distance calls) fully determines the parcel's SHAPE and AREA. This
sweeper finds every corpus doc that carries such calls, runs survey_geometry over them
(pure Python, $0 — NO vision/API), computes polygon + area + closure error, cross-checks
the area against the title's registered area, and persists to `parcels` — the RELATIVE
(local-meter, un-georeferenced) shape layer. Absolute placement on the world map
(`map_parcels`) is a later step that needs a tie point (see the BLLM tie-line report below).

Quality gate — the honest part: corpus OCR garbles technical descriptions
(`N. 40 deg. $5'E`, `deg`→`dog`, `E`→`B`). Garbled calls parse to a bad polygon with a
large CLOSURE ERROR. We do not pretend those are good geometry — they're flagged
`needs_reocr` and NOT written (unless --write-weak). Nothing is ever fabricated: if the
calls don't parse to >=3 courses, the doc is reported and skipped, never guessed.

Usage:
  python3 strip_plot_info.py --matter MWK-001            # dry-run report, one matter
  python3 strip_plot_info.py --matter MWK-001 --write    # persist good/weak parcels
  python3 strip_plot_info.py --doc 13                     # single doc
  python3 strip_plot_info.py --all                        # whole corpus (dry-run)

Matter separation: scoped by case_file/matter_code. Each parcel row is per-title; this
sweeper asserts NO chain relationships (T-30683 Manguisoc / T-4494 are their own parcels,
never folded into the T-4497 family — that stays the title_chain's job).
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
import parcels as P

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# Loose candidate finder (the real parser is survey_geometry._CALL). Tolerant of OCR:
# a bearing letter, degrees, deg/dog/°, a second letter, then a distance.
_CAND = re.compile(r"[NSns][.\s]?\s*\d{1,3}\s*(?:deg|dog|°|d)\b", re.I)
# stated sqm from text — matches BOTH the prose ("containing an area of … (8,706) square
# met…") and the LRA electronic-title ("AREA: … (2,587) SQUARE METERS") forms.
_AREA_TXT = re.compile(r"area\b\s*(?:of|:)?[^()]{0,80}?\(\s*([0-9][0-9,\.]{2,})\s*\)\s*"
                       r"(?:square|sq\.?)\s*met", re.I)
# tie line to a control monument: "... 2952.29 m. from BLLM No. 1, Mp. of Mercedes"
_TIE = re.compile(r"([0-9][0-9,\.]{2,})\s*m\.?\s*from\s+(BL[LB]M[^.;\n]{0,40})", re.I)
# LRA electronic-title tie point: "TIE POINT: BLLM NO. 2, MUNICIPALITY OF MERCEDES ..."
_TIE_LRA = re.compile(r"TIE\s*POINT\s*[:=]?\s*(BL[LB]M[^.;\n]{0,60})", re.I)
# LRA tie line lead — "TO CORNER 1  N. 07° 52' W 251.99 M." locates corner 1 (the georeference
# vector from the monument); it is NOT a boundary edge and must be stripped from the ring.
_LRA_TIE_LEAD = re.compile(r"TO\s+CORNER\s+\d+\b", re.I)
# One lot's technical description starts at "beginning at a point" (older prose) OR at the
# "TIE POINT:" header (modern LRA electronic title). Either marker delimits a segment.
_SEG_MARK = re.compile(r"(?i)(?:beginning\s+at\s+a\s+point|tie\s*point\s*[:=])")

CLOSURE_GOOD_M = 2.0     # <= this: trustworthy closure
CLOSURE_WEAK_M = 8.0     # in (good, weak]: usable but shaky; > weak: needs re-OCR


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def _stated_ha(cur, doc_id, text):
    """Best available registered area, in hectares. titles.area_sqm first (verified-ish),
    then a text parse of 'containing an area of (N) square meters', then documents.area_sqm."""
    cur.execute("SELECT area_sqm FROM titles WHERE source_doc_id=%s AND area_sqm IS NOT NULL "
                "ORDER BY area_sqm DESC LIMIT 1", (doc_id,))
    r = cur.fetchone()
    if r and r["area_sqm"]:
        return float(r["area_sqm"]) / 10000.0, "titles.area_sqm"
    m = _AREA_TXT.search(text or "")
    if m:
        try:
            return float(m.group(1).replace(",", "")) / 10000.0, "text:area-of"
        except ValueError:
            pass
    cur.execute("SELECT area_sqm FROM documents WHERE id=%s", (doc_id,))
    r = cur.fetchone()
    if r and r["area_sqm"]:
        return float(r["area_sqm"]) / 10000.0, "documents.area_sqm"
    return None, None


def _title_no(cur, doc_id, text, fname):
    cur.execute("SELECT tct_number FROM titles WHERE source_doc_id=%s AND tct_number IS NOT NULL "
                "LIMIT 1", (doc_id,))
    r = cur.fetchone()
    if r and r["tct_number"]:
        return r["tct_number"]
    # Prefer the LRA electronic-title number (079-2021002126: district-year-serial) — it's
    # the canonical RD form and unambiguous; then the older "T-NNNN" forms.
    m = (re.search(r"\b0\d{2}-\d{9,}\b", text or "")
         or re.search(r"\b0\d{2}-\d{9,}\b", fname or "")
         or re.search(r"\bT-\s?\d{3,}", text or "")
         or re.search(r"T-?\s?0?7?9?-?\d{3,}", fname or ""))
    return (m.group(0).replace(" ", "") if m else None)


def _quality(a):
    if not a.get("ok"):
        return "reject"
    ce = a.get("closure_error_m") or 0.0
    if ce <= CLOSURE_GOOD_M:
        return "good"
    if ce <= CLOSURE_WEAK_M:
        return "weak"
    return "needs_reocr"


def _segments(text):
    """Split a doc into per-lot technical-description segments. A TCT certified copy often
    carries SEVERAL parcels ('a parcel of land … beginning at a point …' × N); concatenating
    their calls into one ring is the false-closure failure mode (550m+ on clean text).
    Returns [(seg_no|None, seg_text)]; None seg_no = no marker found (whole doc, legacy).
    Handles BOTH the older prose form and the modern LRA electronic-title 'TIE POINT:' form."""
    starts = [m.start() for m in _SEG_MARK.finditer(text or "")]
    if not starts:
        return [(None, text or "")]
    return [(i + 1, text[s:(starts[i + 1] if i + 1 < len(starts) else len(text))])
            for i, s in enumerate(starts)]


def _strip_tie(seg):
    """Remove the tie line from a segment's ring — it locates corner 1 on the earth (the
    georeference vector), it is NOT a boundary edge, and including it corrupts the polygon.
    Handles both formats. Returns (ring_text, tie_snippet|None).

      LRA e-title:  'TIE POINT: BLLM NO. 2 … / TO CORNER 1  N. 07° 52' W 251.99 M. / 1-2 …'
                    → strip the 'TO CORNER n <call>' vector; ring = the numbered courses.
      prose:        'beginning at a point … being <bearing>, <dist> from <monument> …'
                    → strip the leading '<call> from <monument>'.
    """
    lead = _LRA_TIE_LEAD.search(seg or "")
    if lead:
        cm = sg._CALL.search(seg, lead.end())
        if cm and cm.start() - lead.end() <= 6:   # the call immediately follows "TO CORNER n"
            ring = seg[:lead.start()] + "\n" + seg[cm.end():]
            tp = _TIE_LRA.search(seg)
            tie = ((f"tie point {tp.group(1).strip()}; " if tp else "")
                   + seg[lead.start():cm.end()].strip())
            return ring, tie
    m = sg._CALL.search(seg or "")
    if m and re.match(r"\s*(?:fro?m|frm)\b", seg[m.end():m.end() + 14], re.I):
        return seg[m.end():], seg[max(0, m.start() - 40):m.end() + 90].strip()
    return seg, None


def sweep(matter=None, doc_id=None, all_corpus=False, write=False, write_weak=False):
    conn = _conn(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if doc_id:
        cur.execute("SELECT id, case_file, matter_code, extracted_text, original_filename, "
                    "document_title FROM documents WHERE id=%s", (doc_id,))
    else:
        q = ("SELECT id, case_file, matter_code, extracted_text, original_filename, "
             "document_title FROM documents WHERE extracted_text ~* "
             "'[NSns][.[:space:]]?[0-9]{1,3} ?(deg|dog|d)'")
        args = []
        if matter and not all_corpus:
            q += " AND (case_file ILIKE %s OR matter_code ILIKE %s)"
            args += [f"%{matter}%", f"%{matter}%"]
        q += " ORDER BY id"
        cur.execute(q, args)
    docs = cur.fetchall()

    rows, ties = [], []
    tally = {"good": 0, "weak": 0, "needs_reocr": 0, "reject": 0}
    for d in docs:
        text = d["extracted_text"] or ""
        if not _CAND.search(text):
            continue
        fname = d["original_filename"] or d["document_title"] or ""
        title_no = _title_no(cur, d["id"], text, fname)
        stated_ha, area_src = _stated_ha(cur, d["id"], text)
        tm = _TIE.search(text)
        if tm:
            ties.append((d["id"], title_no, tm.group(0).strip()))
        segs = _segments(text)
        doc_deleted = False
        for seg_no, seg in segs:
            ring, tie = _strip_tie(seg)
            if tie:
                ties.append((d["id"], title_no, tie))
            # stated area: this segment's own "containing an area of (N) sq m" first;
            # doc-level (titles/documents) only when the doc is a single description.
            seg_stated, seg_src = None, None
            am = _AREA_TXT.search(seg)
            if am:
                try:
                    seg_stated, seg_src = float(am.group(1).replace(",", "")) / 10000.0, "text:segment"
                except ValueError:
                    pass
            if seg_stated is None and len(segs) == 1:
                seg_stated, seg_src = stated_ha, area_src
            a = sg.cross_check(ring, seg_stated) if seg_stated else sg.analyze(ring)
            if seg_no is not None and len(segs) > 1 and (a.get("calls") or 0) < 3:
                continue  # boilerplate slice of a multi-lot doc — not a description
            q = _quality(a)
            tally[q] += 1
            rows.append(dict(doc=d["id"], seg=seg_no, matter=d["case_file"], title=title_no,
                             calls=a.get("calls"), ok=a.get("ok"),
                             area_ha=a.get("area_ha"), stated_ha=seg_stated, area_src=seg_src,
                             area_matches=a.get("area_matches"),
                             closure_m=a.get("closure_error_m"), quality=q,
                             reason=a.get("reason")))
            if write and q in (("good", "weak") if write_weak else ("good",)):
                if not doc_deleted:
                    # idempotent: this sweeper owns the rows for this source_doc_id
                    cur.execute("DELETE FROM parcels WHERE source_doc_id=%s", (d["id"],))
                    doc_deleted = True
                P.upsert_parcel(d["case_file"] or matter, title_no, ring, d["id"], seg_stated)

    # ---- report ----
    print(f"\n{'doc':>5} {'title':<16} {'calls':>5} {'area_ha':>9} {'stated':>8} "
          f"{'clos_m':>7}  quality")
    print("-" * 72)
    for r in sorted(rows, key=lambda x: (x["quality"], -(x["calls"] or 0))):
        ah = f"{r['area_ha']:.3f}" if r["area_ha"] else "—"
        st = f"{r['stated_ha']:.3f}" if r["stated_ha"] else "—"
        cm = f"{r['closure_m']:.1f}" if r["closure_m"] is not None else "—"
        mark = "" if r["area_matches"] is None else ("✓" if r["area_matches"] else "✗area")
        label = f"{r['doc']}#{r['seg']}" if r.get("seg") else str(r["doc"])
        print(f"{label:>8} {str(r['title'] or '?'):<16} {str(r['calls'] or 0):>5} "
              f"{ah:>9} {st:>8} {cm:>7}  {r['quality']} {mark}")

    print(f"\nSummary: {len(rows)} description segment(s) across docs · "
          f"good={tally['good']} weak={tally['weak']} "
          f"needs_reocr={tally['needs_reocr']} reject={tally['reject']}")
    if ties:
        print(f"\nTIE LINES found ({len(ties)}) — georeferencing anchors for the map_parcels bridge:")
        for did, tno, snip in ties:
            print(f"  doc {did} ({tno or '?'}): …{snip}…")
    if write:
        wq = "good+weak" if write_weak else "good"
        print(f"\nWROTE parcels for quality={wq}. needs_reocr/reject were NOT written "
              f"(flag for vision re-OCR — never fabricated).")
    else:
        print("\n(dry-run — nothing written. add --write to persist good parcels, "
              "--write --write-weak to include shaky ones.)")
    cur.close(); conn.close()


def main():
    ap = argparse.ArgumentParser(description="Strip plot geometry from corpus titles/plans")
    ap.add_argument("--matter", help="case_file / matter code (e.g. MWK-001)")
    ap.add_argument("--doc", type=int, help="single document id")
    ap.add_argument("--all", action="store_true", help="sweep the whole corpus")
    ap.add_argument("--write", action="store_true", help="persist good parcels")
    ap.add_argument("--write-weak", action="store_true", help="also persist weak-closure parcels")
    args = ap.parse_args()
    if not (args.matter or args.doc or args.all):
        ap.error("give --matter, --doc, or --all")
    sweep(matter=args.matter, doc_id=args.doc, all_corpus=args.all,
          write=args.write, write_weak=args.write_weak)


if __name__ == "__main__":
    main()
