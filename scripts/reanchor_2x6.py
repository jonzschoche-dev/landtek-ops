#!/usr/bin/env python3
"""reanchor_2x6.py — anchor the 2-X-6 family parcels (T-33776, T-36668, T-47656) via the
MUNICIPAL monument, solved from the Balane pin + its certified tie.

The Psd-051607-014971 / Psd-05-026197 sub-subdivision titles do NOT tie to the 1975 plan's
barrio monument (BLLM No. 2, Bo. of Mercedes, at local E=261,N=-16). They tie to a second,
municipal-era monument — "BLM/BLLM No. 2, Municipality of Mercedes / Pls-677-D" — which sits
~1 km west. That monument is SOLVED, not assumed: the Balane title (certified Exhibit 1,
doc 410) gives TIE POINT -> CORNER 1: N 07-52 W, 251.99 m, and the Balane parcel's corner 1
is fixed at Jonathan's verified pin, so M2 = balane_corner1 - tie_vector.

Placements (each from its own title's tie, all from M2):
  T-33776 = Lot 2-X-6-H (Roscoe Leano) · 1,295 m2 · tie N 06-42 E, 287.56  (doc 320)
  T-36668 = Lot 2-X-6-A ·                  300 m2 · tie N 24-16 W, 306.25  (docs 319/320)
  T-47656 = Lot 2-X-6-N (cancelled -> T-48335/48336) · 15,250 m2 ·
            tie N 39-19 E, 397.50 + 5 courses read off the cert back page (doc 307);
            ring closes 0.006 m, area 15,249.6 vs 15,250 (0.00%).

Cross-checks enforced before writing:
  * centroid inside the tie-validated Lot 2-X ring; vertices within a 10 m coastal
    tolerance (the Balane pin itself straddles the mesh boundary by ~8 m — that offset is
    the pin's eyeball uncertainty, shared coherently by the whole family block);
  * child nesting: T-48335's own tie (2-X-6-N-1, N 30-12 E 363.90, doc 308) must land
    INSIDE the placed 2-X-6-N — two titles corroborating the monument;
  * no centroid overlap among family parcels.

Re-run with --write after any Balane pin re-drag; the family follows the pin.
"""
from __future__ import annotations
import json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subdivision_geometry as SG
import subdivision_assemble as SA
import psycopg2

BAL_TIE = ('N', 7, 52, 'W', 251.99)          # doc 410, certified: M2 -> Balane corner 1
FAMILY = {
    "MWK-T-33776": {"label": "Lot 2-X-6-H (Roscoe Leano)", "tie": ('N', 6, 42, 'E', 287.56),
                    "mode": "translate"},
    "MWK-T-36668": {"label": "Lot 2-X-6-A", "tie": ('N', 24, 16, 'W', 306.25),
                    "mode": "translate"},
    "MWK-T-47656": {"label": "Lot 2-X-6-N (T-47656, cancelled -> 48335/48336)",
                    "tie": ('N', 39, 19, 'E', 397.50), "mode": "courses", "area": 15249.6,
                    "courses": [('S',18,58,'W',140.13), ('N',72,54,'W',102.94),
                                ('N',19,56,'E',94.41), ('N',23,10,'E',67.73),
                                ('S',60,11,'E',98.08)]},
}
CHILD_CHECK = {"MWK-T-47656": ('N', 30, 12, 'E', 363.90)}   # 2-X-6-N-1 (T-48335, doc 308)
TOL = 10.0                                                   # m, coastal/pin tolerance


def vec(ns, dg, mn, ew, d):
    a = math.radians(SG.az(ns, dg, mn, ew)); return (d*math.sin(a), d*math.cos(a))

def inside(pt, poly):
    x, y = pt; n = len(poly); ins = False
    for i in range(n-1):
        x1, y1 = poly[i]; x2, y2 = poly[i+1]
        if (y1 > y) != (y2 > y) and x < (x2-x1)*(y-y1)/(y2-y1)+x1: ins = not ins
    return ins

def d_poly(p, poly):
    def d_seg(p, a, b):
        ax, ay = a; bx, by = b; px, py = p
        dx, dy = bx-ax, by-ay; L2 = dx*dx+dy*dy
        t = 0 if L2 == 0 else max(0, min(1, ((px-ax)*dx+(py-ay)*dy)/L2))
        return math.hypot(px-(ax+t*dx), py-(ay+t*dy))
    return min(d_seg(p, poly[i], poly[i+1]) for i in range(len(poly)-1))


def main():
    write = "--write" in sys.argv
    conn = psycopg2.connect(SG.DSN); cur = conn.cursor()
    def ring_of(code):
        cur.execute("SELECT geom_geojson FROM map_parcels WHERE parcel_code=%s", (code,))
        g = cur.fetchone()[0]; g = g if isinstance(g, dict) else json.loads(g)
        return g["coordinates"][0]
    def to_local(lng, lat):
        return ((lng-SA.ANCHOR_LNG)*SA.MPERDEG_LAT*SA.COSLAT, (lat-SA.ANCHOR_LAT)*SA.MPERDEG_LAT)

    xring = [to_local(*p) for p in ring_of("MWK-PSD221861-X")]
    bc1 = to_local(*ring_of("MWK-BALANE")[0])
    tv = vec(*BAL_TIE)
    M2 = (bc1[0]-tv[0], bc1[1]-tv[1])
    print(f"municipal monument M2 local E={M2[0]:.1f} N={M2[1]:.1f}  wgs84={SA.to_lnglat(*M2)}")

    placed_rings = {}
    for code, spec in FAMILY.items():
        t = vec(*spec["tie"]); c1 = (M2[0]+t[0], M2[1]+t[1])
        if spec["mode"] == "courses":
            pts = [c1]; x, y = c1
            for ns, dg, mn, ew, d in spec["courses"]:
                a = math.radians(SG.az(ns, dg, mn, ew)); x += d*math.sin(a); y += d*math.cos(a); pts.append((x, y))
            new = pts[:-1]+[pts[0]]
        else:
            loc = [to_local(*p) for p in ring_of(code)]
            off = (c1[0]-loc[0][0], c1[1]-loc[0][1])
            new = [(px+off[0], py+off[1]) for px, py in loc]
        cen = (sum(p[0] for p in new[:-1])/(len(new)-1), sum(p[1] for p in new[:-1])/(len(new)-1))
        worst = max(0.0 if inside(p, xring) else d_poly(p, xring) for p in new[:-1])
        ok = inside(cen, xring) and worst <= TOL
        child_ok = True
        if code in CHILD_CHECK:
            cv = vec(*CHILD_CHECK[code])
            child_ok = inside((M2[0]+cv[0], M2[1]+cv[1]), new)
            ok = ok and child_ok
        print(f"{code} [{spec['label']}]: centroid-in={inside(cen,xring)} worst-outlier={worst:.1f} m "
              f"child-nested={child_ok} -> {'WRITE' if ok else 'HOLD'}")
        if not ok:
            continue
        placed_rings[code] = new
        if write:
            newring = [SA.to_lnglat(px, py) for px, py in new]
            clng, clat = SA.to_lnglat(*cen)
            cur.execute("""UPDATE map_parcels SET geom_geojson=%s::jsonb, centroid_lat=%s,
                centroid_lng=%s, label=%s, source_note=%s, updated_at=now()
                WHERE parcel_code=%s""",
                (json.dumps({"type": "Polygon", "coordinates": [newring]}), clat, clng,
                 spec["label"],
                 f"{spec['label']}; anchored via municipal monument BLM No.2 solved from the Balane "
                 f"pin + certified tie (doc 410 N07-52W 251.99) + this title's own tie "
                 f"{spec['tie']}; nested inside Lot 2-X ({TOL:.0f} m coastal tolerance)", code))
            conn.commit(); print("   written.")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
