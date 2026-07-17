#!/usr/bin/env python3
"""Assemble the verified Psd-221861 lots into one georeferenced mesh by shared edges.
All lots are true-north oriented, so assembly is pure TRANSLATION: adjacent lots share a
boundary that appears in both course lists (same length, opposite bearing). Anchor = Lot 2-A
corner-1 at the operator-placed position; propagate outward by BFS over shared edges."""
import math, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subdivision_geometry as SG

MPERDEG_LAT = 111320.0

def anchor():
    """Shared-frame local (0,0) == Lot 2-A corner 1 == the operator-placed position.
    Read live from map_parcels (T-32911) so the whole mesh follows any re-drag of 2-A."""
    import psycopg2
    c = psycopg2.connect(SG.DSN); cur = c.cursor()
    cur.execute("SELECT geom_geojson FROM map_parcels WHERE title_no='T-32911' AND geom_geojson IS NOT NULL LIMIT 1")
    r = cur.fetchone(); cur.close(); c.close()
    if not r:
        return 123.00927043, 14.10934703   # fallback: last known 2-A corner-1
    g = r[0] if isinstance(r[0], dict) else json.loads(r[0])
    lng, lat = g["coordinates"][0][0]      # v1 == corner 1
    return lng, lat

ANCHOR_LNG, ANCHOR_LAT = anchor()
COSLAT = math.cos(math.radians(ANCHOR_LAT))

def local_verts(courses):
    x = y = 0.0; pts = [(0.0, 0.0)]
    for ns, dg, mn, ew, d in courses:
        r = math.radians(SG.az(ns, dg, mn, ew)); x += d*math.sin(r); y += d*math.cos(r); pts.append((x, y))
    return pts[:-1]  # drop closing dup

def edges(verts):
    e = []
    n = len(verts)
    for i in range(n):
        a = verts[i]; b = verts[(i+1) % n]
        dx, dy = b[0]-a[0], b[1]-a[1]
        L = math.hypot(dx, dy); az = math.degrees(math.atan2(dx, dy)) % 360
        e.append({"i": i, "j": (i+1) % n, "L": L, "az": az})
    return e

def to_lnglat(E, N):
    return [round(ANCHOR_LNG + E/(MPERDEG_LAT*COSLAT), 8), round(ANCHOR_LAT + N/MPERDEG_LAT, 8)]

def _pip(pt, poly):
    x, y = pt; inside = False; n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i+1) % n]
        if ((y1 > y) != (y2 > y)) and x < (x2-x1)*(y-y1)/(y2-y1)+x1:
            inside = not inside
    return inside

def _overlap(qa, others, frac=0.04):
    """Interior-AREA overlap by sampling — robust for concave (L-shaped) lots AND for lots that
    merely share an edge or a T-junction (those contribute ~0 interior overlap; a real stacking
    contributes a large fraction). Centroid/edge-crossing tests both misfire on this subdivision's
    concave lots (2-N, 2-X); area sampling doesn't."""
    xs = [p[0] for p in qa]; ys = [p[1] for p in qa]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    n = 22
    interior = []
    for i in range(n):
        for j in range(n):
            px = x0 + (x1-x0)*(i+0.5)/n; py = y0 + (y1-y0)*(j+0.5)/n
            if _pip((px, py), qa):
                interior.append((px, py))
    if not interior:
        return False
    for pb in others:
        hit = sum(1 for p in interior if _pip(p, pb))
        if hit / len(interior) > frac:
            return True
    return False

def assemble():
    res = SG.validate()
    ok = {k: v for k, v in res.items() if v["ok"]}
    lv = {k: local_verts(v["courses"]) for k, v in ok.items()}
    le = {k: edges(lv[k]) for k in ok}
    placed = {"2-A": [tuple(p) for p in lv["2-A"]]}
    frontier = ["2-A"]
    LT, AT = 0.2, 0.6                # tight length / azimuth match tolerance
    edges_used = []
    while frontier:
        P = frontier.pop()
        gPe = edges(placed[P])
        for Q in list(ok):
            if Q in placed:
                continue
            cand = []
            for ep in gPe:
                for eq in le[Q]:
                    if abs(ep["L"]-eq["L"]) <= LT and abs(((ep["az"]-(eq["az"]+180)) % 360 + 180) % 360 - 180) <= AT:
                        gPi = placed[P][ep["i"]]; Qj = lv[Q][eq["j"]]
                        tx, ty = gPi[0]-Qj[0], gPi[1]-Qj[1]
                        cand.append((ep["L"], [(vx+tx, vy+ty) for (vx, vy) in lv[Q]]))
            # accept first candidate placement that does NOT overlap any placed lot
            for L, cverts in sorted(cand, key=lambda c: -c[0]):
                if not _overlap(cverts, [v for k, v in placed.items()]):
                    placed[Q] = cverts; frontier.append(Q); edges_used.append((P, Q, round(L, 2)))
                    break
    return ok, placed, edges_used

def poly_area(verts):
    n = len(verts)
    return abs(sum(verts[i][0]*verts[(i+1) % n][1]-verts[(i+1) % n][0]*verts[i][1] for i in range(n)))/2

def centroid(verts):
    return (sum(v[0] for v in verts)/len(verts), sum(v[1] for v in verts)/len(verts))

def overlaps(pa, pb):
    # cheap test: centroid of one inside the other's bbox AND close centroids -> flag for review
    ca, cb = centroid(pa), centroid(pb)
    d = math.hypot(ca[0]-cb[0], ca[1]-cb[1])
    ra = math.sqrt(poly_area(pa)/math.pi); rb = math.sqrt(poly_area(pb)/math.pi)
    return d < 0.5*(ra+rb)   # centroids closer than sum of "radii"/2 -> likely overlap

def main():
    ok, placed, used = assemble()
    write = "--write" in sys.argv
    print(f"lots verified: {len(ok)}  |  placed by shared-edge assembly: {len(placed)}")
    for a, b, L in used:
        print(f"    {a} -- {b}  (shared edge {L} m)")
    islands = [k for k in ok if k not in placed]
    print(f"not connected to 2-A component: {islands}")
    # overlap sanity
    ks = list(placed)
    ov = [(ks[i], ks[j]) for i in range(len(ks)) for j in range(i+1, len(ks))
          if _overlap(placed[ks[i]], [placed[ks[j]]])]
    print(f"overlap flags (interior-area): {ov if ov else 'none'}")
    xs = [to_lnglat(*v) for verts in placed.values() for v in verts]
    lngs = [p[0] for p in xs]; lats = [p[1] for p in xs]
    print(f"mesh bbox: lng [{min(lngs):.5f},{max(lngs):.5f}] lat [{min(lats):.5f},{max(lats):.5f}]  "
          f"~{(max(lngs)-min(lngs))*107965:.0f}m x {(max(lats)-min(lats))*MPERDEG_LAT:.0f}m")
    feats = []
    for lot, verts in placed.items():
        ring = [to_lnglat(*v) for v in verts]; ring.append(ring[0])
        feats.append({"type": "Feature", "properties": {"lot": lot, "area": ok[lot]["area"]},
                      "geometry": {"type": "Polygon", "coordinates": [ring]}})
    json.dump({"type": "FeatureCollection", "features": feats}, open("/tmp/subdiv_assembled.geojson", "w"))
    print("wrote /tmp/subdiv_assembled.geojson")

    if write:
        import psycopg2
        conn = psycopg2.connect(SG.DSN); conn.autocommit = True; cur = conn.cursor()
        n = 0
        for lot, verts in placed.items():
            if lot == "2-A":
                continue  # already placed as T-32911 (map_parcels id 17)
            ring = [to_lnglat(*v) for v in verts]; ring.append(ring[0])
            cen = centroid(verts); clng, clat = to_lnglat(*cen)
            gj = json.dumps({"type": "Polygon", "coordinates": [ring]})
            code = f"MWK-PSD221861-{lot.replace('2-','')}"
            cur.execute("""INSERT INTO map_parcels
                (parcel_code, client_code, matter_code, title_no, label, geom_geojson,
                 centroid_lat, centroid_lng, area_sqm, stated_area_sqm, accuracy_tier,
                 source_note, status)
                VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,'rough',%s,'draft')
                ON CONFLICT (parcel_code) DO UPDATE SET geom_geojson=EXCLUDED.geom_geojson,
                 centroid_lat=EXCLUDED.centroid_lat, centroid_lng=EXCLUDED.centroid_lng,
                 area_sqm=EXCLUDED.area_sqm, source_note=EXCLUDED.source_note, updated_at=now()""",
                (code, "MWK-001", "MWK-001", f"PSD-221861 Lot {lot}", f"Lot {lot} (Psd-221861)",
                 gj, clat, clng, round(ok[lot]["area"], 1), round(ok[lot]["stated"], 1),
                 f"Psd-221861 plan (doc 287); shape closure {ok[lot]['closure']:.2f}m; "
                 f"assembled by shared-edge from Lot 2-A anchor (relative tier — not survey-georeferenced)"))
            n += 1
        print(f"\nwrote/updated {n} assembled lots into map_parcels (tier=rough).")
        cur.close(); conn.close()

if __name__ == "__main__":
    main()
