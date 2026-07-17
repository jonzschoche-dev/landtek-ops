#!/usr/bin/env python3
"""geometry_solve.py — the truth-finding core: recover MISSING course values from constraints.

A survey ring is over-determined. If the bearings are known and only a few distances are
missing/damaged, the ring still MUST close (Σ course-vectors = 0, in East and North) and, if
known, enclose a stated AREA. Those constraints let the engine COMPUTE the missing distances
rather than read them — and, crucially, VALIDATE the result: a solution that closes but whose
area is wrong proves the *known* inputs are wrong (the case with the T-4497 boundary — a torn
distance column plus a modeling error made the reads enclose 235k m² vs the true 139,132).

  solve_ring(courses, target_area=None)
    courses: [(azimuth_deg_cw_from_N, distance_or_None)]  (None = unknown/damaged)
    -> {ok, courses (completed), area_sqm, closure_m, unknowns_solved, area_match}

Exactly-2 unknowns are solved in closed form from the 2 closure equations; the area (if given)
is the independent check. More unknowns need the fuller network adjustment (multiple lots +
tie lines + shared edges) — this module is the per-ring primitive that engine is built from.
"""
from __future__ import annotations

import math


def solve_ring(courses, target_area=None):
    ke = kn = 0.0
    unk, unit = [], []
    for i, (az, d) in enumerate(courses):
        r = math.radians(az % 360.0)
        se, cn = math.sin(r), math.cos(r)
        if d is None:
            unk.append(i); unit.append((se, cn))
        else:
            ke += d * se; kn += d * cn

    solved = {}
    if len(unk) == 0:
        pass
    elif len(unk) == 1:
        # over-determined: least-squares projection onto the single unknown direction
        a0, b0 = unit[0]
        denom = a0 * a0 + b0 * b0
        solved[unk[0]] = (-(ke * a0 + kn * b0) / denom) if denom else 0.0
    elif len(unk) == 2:
        (a0, b0), (a1, b1) = unit
        det = a0 * b1 - a1 * b0
        if abs(det) < 1e-9:
            return {"ok": False, "reason": "unknown courses are parallel — not solvable by closure"}
        solved[unk[0]] = (-ke * b1 + a1 * kn) / det       # closure: Σ = 0
        solved[unk[1]] = (-a0 * kn + ke * b0) / det
    else:
        return {"ok": False, "reason": f"{len(unk)} unknowns — needs the full network adjustment "
                f"(closure gives only 2 equations; area gives 1 more)"}

    if any(v <= 0 for v in solved.values()):
        return {"ok": False, "reason": "solved a non-positive distance — inputs inconsistent",
                "unknowns_solved": {i + 1: round(v, 2) for i, v in solved.items()}}

    completed = [(az, (solved[i] if i in solved else d)) for i, (az, d) in enumerate(courses)]
    x = y = 0.0; pts = [(0.0, 0.0)]
    for az, d in completed:
        r = math.radians(az % 360.0)
        x += d * math.sin(r); y += d * math.cos(r); pts.append((x, y))
    closure = math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
    s = sum(pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1] for i in range(len(pts) - 1))
    area = abs(s) / 2.0
    match = None if target_area is None else (abs(area - target_area) / target_area <= 0.02)
    return {"ok": True, "courses": completed, "area_sqm": round(area, 1),
            "closure_m": round(closure, 3),
            "unknowns_solved": {i + 1: round(solved[i], 2) for i in solved},
            "area_match": match,
            "area_off_pct": (None if target_area is None else round(abs(area - target_area) / target_area * 100, 2))}


if __name__ == "__main__":
    # demo: a 50m square with two ADJACENT sides "damaged" — recovered from closure alone
    import json
    demo = [(0.0, 50.0), (90.0, 50.0), (180.0, None), (270.0, None)]
    print(json.dumps(solve_ring(demo, target_area=2500), indent=2))
