#!/usr/bin/env python3
"""geometry_consensus.py — multi-source affirmation of parcel geometry (anti-single-OCR).

A course extracted from ONE document is an assertion, not a fact. The same boundary is
described by SEVERAL corpus witnesses (multiple certified copies of the title, the survey
plan, the titles register, operator ground truth). This engine:

  1. extracts each source's courses into `parcel_courses` (verbatim raw_call kept = excerpt),
  2. ALIGNS the sequences across sources and classifies every course:
        ✔ corroborated (≥2 independent docs agree)  ·  ○ single-source  ·  ✖ CONFLICT,
  3. applies MANUAL corrections (`parcel_course_corrections`, operator provenance — a human
     read the scan; outranks everything),
  4. composes the consensus ring, computes closure + area, and TRIANGULATES the area against
     every stated source (each copy's "containing an area of", titles.area_sqm incl. the
     operator-asserted value, plan corner counts),
  5. writes to `parcels` ONLY when closure passes; provenance reflects how it was affirmed
     (operator > inferred_corroborated > inferred_strong). Doubts are never silently accepted
     — they are the review list.

Usage:
  python3 geometry_consensus.py build  --title T-4497 [--matter MWK-001] [--write]
  python3 geometry_consensus.py review --title T-4497
  python3 geometry_consensus.py correct --title T-4497 --pos 12 --action replace \
      --bearing "N. 18 deg 34' W." --distance 240.90 --reason "read from doc 684 scan"
  python3 geometry_consensus.py correct --title T-4497 --pos 16 --action insert \
      --bearing "S. 49 deg 30' E." --distance 133.83 --reason "course missing from all OCR copies; on plan"
"""
from __future__ import annotations

import argparse
import difflib
import os
import re
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import survey_geometry as sg
import strip_plot_info as SP
import parcels as P

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
CLOSURE_WRITE_M = 8.0          # composed ring must close at least this well to be written
AZ_TOL, DIST_TOL = 1.5, 1.0    # near-agreement tolerance (deg, meters)


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def _norm_title(t):
    return re.sub(r"[^A-Z0-9]", "", (t or "").upper())


def _az_to_call(az, dist):
    """Azimuth (cw from N) + distance -> canonical bearing call text sg can re-parse."""
    az = az % 360.0
    if az < 90:    q1, q2, a = "N", "E", az
    elif az < 180: q1, q2, a = "S", "E", 180 - az
    elif az < 270: q1, q2, a = "S", "W", az - 180
    else:          q1, q2, a = "N", "W", 360 - az
    d = int(a); m = int(round((a - d) * 60))
    if m == 60: d, m = d + 1, 0
    return f"{q1}. {d} deg {m:02d}' {q2}., {dist:.2f} m"


def _courses_from_text(text):
    """[(azimuth, dist, raw)] for each call in a ring text, in order."""
    out = []
    for m in sg._CALL.finditer(text or ""):
        parsed = list(sg.parse_calls(m.group(0)))
        if parsed:
            out.append((parsed[0][0], parsed[0][1], " ".join(m.group(0).split())))
    return out


def _tok(c):
    """Quantized token for sequence alignment."""
    return (round(c[0]), round(c[1] * 2) / 2)


def _near(a, b):
    return abs(a[0] - b[0]) <= AZ_TOL and abs(a[1] - b[1]) <= DIST_TOL


# ---------------------------------------------------------------- extraction

def extract_sources(cur, title_no, matter):
    """Find every corpus doc asserting courses for this title; return {doc_id: {seg: courses}}."""
    tnorm = _norm_title(title_no)
    cur.execute(
        "SELECT id, case_file, extracted_text, original_filename, document_title FROM documents "
        "WHERE extracted_text ~* '[NSns][.[:space:]]?[0-9]{1,3} ?(deg|dog|d)' "
        "AND (case_file ILIKE %s OR matter_code ILIKE %s)", (f"%{matter}%", f"%{matter}%"))
    sources = {}
    for d in cur.fetchall():
        fname = d["original_filename"] or d["document_title"] or ""
        if _norm_title(SP._title_no(cur, d["id"], d["extracted_text"], fname)) != tnorm:
            continue
        segs = {}
        for seg_no, seg in SP._segments(d["extracted_text"] or ""):
            ring, _tie = SP._strip_tie(seg)
            courses = _courses_from_text(ring)
            if len(courses) >= 3:
                segs[seg_no or 1] = courses
        if segs:
            sources[d["id"]] = segs
    return sources


def persist_courses(cur, title_no, matter, sources):
    for doc_id, segs in sources.items():
        cur.execute("DELETE FROM parcel_courses WHERE source_doc_id=%s", (doc_id,))
        for seg, courses in segs.items():
            for i, (az, dist, raw) in enumerate(courses, 1):
                cur.execute(
                    "INSERT INTO parcel_courses (title_no, matter_code, source_doc_id, seg, idx, "
                    "azimuth_deg, distance_m, raw_call) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (source_doc_id, seg, idx) DO NOTHING",
                    (title_no, matter, doc_id, seg, i, az, dist, raw))


# ---------------------------------------------------------------- alignment

def align(sources):
    """Pick the longest sequence as backbone; align every other source to it.
    Returns (backbone_doc, backbone list, per-course status list, extras, conflicts)."""
    flat = [(doc, seg, courses) for doc, segs in sources.items() for seg, courses in segs.items()]
    if not flat:
        return None, [], [], [], []
    flat.sort(key=lambda x: -len(x[2]))
    bdoc, bseg, backbone = flat[0]
    agree = [{f"{bdoc}#{bseg}"} for _ in backbone]      # which sources back each course
    conflicts, extras = [], []
    for doc, seg, courses in flat[1:]:
        src = f"{doc}#{seg}"
        smt = difflib.SequenceMatcher(a=[_tok(c) for c in backbone],
                                      b=[_tok(c) for c in courses], autojunk=False)
        for op, a1, a2, b1, b2 in smt.get_opcodes():
            if op == "equal":
                for k in range(a2 - a1):
                    agree[a1 + k].add(src)
            elif op == "replace":
                for k in range(max(a2 - a1, b2 - b1)):
                    ai, bi = a1 + k, b1 + k
                    if ai < a2 and bi < b2:
                        if _near(backbone[ai], courses[bi]):
                            agree[ai].add(src)          # near-agreement within tolerance
                        else:
                            conflicts.append((ai + 1, backbone[ai], src, courses[bi]))
                    elif bi < b2:
                        extras.append((src, courses[bi]))
            elif op == "insert":
                for k in range(b1, b2):
                    extras.append((src, courses[k]))
    return f"{bdoc}#{bseg}", backbone, agree, extras, conflicts


def apply_corrections(cur, title_no, ring):
    """Apply operator corrections to the consensus ring. Returns (ring, n_applied, notes)."""
    cur.execute("SELECT position, action, azimuth_deg, distance_m, raw_call, reason "
                "FROM parcel_course_corrections WHERE title_no=%s ORDER BY position", (title_no,))
    n, notes = 0, []
    for pos, action, az, dist, raw, reason in cur.fetchall():
        i = pos - 1
        if action == "replace" and 0 <= i < len(ring):
            ring[i] = (az, dist, f"[operator] {raw or _az_to_call(az, dist)}")
        elif action == "insert" and 0 <= i <= len(ring):
            ring.insert(i, (az, dist, f"[operator] {raw or _az_to_call(az, dist)}"))
        elif action == "delete" and 0 <= i < len(ring):
            ring.pop(i)
        else:
            notes.append(f"correction pos {pos} ({action}) out of range — skipped"); continue
        n += 1
        notes.append(f"pos {pos} {action}: {reason}")
    return ring, n, notes


# ---------------------------------------------------------------- affirmation

def affirmations(cur, title_no, sources, computed_ha):
    """Triangulate computed area against every independent stated source."""
    out = []
    cur.execute("SELECT area_sqm, provenance_notes FROM titles WHERE tct_number=%s", (title_no,))
    r = cur.fetchone()
    if r and r["area_sqm"]:
        ha = float(r["area_sqm"]) / 10000.0
        out.append(("titles register" + (" (operator-asserted)" if "operator" in (r["provenance_notes"] or "") else ""),
                    ha, computed_ha and abs(computed_ha - ha) / ha <= 0.05))
    for doc_id in sources:
        cur.execute("SELECT extracted_text FROM documents WHERE id=%s", (doc_id,))
        text = (cur.fetchone() or {}).get("extracted_text") or ""
        m = SP._AREA_TXT.search(text)
        if m:
            try:
                ha = float(m.group(1).replace(",", "")) / 10000.0
                out.append((f"doc {doc_id} stated area", ha,
                            computed_ha and abs(computed_ha - ha) / ha <= 0.05))
            except ValueError:
                pass
        cm = re.search(r"\(([0-9]{1,3})\s*corners?\)", text, re.I)
        if cm:
            out.append((f"doc {doc_id} corner count", int(cm.group(1)), None))
    return out


# ---------------------------------------------------------------- commands

def build(title_no, matter, write=False):
    conn = _conn(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    sources = extract_sources(cur, title_no, matter)
    if not sources:
        print(f"No corpus source asserts courses for {title_no}."); return
    persist_courses(cur, title_no, matter, sources)
    backbone_src, backbone, agree, extras, conflicts = align(sources)
    ring = list(backbone)
    ring, n_corr, corr_notes = apply_corrections(cur, title_no, ring)

    calls_text = "\n".join(_az_to_call(az, d) for az, d, _ in ring)
    a = sg.analyze(calls_text)
    computed_ha = a.get("area_ha")

    print(f"=== CONSENSUS — {title_no} · {len(sources)} source doc(s): {sorted(sources)} ===")
    print(f"backbone: {backbone_src} ({len(backbone)} courses) · corrections applied: {n_corr}")
    for note in corr_notes:
        print(f"  🔧 {note}")
    n_corrob = 0
    for i, (az, dist, raw) in enumerate(ring):
        srcs = agree[i] if i < len(agree) else set()
        if raw.startswith("[operator]"):
            mark = "🔧 operator"
        elif len(srcs) >= 2:
            mark = f"✔ corroborated×{len(srcs)}"; n_corrob += 1
        else:
            mark = "○ single-source"
        print(f"  {i+1:>3}. {_az_to_call(az, dist):<38} {mark}")
    for pos, bc, src, oc in conflicts:
        print(f"  ✖ CONFLICT at pos {pos}: backbone says {_az_to_call(bc[0], bc[1])} "
              f"but {src} says {_az_to_call(oc[0], oc[1])} — REVIEW")
    for src, c in extras[:10]:
        print(f"  ➕ extra course in {src} (not in backbone): {_az_to_call(c[0], c[1])} — REVIEW")

    print(f"\nring: {a.get('calls')} courses · computed area {computed_ha or 0:.3f} ha · "
          f"closure {a.get('closure_error_m') or 0:.1f} m")
    affs = affirmations(cur, title_no, sources, computed_ha)
    print("affirmations (computed vs independent sources):")
    for name, val, ok in affs:
        tag = "—" if ok is None else ("✅ affirms" if ok else "❌ disagrees")
        unit = "corners" if "corner" in name else "ha"
        print(f"  {name:<42} {val:>10} {unit:<8} {tag}")

    doubt = len(conflicts) + len(extras) + sum(1 for s in agree if len(s) < 2)
    closure = a.get("closure_error_m")
    area_affirmed = any(ok for _, _, ok in affs if ok is not None)
    if write:
        if closure is None or closure > CLOSURE_WRITE_M:
            print(f"\nNOT WRITTEN: closure {closure}m > {CLOSURE_WRITE_M}m gate — "
                  f"resolve the {doubt} flagged course(s) first (review/correct).")
        elif not area_affirmed:
            print("\nNOT WRITTEN: ring closes but NO independent source affirms the computed "
                  "area — a well-closed wrong polygon is still wrong. Resolve the review list "
                  "or record the correct stated area first.")
        else:
            bdoc = int(backbone_src.split("#")[0])
            cur.execute("DELETE FROM parcels WHERE title_no=%s", (title_no,))
            P.upsert_parcel(matter, title_no, calls_text, bdoc, None)
            prov = "operator" if n_corr else ("inferred_corroborated"
                    if n_corrob >= len(ring) * 0.6 else "inferred_strong")
            cur.execute("UPDATE parcels SET provenance_level=%s WHERE title_no=%s", (prov, title_no))
            print(f"\nWROTE consensus parcel (provenance={prov}, area-affirmed, "
                  f"closure {closure:.1f}m).")
    else:
        print(f"\n(dry-run · {doubt} course(s) need review — `review` lists them, "
              f"`correct` fixes them with operator provenance)")
    cur.close(); conn.close()


def review(title_no, matter):
    conn = _conn(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT source_doc_id, seg, idx, azimuth_deg, distance_m, raw_call "
                "FROM parcel_courses WHERE title_no=%s ORDER BY source_doc_id, seg, idx", (title_no,))
    rows = cur.fetchall()
    if not rows:
        print(f"No stored courses for {title_no} — run `build` first."); return
    print(f"=== RAW COURSE ASSERTIONS — {title_no} (verify against the actual scans) ===")
    last = None
    for r in rows:
        key = (r["source_doc_id"], r["seg"])
        if key != last:
            print(f"\n-- doc {r['source_doc_id']} seg {r['seg']} "
                  f"(open scan: /ops/map has no doc view; use /files or Drive) --")
            last = key
        print(f"  {r['idx']:>3}. {_az_to_call(r['azimuth_deg'], r['distance_m']):<38} raw: {r['raw_call'][:60]}")
    print("\nTo correct: geometry_consensus.py correct --title T-X --pos N "
          "--action replace|insert|delete --bearing \"N. 18 deg 34' W.\" --distance 240.90 --reason '...'")
    cur.close(); conn.close()


def correct(title_no, pos, action, bearing, distance, reason, by):
    az = dist = None
    if action != "delete":
        parsed = list(sg.parse_calls(f"{bearing}, {distance:.2f} m"))
        if not parsed:
            print(f"Could not parse bearing {bearing!r} — use the form \"N. 18 deg 34' W.\""); sys.exit(1)
        az, dist = parsed[0]
    conn = _conn(); cur = conn.cursor()
    cur.execute(
        "INSERT INTO parcel_course_corrections (title_no, position, action, azimuth_deg, "
        "distance_m, raw_call, reason, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (title_no, position, action) DO UPDATE SET azimuth_deg=EXCLUDED.azimuth_deg, "
        "distance_m=EXCLUDED.distance_m, raw_call=EXCLUDED.raw_call, reason=EXCLUDED.reason",
        (title_no, pos, action, az, dist, bearing if action != "delete" else None, reason, by))
    cur.close(); conn.close()
    print(f"Recorded operator correction: {title_no} pos {pos} {action} "
          f"{bearing or ''} {distance or ''} — rerun `build` to see the effect.")


def main():
    ap = argparse.ArgumentParser(description="Multi-source parcel-geometry consensus")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--title", required=True)
    b.add_argument("--matter", default="MWK-001"); b.add_argument("--write", action="store_true")
    r = sub.add_parser("review"); r.add_argument("--title", required=True)
    r.add_argument("--matter", default="MWK-001")
    c = sub.add_parser("correct"); c.add_argument("--title", required=True)
    c.add_argument("--pos", type=int, required=True)
    c.add_argument("--action", choices=["replace", "insert", "delete"], default="replace")
    c.add_argument("--bearing"); c.add_argument("--distance", type=float)
    c.add_argument("--reason", required=True); c.add_argument("--by", default="jonathan")
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.title, a.matter, write=a.write)
    elif a.cmd == "review":
        review(a.title, a.matter)
    else:
        if a.action != "delete" and (not a.bearing or a.distance is None):
            ap.error("--bearing and --distance required unless --action delete")
        correct(a.title, a.pos, a.action, a.bearing, a.distance, a.reason, a.by)


if __name__ == "__main__":
    main()
