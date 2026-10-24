#!/usr/bin/env python3
"""ring_tools.py <courses.json> [KEY ...] — closure/area check + diagnosis for transcribed title rings.
For each key: prints closure and area vs stated. If closure > 1 m it also lists single-course
fixes (one distance solved along its own bearing, or one quadrant letter flipped) that close the
ring AND hit the stated area. A fix is only a CANDIDATE: accept it only if the scan or another
certified title corroborates it, and record it under "corrections"."""
import json, math, sys
def az(ns, d, m, ew):
    a = d + m / 60.0
    return {('N','E'): a, ('S','E'): 180 - a, ('S','W'): 180 + a, ('N','W'): 360 - a}[(ns, ew)]
def ring(C):
    x = y = 0.0; pts = [(0.0, 0.0)]
    for ns, d, m, ew, dist in C:
        r = math.radians(az(ns, d, m, ew)); x += dist * math.sin(r); y += dist * math.cos(r); pts.append((x, y))
    A = 0.5 * abs(sum(pts[i][0]*pts[i+1][1] - pts[i+1][0]*pts[i][1] for i in range(len(pts)-1)))
    return pts, math.hypot(x, y), A
J = json.load(open(sys.argv[1])); keys = sys.argv[2:] or [k for k in J if not k.startswith('_')]
for k in keys:
    v = J[k]; C = v['courses']; S = v['stated_area']
    pts, c, A = ring(C)
    print(f"{k} {v.get('lot','')}: {len(C)} courses closure={c:.3f} m area={A:,.1f} vs {S:,} ({100*(A-S)/S:+.2f}%)")
    if c <= 1.0: continue
    ex, ny = pts[-1]; cands = []
    for i, (ns, d, m, ew, dist) in enumerate(C):
        r = math.radians(az(ns, d, m, ew)); t = -(ex*math.sin(r) + ny*math.cos(r))
        T = [list(x) for x in C]; T[i][4] = dist + t; _, cc, AA = ring(T)
        if cc < 1 and T[i][4] > 0: cands.append((abs(AA-S)/S, cc, f"course {i+1}: distance {dist} -> {dist+t:.2f}"))
        for alt in [('S' if ns == 'N' else 'N', ew), (ns, 'W' if ew == 'E' else 'E')]:
            T = [list(x) for x in C]; T[i][0], T[i][3] = alt; _, cc, AA = ring(T)
            if cc < 1: cands.append((abs(AA-S)/S, cc, f"course {i+1}: {ns}{d}-{m}{ew} -> {alt[0]}{d}-{m}{alt[1]}"))
    for a, cc, s in sorted(cands)[:6]: print(f"   candidate: {s}  (closure {cc:.2f} m, area off {100*a:.2f}%)")
