#!/usr/bin/env python3
"""survey_geometry.py — turn a Torrens / technical-description metes-and-bounds block
into a closed parcel polygon, its computed area, and a closure error. Pure Python,
NO API call — the creditless core engine of the geospatial pillar (MASTER_PLAN §4A).

A "call" reads like:   N. 86 deg 23' E., 269.35 m    /    S 11°38'E 72.96 m
We parse the bearing (quadrant N/S + degrees + minutes + E/W) and distance (meters),
convert each to a planar vector (azimuth measured clockwise from North), walk the
boundary from a local origin (0,0), then compute:

  - area_sqm via the shoelace formula  → CROSS-CHECK against the title's stated hectares
  - closure_error_m = gap from the last vertex back to the start (a survey-quality signal)

Coordinates are LOCAL/relative (meters). Absolute georeferencing (PRS92 ↔ WGS84) needs a
tie point and is layered on later — but the SHAPE and AREA are exact from the calls alone,
and the area cross-check alone validates that our extracted geometry matches the title.

Usage:
  echo "<technical description text>" | python3 survey_geometry.py
  python3 survey_geometry.py "N. 86 deg 23' E., 269.35 m  S. 11 deg 38' E., 72.96 m ..."
"""
from __future__ import annotations
import math
import re

# Bearing+distance call: [NS] <deg> (deg|°) <min>' [EW] (.,) <distance> (m)
# Tolerant of OCR noise: optional periods, deg/°/d, optional minutes, m/meters/M.
_CALL = re.compile(
    r"([NSns])\.?\s*([0-9]{1,3})\s*(?:deg|°|d)\.?\s*([0-9]{1,2})?\s*['′’]?\s*"
    r"([EWew])\.?\s*[.,]?\s*([0-9]{1,4}(?:\.[0-9]+)?)\s*(?:m\b|meters|M\b)"
)


def parse_calls(text: str):
    """Yield (azimuth_deg_clockwise_from_north, distance_m) for each call found."""
    for m in _CALL.finditer(text or ""):
        ns, deg, mins, ew, dist = m.groups()
        ang = float(deg) + (float(mins) / 60.0 if mins else 0.0)
        ns, ew = ns.upper(), ew.upper()
        if ns == "N" and ew == "E":
            az = ang
        elif ns == "S" and ew == "E":
            az = 180.0 - ang
        elif ns == "S" and ew == "W":
            az = 180.0 + ang
        else:  # N..W
            az = 360.0 - ang
        d = float(dist)
        if 0 < d < 100000:  # ignore absurd OCR distances
            yield az % 360.0, d


def boundary(text: str):
    """Walk the calls into (x=East, y=North) vertices from a local origin (0,0)."""
    pts = [(0.0, 0.0)]
    for az, d in parse_calls(text):
        a = math.radians(az)
        x, y = pts[-1]
        pts.append((x + d * math.sin(a), y + d * math.cos(a)))
    return pts


def _shoelace(ring):
    s = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def analyze(text: str):
    pts = boundary(text)
    n = len(pts) - 1  # number of calls (vertices beyond origin)
    if n < 3:
        return {"calls": n, "ok": False, "reason": "need >=3 calls for a polygon"}
    ring = pts + [pts[0]]
    closure = math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
    perim = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                for i in range(len(pts) - 1))
    area = _shoelace(ring)
    return {
        "ok": True,
        "calls": n,
        "area_sqm": round(area, 2),
        "area_ha": round(area / 10000.0, 4),
        "perimeter_m": round(perim, 2),
        "closure_error_m": round(closure, 3),
        "closure_pct_of_perimeter": round(100 * closure / perim, 3) if perim else None,
        "wkt_local": "POLYGON((" + ", ".join(f"{x:.3f} {y:.3f}" for x, y in ring) + "))",
    }


def cross_check(text: str, stated_hectares: float, tol_pct: float = 5.0):
    """Compare computed area to a title's stated hectares. Returns the analysis plus a
    match verdict — the creditless validation that extracted geometry agrees with the title."""
    a = analyze(text)
    if not a.get("ok"):
        return a
    diff_pct = abs(a["area_ha"] - stated_hectares) / stated_hectares * 100 if stated_hectares else None
    a["stated_ha"] = stated_hectares
    a["area_diff_pct"] = round(diff_pct, 2) if diff_pct is not None else None
    a["area_matches"] = (diff_pct is not None and diff_pct <= tol_pct)
    return a


if __name__ == "__main__":
    import sys
    import json
    txt = sys.stdin.read() if not sys.stdin.isatty() else " ".join(sys.argv[1:])
    r = analyze(txt)
    if isinstance(r, dict):
        r.pop("wkt_local", None)  # too long for the CLI summary
    print(json.dumps(r, indent=2))
