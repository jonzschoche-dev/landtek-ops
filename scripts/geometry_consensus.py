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
        "WHERE extracted_text ~* '[NSns][.[:space:]]?[0-9]{1,3} ?(deg|dog|d|°)' "
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
    # Title-level wipe first: a doc that USED to assert courses for this title but no
    # longer does (re-OCR'd text, reattribution, ring shrank <3 courses) must not leave
    # stale assertion rows behind — bundle() reads the persisted rows and must mirror
    # what live extraction sees.
    cur.execute("DELETE FROM parcel_courses WHERE title_no=%s", (title_no,))
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

CLUSTER_RATIO = 0.4   # min SequenceMatcher ratio for two segments to be the same lot


def _lot_label(i):
    """0→A … 25→Z, 26→AA … — corrections/proposals key on this label, so it must stay a
    clean letter code no matter how many clusters garbled OCR produces."""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def cluster_segments(sources):
    """Group segments into LOT clusters by course-sequence similarity BEFORE consensus.
    A title's certified copies carry several distinct lots; aligning them all to one
    backbone manufactures false conflicts (the T-4497 lesson: 684/348/382 agree with each
    other yet 'conflicted' with 562's different-lot ring). Greedy: longest segment seeds a
    cluster; every other segment joins the first cluster it matches at >= CLUSTER_RATIO.

    DETERMINISM: durable rows (corrections, proposals) key on the lot label, so ordering
    is totally ordered by (-len, doc, seg) — never dict/SQL arrival order. Label stability
    across future INGESTS is still not guaranteed, which is why every correction also
    carries expected_call, verified at apply time (see apply_corrections)."""
    flat = [(doc, seg, courses) for doc, segs in sources.items() for seg, courses in segs.items()]
    flat.sort(key=lambda x: (-len(x[2]), x[0], x[1]))
    clusters = []
    for doc, seg, courses in flat:
        toks = [_tok(c) for c in courses]
        placed = False
        for cl in clusters:
            rep = [_tok(c) for c in cl[0][2]]
            if difflib.SequenceMatcher(a=rep, b=toks, autojunk=False).ratio() >= CLUSTER_RATIO:
                cl.append((doc, seg, courses)); placed = True; break
        if not placed:
            clusters.append([(doc, seg, courses)])
    clusters.sort(key=lambda cl: (-len(cl[0][2]), cl[0][0], cl[0][1]))
    return clusters


def align_cluster(cluster):
    """Consensus within ONE lot cluster. Corroboration counts DISTINCT DOCS only — a doc's
    duplicate internal copy of the same description cannot self-corroborate.
    Returns (backbone_src, backbone, agree_docsets, extras, conflicts)."""
    bdoc, bseg, backbone = cluster[0]
    agree = [{bdoc} for _ in backbone]
    conflicts, extras = [], []
    for doc, seg, courses in cluster[1:]:
        src = f"{doc}#{seg}"
        smt = difflib.SequenceMatcher(a=[_tok(c) for c in backbone],
                                      b=[_tok(c) for c in courses], autojunk=False)
        for op, a1, a2, b1, b2 in smt.get_opcodes():
            if op == "equal":
                for k in range(a2 - a1):
                    agree[a1 + k].add(doc)
            elif op == "replace":
                for k in range(max(a2 - a1, b2 - b1)):
                    ai, bi = a1 + k, b1 + k
                    if ai < a2 and bi < b2:
                        if _near(backbone[ai], courses[bi]):
                            agree[ai].add(doc)          # near-agreement within tolerance
                        else:
                            conflicts.append((ai + 1, backbone[ai], src, courses[bi]))
                    elif bi < b2:
                        extras.append((src, courses[bi]))
            elif op == "insert":
                for k in range(b1, b2):
                    extras.append((src, courses[k]))
    return f"{bdoc}#{bseg}", backbone, agree, extras, conflicts


def apply_corrections(cur, title_no, ring, lot="A"):
    """Apply operator corrections to one lot's consensus ring.

    Returns (ring, n_applied, notes, idx_map) where idx_map[i] is the index of ring[i]
    in the ORIGINAL (uncorrected) backbone, or None for operator-inserted courses.
    Callers must look up per-course corroboration via idx_map — insert/delete
    corrections shift positions, and indexing agree[] with the corrected index would
    pin corroboration badges on the wrong courses."""
    cur.execute("SELECT position, action, azimuth_deg, distance_m, raw_call, reason, "
                "expected_call FROM parcel_course_corrections WHERE title_no=%s AND lot=%s "
                "ORDER BY position", (title_no, lot))
    n, notes = 0, []
    idx_map = list(range(len(ring)))
    for pos, action, az, dist, raw, reason, expected in cur.fetchall():
        i = pos - 1
        # TARGET VERIFICATION (the anti-misapply guard): lot labels/positions can shift
        # when new source docs reshuffle clusters. If the correction recorded what course
        # it was written against (expected_call), require the course NOW at that position
        # to match within tolerance — else SKIP LOUDLY. An operator-provenance value
        # landing on the wrong course would silently corrupt the ring.
        if expected and action in ("replace", "delete") and 0 <= i < len(ring):
            exp = list(sg.parse_calls(expected))
            if exp and not _near((exp[0][0], exp[0][1], ""), ring[i]):
                notes.append(f"pos {pos} {action} SKIPPED: target moved — correction expects "
                             f"'{expected}' but ring has '{_az_to_call(ring[i][0], ring[i][1])}' "
                             f"(re-review at /ops/map/consensus)")
                continue
        if action == "replace" and 0 <= i < len(ring):
            ring[i] = (az, dist, f"[operator] {raw or _az_to_call(az, dist)}")
        elif action == "insert" and 0 <= i <= len(ring):
            ring.insert(i, (az, dist, f"[operator] {raw or _az_to_call(az, dist)}"))
            idx_map.insert(i, None)
        elif action == "delete" and 0 <= i < len(ring):
            ring.pop(i); idx_map.pop(i)
        else:
            notes.append(f"correction pos {pos} ({action}) out of range — skipped"); continue
        n += 1
        notes.append(f"pos {pos} {action}: {reason}")
    return ring, n, notes, idx_map


# ---------------------------------------------------------------- affirmation

def affirmations(cur, title_no, cluster, computed_ha):
    """Triangulate a LOT's computed area against every independent stated source.

    `cluster` is [(doc_id, seg, courses)] — THIS lot's segments only. Each source's
    stated area is read from that doc's OWN SEGMENT text ("containing an area of …"),
    not the doc's first figure: a multi-lot certified copy states several areas, and
    judging lot B against lot A's figure both blocks legitimate lots forever and can
    falsely affirm a wrong ring. The whole-title register row stays as an informative
    comparator (it will only affirm when the lot IS the whole title)."""
    out = []
    cur.execute("SELECT area_sqm, provenance_notes FROM titles WHERE tct_number=%s", (title_no,))
    r = cur.fetchone()
    if r and r["area_sqm"]:
        ha = float(r["area_sqm"]) / 10000.0
        out.append(("titles register" + (" (operator-asserted)" if "operator" in (r["provenance_notes"] or "") else ""),
                    ha, computed_ha and abs(computed_ha - ha) / ha <= 0.05))
    seen_docs = set()
    for doc_id, seg, _courses in cluster:
        cur.execute("SELECT extracted_text FROM documents WHERE id=%s", (doc_id,))
        text = (cur.fetchone() or {}).get("extracted_text") or ""
        segs = SP._segments(text)
        seg_text = ""
        for sno, stext in segs:
            if (sno or 1) == seg:
                seg_text = stext; break
        m = SP._AREA_TXT.search(seg_text)
        if m:
            try:
                ha = float(m.group(1).replace(",", "")) / 10000.0
                out.append((f"doc {doc_id}#{seg} stated area", ha,
                            computed_ha and abs(computed_ha - ha) / ha <= 0.05))
            except ValueError:
                pass
        if doc_id not in seen_docs:
            seen_docs.add(doc_id)
            cm = re.search(r"\(([0-9]{1,3})\s*corners?\)", text, re.I)
            if cm:
                out.append((f"doc {doc_id} corner count", int(cm.group(1)), None))
    return out


def corroboration(cur, title_no, matter=None):
    """How strongly the corpus backs the REGISTERED area itself (independent of the ring):
    (1) count every doc that carries both the title number and the literal area figure —
        'the 13.9 ha is on multiple maps' made mechanical;
    (2) subdivision arithmetic — the derivative titles' areas must sum toward (never past)
        the mother title's area. Returns printable lines.

    `matter` scopes the corpus scan (A5/A9): the client-served bundle passes the title's
    matter so no other client's doc ids or figures ever enter the tally — and the scan
    stops being a full-table regex on every request."""
    lines = []
    cur.execute("SELECT area_sqm FROM titles WHERE tct_number=%s", (title_no,))
    r = cur.fetchone()
    parent_sqm = float(r["area_sqm"]) if r and r["area_sqm"] else None
    digits = re.sub(r"[^0-9]", "", title_no)[-4:]
    # Consensus of what the DOCUMENTS state (not what the register says): tally every area
    # figure asserted by docs that mention this title; the mode is the corpus's answer.
    if matter:
        cur.execute("SELECT id, extracted_text FROM documents WHERE extracted_text ~ %s "
                    "AND (case_file ILIKE %s OR matter_code ILIKE %s)",
                    (digits, f"%{matter}%", f"%{matter}%"))
    else:
        cur.execute("SELECT id, extracted_text FROM documents WHERE extracted_text ~ %s", (digits,))
    votes = {}
    fig = re.compile(r"([0-9][0-9,\.]{2,10})\s*\)?\s*(?:SQ\.?\s*M(?:TS|ETERS)?\b|square\s*met)", re.I)
    for d in cur.fetchall():
        seen = set()
        for m in fig.finditer(d["extracted_text"] or ""):
            try:
                v = int(round(float(m.group(1).replace(",", ""))))
            except ValueError:
                continue
            if 100 <= v <= 5_000_000 and v not in seen:
                seen.add(v)
                votes.setdefault(v, set()).add(d["id"])
    if votes:
        top = sorted(votes.items(), key=lambda kv: -len(kv[1]))[:3]
        for v, ids in top:
            mark = ""
            if parent_sqm:
                mark = (" ✅ register matches" if abs(v - parent_sqm) / parent_sqm <= 0.005
                        else f" (register says {parent_sqm:,.0f})")
            lines.append(f"figure {v:,} sqm ({v/10000:.4f} ha) stated by {len(ids)} doc(s) "
                         f"{sorted(ids)[:10]}{'…' if len(ids) > 10 else ''}{mark}")
    cur.execute(
        "SELECT count(*) AS total, count(t.area_sqm) AS with_area, "
        "coalesce(sum(t.area_sqm),0) AS sum_sqm "
        "FROM title_chain tc LEFT JOIN titles t ON t.tct_number = tc.child_title "
        "WHERE tc.parent_title ~ %s", (r"(^|[^0-9])" + digits + r"($|[^0-9])",))
    s = cur.fetchone()
    if s and s["total"]:
        sum_ha = float(s["sum_sqm"]) / 10000.0
        line = (f"subdivision arithmetic: {s['with_area']}/{s['total']} derivative titles "
                f"have areas, summing {sum_ha:.3f} ha")
        if parent_sqm:
            pct = 100 * float(s["sum_sqm"]) / parent_sqm
            if float(s["sum_sqm"]) > parent_sqm * 1.05:
                line += f" = {pct:.0f}% of parent ❌ CHILDREN EXCEED PARENT — review chain/areas"
            else:
                line += (f" = {pct:.0f}% of parent ✅ consistent"
                         + (" (partial — missing child areas)" if s["with_area"] < s["total"] else " (complete)"))
        lines.append(line)
    return lines


def load_courses(cur, title_no, client_code=None):
    """Rebuild the per-source course map from parcel_courses (the persisted assertions).
    This is the READ path for rendering surfaces — no corpus re-scan, no re-extraction.
    `client_code` (client-facing calls) filters by _client_of(matter_code): TCT numbers
    repeat across Registries of Deeds, so a bare title-string match could merge another
    client's assertions into this client's sheet (A5/A9)."""
    if client_code:
        cur.execute("SELECT source_doc_id, seg, idx, azimuth_deg, distance_m, raw_call "
                    "FROM parcel_courses WHERE title_no=%s AND _client_of(matter_code)=%s "
                    "ORDER BY source_doc_id, seg, idx", (title_no, client_code))
    else:
        cur.execute("SELECT source_doc_id, seg, idx, azimuth_deg, distance_m, raw_call "
                    "FROM parcel_courses WHERE title_no=%s ORDER BY source_doc_id, seg, idx",
                    (title_no,))
    sources = {}
    for r in cur.fetchall():
        sources.setdefault(r["source_doc_id"], {}).setdefault(r["seg"], []).append(
            (r["azimuth_deg"], r["distance_m"], r["raw_call"] or ""))
    return sources


def bundle(title_no, matter=None, client_code=None):
    """JSON-safe consensus bundle for the client map panel + ops console. Read-only;
    mirrors build()'s clustering / corrections / affirmation math exactly, so what a
    client sees IS what the write-gate evaluates. Every course carries its status
    (corroborated / single / operator) and the verbatim raw_call excerpt per source doc —
    the full source stack behind every line on the screen."""
    conn = _conn(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    sources = load_courses(cur, title_no, client_code=client_code)
    out = {"title_no": title_no, "ok": bool(sources), "lots": [], "corroboration": []}
    if not sources:
        cur.close(); conn.close(); return out
    if matter is None:
        cur.execute("SELECT matter_code FROM parcel_courses WHERE title_no=%s "
                    "AND matter_code IS NOT NULL ORDER BY matter_code LIMIT 1", (title_no,))
        r = cur.fetchone()
        matter = r["matter_code"] if r else None
    clusters = cluster_segments(sources)
    for ci, cluster in enumerate(clusters):
        lot = _lot_label(ci)
        cluster_docs = sorted({doc for doc, _, _ in cluster})
        backbone_src, backbone, agree, extras, conflicts = align_cluster(cluster)
        ring, n_corr, _notes, idx_map = apply_corrections(cur, title_no, list(backbone), lot)
        calls_text = "\n".join(_az_to_call(az, d) for az, d, _ in ring)
        a = sg.analyze(calls_text)
        computed_ha = a.get("area_ha")
        courses = []
        for i, (az, dist, raw) in enumerate(ring):
            orig = idx_map[i] if i < len(idx_map) else None
            docs_backing = sorted(agree[orig]) if orig is not None and orig < len(agree) else []
            if raw.startswith("[operator]"):
                status = "operator"
            elif len(docs_backing) >= 2:
                status = "corroborated"
            else:
                status = "single"
            raws = {}
            for doc, _seg, dcourses in cluster:
                for c in dcourses:
                    if _near((az, dist, ""), c):
                        raws[str(doc)] = (c[2] or "").strip()[:220]
                        break
            courses.append({"pos": i + 1, "call": _az_to_call(az, dist),
                            "azimuth": round(az, 4), "distance_m": round(dist, 2),
                            "status": status, "docs": docs_backing, "raws": raws})
        affs = affirmations(cur, title_no, cluster, computed_ha)
        closure = a.get("closure_error_m")
        out["lots"].append({
            "lot": lot, "backbone": backbone_src, "docs": cluster_docs,
            "segments": [f"{doc}#{seg}" for doc, seg, _ in cluster],
            "courses": courses,
            "conflicts": [{"pos": p, "backbone_call": _az_to_call(bc[0], bc[1]),
                           "src": src, "src_call": _az_to_call(oc[0], oc[1]),
                           "src_raw": (oc[2] or "").strip()[:220]}
                          for p, bc, src, oc in conflicts],
            "extras": [{"src": src, "call": _az_to_call(c[0], c[1]),
                        "raw": (c[2] or "").strip()[:220]} for src, c in extras[:12]],
            "corrections_applied": n_corr,
            "computed_ha": round(computed_ha, 4) if computed_ha else None,
            "closure_m": round(closure, 1) if closure is not None else None,
            "n_courses": a.get("calls"),
            "affirmations": [{"name": n, "value": v, "ok": ok} for n, v, ok in affs],
        })
    out["corroboration"] = corroboration(cur, title_no, matter=matter)
    cur.execute("SELECT area_sqm FROM titles WHERE tct_number=%s", (title_no,))
    r = cur.fetchone()
    out["register_area_sqm"] = float(r["area_sqm"]) if r and r["area_sqm"] else None
    cur.close(); conn.close()
    return out


# ---------------------------------------------------------------- commands

def build(title_no, matter, write=False):
    conn = _conn(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    sources = extract_sources(cur, title_no, matter)
    if not sources:
        print(f"No corpus source asserts courses for {title_no}."); return
    persist_courses(cur, title_no, matter, sources)
    clusters = cluster_segments(sources)
    print(f"=== CONSENSUS — {title_no} · {len(sources)} source doc(s): {sorted(sources)} · "
          f"{len(clusters)} lot cluster(s) ===")
    # NB: no upfront DELETE — a rebuild whose lots all FAIL the gates must never destroy
    # previously gated-in parcels. Each passing lot replaces only its own row (below).
    total_ha, total_doubt, wrote = 0.0, 0, 0
    wiped = set()   # (title_no, backbone_doc) pairs already replaced THIS run
    for ci, cluster in enumerate(clusters):
        lot = _lot_label(ci)
        cluster_docs = sorted({doc for doc, _, _ in cluster})
        members = ", ".join(f"{doc}#{seg}" for doc, seg, _ in cluster)
        backbone_src, backbone, agree, extras, conflicts = align_cluster(cluster)
        ring = list(backbone)
        ring, n_corr, corr_notes, idx_map = apply_corrections(cur, title_no, ring, lot)
        calls_text = "\n".join(_az_to_call(az, d) for az, d, _ in ring)
        a = sg.analyze(calls_text)
        computed_ha = a.get("area_ha")
        closure = a.get("closure_error_m")

        print(f"\n--- LOT {lot} · segments [{members}] · backbone {backbone_src} ---")
        for note in corr_notes:
            print(f"  🔧 {note}")
        n_corrob = 0
        for i, (az, dist, raw) in enumerate(ring):
            orig = idx_map[i] if i < len(idx_map) else None
            docs_backing = agree[orig] if orig is not None and orig < len(agree) else set()
            if raw.startswith("[operator]"):
                mark = "🔧 operator"
            elif len(docs_backing) >= 2:
                mark = f"✔ corroborated×{len(docs_backing)} docs"; n_corrob += 1
            else:
                mark = "○ single-source"
            print(f"  {i+1:>3}. {_az_to_call(az, dist):<38} {mark}")
        for pos, bc, src, oc in conflicts:
            print(f"  ✖ CONFLICT at pos {pos}: backbone {_az_to_call(bc[0], bc[1])} "
                  f"vs {src} {_az_to_call(oc[0], oc[1])} — REVIEW")
        for src, c in extras[:8]:
            print(f"  ➕ extra in {src}: {_az_to_call(c[0], c[1])} — REVIEW")

        affs = affirmations(cur, title_no, cluster, computed_ha)
        print(f"  ring: {a.get('calls')} courses · {computed_ha or 0:.4f} ha · "
              f"closure {closure if closure is not None else float('nan'):.1f} m")
        for name, val, ok in affs:
            tag = "—" if ok is None else ("✅ affirms" if ok else "❌ disagrees")
            unit = "corners" if "corner" in name else "ha"
            print(f"    {name:<40} {val:>10} {unit:<8} {tag}")

        doubt = len(conflicts) + len(extras) + sum(1 for s in agree if len(s) < 2)
        total_doubt += doubt
        if computed_ha:
            total_ha += computed_ha
        area_affirmed = any(ok for _, _, ok in affs if ok is not None)
        if write:
            if closure is None or closure > CLOSURE_WRITE_M:
                print(f"  LOT {lot} NOT WRITTEN: closure gate ({closure} m > {CLOSURE_WRITE_M} m) "
                      f"— {doubt} course(s) to review/correct.")
            elif not area_affirmed:
                print(f"  LOT {lot} NOT WRITTEN: closes but no independent source affirms the "
                      f"area — a well-closed wrong polygon is still wrong.")
            else:
                bdoc = int(backbone_src.split("#")[0])
                # Replace only THIS lot's prior row; guard so two lots sharing a backbone
                # doc don't wipe each other's just-written rows in the same run.
                if (title_no, bdoc) not in wiped:
                    cur.execute("DELETE FROM parcels WHERE title_no=%s AND source_doc_id=%s",
                                (title_no, bdoc))
                    wiped.add((title_no, bdoc))
                res = P.upsert_parcel(matter, title_no, calls_text, bdoc, None)
                pid = res.get("parcel_id") if isinstance(res, dict) else None
                if not pid:
                    print(f"  LOT {lot} NOT WRITTEN: upsert_parcel declined "
                          f"({(res or {}).get('reason', 'unknown')}).")
                else:
                    prov = "operator" if n_corr else ("inferred_corroborated"
                            if n_corrob >= len(ring) * 0.6 else "inferred_strong")
                    cur.execute("UPDATE parcels SET provenance_level=%s WHERE id=%s", (prov, pid))
                    wrote += 1
                    print(f"  LOT {lot} WROTE parcel id={pid} (provenance={prov}, "
                          f"area-affirmed, closure {closure:.1f} m).")

    print("\nstated-area corroboration (how strongly the corpus backs the register):")
    for line in corroboration(cur, title_no, matter=matter):
        print(f"  {line}")
    cur.execute("SELECT area_sqm FROM titles WHERE tct_number=%s", (title_no,))
    r = cur.fetchone()
    if r and r["area_sqm"] and total_ha:
        pct = 100 * total_ha * 10000 / float(r["area_sqm"])
        print(f"  lot rings sum {total_ha:.4f} ha = {pct:.0f}% of the registered "
              f"{float(r['area_sqm'])/10000:.4f} ha "
              + ("✅ consistent (partial coverage)" if pct <= 105 else "❌ EXCEEDS the title — review"))
    if write:
        print(f"\n{wrote}/{len(clusters)} lot(s) written · {total_doubt} course(s) still flagged.")
    else:
        print(f"\n(dry-run · {total_doubt} course(s) flagged for review across {len(clusters)} lot(s) — "
              f"`correct --lot X --pos N` fixes with operator provenance)")
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


def correct(title_no, pos, action, bearing, distance, reason, by, lot="A"):
    az = dist = None
    if action != "delete":
        parsed = list(sg.parse_calls(f"{bearing}, {distance:.2f} m"))
        if not parsed:
            print(f"Could not parse bearing {bearing!r} — use the form \"N. 18 deg 34' W.\""); sys.exit(1)
        az, dist = parsed[0]
    conn = _conn(); cur = conn.cursor()
    cur.execute(
        "INSERT INTO parcel_course_corrections (title_no, lot, position, action, azimuth_deg, "
        "distance_m, raw_call, reason, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (title_no, lot, position, action) DO UPDATE SET azimuth_deg=EXCLUDED.azimuth_deg, "
        "distance_m=EXCLUDED.distance_m, raw_call=EXCLUDED.raw_call, reason=EXCLUDED.reason",
        (title_no, lot, pos, action, az, dist, bearing if action != "delete" else None, reason, by))
    cur.close(); conn.close()
    print(f"Recorded operator correction: {title_no} LOT {lot} pos {pos} {action} "
          f"{bearing or ''} {distance or ''} — rerun `build` to see the effect.")


def main():
    ap = argparse.ArgumentParser(description="Multi-source parcel-geometry consensus")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--title", required=True)
    b.add_argument("--matter", default="MWK-001"); b.add_argument("--write", action="store_true")
    r = sub.add_parser("review"); r.add_argument("--title", required=True)
    r.add_argument("--matter", default="MWK-001")
    c = sub.add_parser("correct"); c.add_argument("--title", required=True)
    c.add_argument("--lot", default="A", help="lot cluster letter from the build report")
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
        correct(a.title, a.pos, a.action, a.bearing, a.distance, a.reason, a.by, lot=a.lot)


if __name__ == "__main__":
    main()
