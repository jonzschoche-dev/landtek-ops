#!/usr/bin/env python3
"""place_from_courses.py — place vision-transcribed title rings on the map from their own
tie lines, using the municipal monument BLM No. 2 solved exactly as reanchor_2x6.py does
(Balane pin + certified tie, doc 410). Courses come from a JSON file of transcriptions
(e.g. case_work/MWK-001/GIS_2026-10/sp2156_courses.json), never from guessed values.

Gates before a ring is written to map_parcels:
  * the ring closes (< 1 m) and its area is within 1% of the stated area;
  * its centroid lies inside the placed Lot 2-X ring and every vertex is within TOL of it;
  * any declared containment checks pass ("inside": parcel_code or transcribed key whose
    ring must contain this one's centroid; "contains": parcel_code whose vertices must
    fall inside this ring, within TOL).

  python3 place_from_courses.py <courses.json>            # dry run + GeoJSON export
  python3 place_from_courses.py <courses.json> --write    # also update map_parcels
"""
import json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subdivision_geometry as SG
import subdivision_assemble as SA
import psycopg2
from reanchor_2x6 import BAL_TIE, vec, inside, d_poly
import subdivision_place_orphans as SPO

TOL = 3.0   # frames reconciled 2026-10-24 (M1 frame shifted -10.3E/-4.9N onto the Balane-pin frame)


def walk(c1, courses):
    pts = [c1]; x, y = c1
    for ns, dg, mn, ew, d in courses:
        a = math.radians(SG.az(ns, dg, mn, ew)); x += d * math.sin(a); y += d * math.cos(a); pts.append((x, y))
    clos = math.hypot(pts[-1][0] - c1[0], pts[-1][1] - c1[1])
    ring = pts[:-1] + [pts[0]]
    area = 0.5 * abs(sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)))
    return ring, clos, area


def within(ring, other, tol=None):
    """True when every vertex of ring lies inside other or within tol of its boundary (robust for
    concave lots, where a vertex-average point can fall outside the lot itself)."""
    tol = TOL if tol is None else tol
    return bool(other) and max(0.0 if inside(p, other) else d_poly(p, other) for p in ring[:-1]) <= tol


def main():
    path = sys.argv[1]; write = "--write" in sys.argv
    J = {k: v for k, v in json.load(open(path)).items() if not k.startswith("_")}
    conn = psycopg2.connect(SG.DSN); cur = conn.cursor()

    def ring_of(code):
        cur.execute("SELECT geom_geojson FROM map_parcels WHERE parcel_code=%s", (code,))
        r = cur.fetchone()
        if not r or not r[0]:
            return None
        g = r[0] if isinstance(r[0], dict) else json.loads(r[0])
        return [to_local(*p) for p in g["coordinates"][0]]

    def to_local(lng, lat):
        return ((lng - SA.ANCHOR_LNG) * SA.MPERDEG_LAT * SA.COSLAT, (lat - SA.ANCHOR_LAT) * SA.MPERDEG_LAT)

    xring = ring_of("MWK-PSD221861-X")
    bc1 = ring_of("MWK-BALANE")[0]
    tv = vec(*BAL_TIE); M2 = (bc1[0] - tv[0], bc1[1] - tv[1])
    print(f"M2 (BLM No.2, Municipality of Mercedes) local E={M2[0]:.1f} N={M2[1]:.1f} wgs84={SA.to_lnglat(*M2)}")

    B1 = SPO.bllm_local()
    print(f"M1 (BLLM No.2, Bo. of Mercedes, 1975 plan) local E={B1[0]:.1f} N={B1[1]:.1f} wgs84={SA.to_lnglat(*B1)}")
    MON = {"M2": M2, "M1": B1}

    def place(v, mon):
        t = vec(*v["tie"]); m = MON[mon]
        return walk((m[0] + t[0], m[1] + t[1]), v["courses"])[0]

    def in_any(r, codes):
        """every vertex inside (or within TOL of) the UNION of the listed parcels"""
        rings = [x for x in (ring_of(c) for c in codes) if x]
        if not rings:
            return False
        return all(any(inside(p, o) or d_poly(p, o) <= TOL for o in rings) for p in r[:-1])

    placed, feats, used = {}, [], {}
    for key, v in J.items():
        mk = v.get("monument_key", "M2")
        if mk == "auto":
            scores = {}
            for m in ("M2", "M1"):
                r = place(v, m)
                scores[m] = in_any(r, v.get("inside_any", [])) if v.get("inside_any") else within(r, xring)
            print(f"   {key}: monument test {scores}")
            mk = [m for m, ok in scores.items() if ok][0] if sum(scores.values()) == 1 else None
        used[key] = mk
        placed[key] = place(v, mk) if mk else place(v, "M2")
    for key, v in J.items():
        ring = placed[key]; _, clos, area = walk(ring[0], v["courses"])
        cen = (sum(p[0] for p in ring[:-1]) / (len(ring) - 1), sum(p[1] for p in ring[:-1]) / (len(ring) - 1))
        checks = {
            "closes": clos < 1.0,
            "area_1pct": abs(area - v["stated_area"]) / v["stated_area"] < 0.01,
            "in_2X": within(ring, xring),
        }
        checks["monument_unambiguous"] = used[key] is not None
        if v.get("mother_title"):           # T-4497: must CONTAIN Lot 2-X and the 1975 lots, not sit inside 2-X
            checks["in_2X"] = within(xring, ring)
        if v.get("inside_any"):
            checks["inside_any"] = in_any(ring, v["inside_any"])
            checks["in_2X"] = True if used[key] == "M1" and checks["inside_any"] else checks["in_2X"]
        for other in v.get("inside", []):
            o = placed.get(other) or placed.get(other.replace("MWK-", "", 1)) or ring_of(other)
            checks[f"inside:{other}"] = within(ring, o)
        for other in v.get("contains", []):
            o = placed.get(other) or placed.get(other.replace("MWK-", "", 1)) or ring_of(other)
            checks[f"contains:{other}"] = within(o, ring)
        ok = all(checks.values())
        print(f"{key} [{v['lot']}] closure={clos:.3f} m area={area:,.0f}/{v['stated_area']:,} -> "
              + ", ".join(f"{k}={'ok' if c else 'FAIL'}" for k, c in checks.items()) + f" => {'PLACE' if ok else 'HOLD'}")
        lnglat = [list(SA.to_lnglat(px, py)) for px, py in ring]
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [lnglat]},
                      "properties": {"title": key, "lot": v["lot"], "plan": v["plan"], "stated_area": v["stated_area"],
                                     "computed_area": round(area, 1), "closure_m": round(clos, 3), "src_doc": v["src_doc"],
                                     "corrections": len(v.get("corrections", [])), "status": "placed" if ok else "held", "monument": used[key] or "ambiguous",
                                     "accuracy": "rough (position from Balane pin + monument tie; shape survey-exact)"}})
        if ok and write:
            code = "MWK-" + key
            clng, clat = SA.to_lnglat(*cen)
            note = (f"Lot {v['lot']} ({v['plan']}); courses vision-transcribed from doc {v['src_doc']}, closure {clos:.2f} m, "
                    f"area {area:,.0f} vs {v['stated_area']:,}; anchored at monument (M2 = BLM No.2 Municipality, solved from Balane pin + doc 410 tie; M1 = BLLM No.2 Bo. of Mercedes, from Lot 2-A tie) + "
                    f"own tie {v['tie']} from {used[key]}; checks: {', '.join(checks)}"
                    + (f"; {len(v['corrections'])} course correction(s) documented in {os.path.basename(path)}" if v.get("corrections") else ""))
            cur.execute("""INSERT INTO map_parcels (parcel_code, client_code, matter_code, title_no, label,
                geom_geojson, centroid_lat, centroid_lng, area_sqm, stated_area_sqm, accuracy_tier, status,
                source_note, plotted_by, plotted_at)
                VALUES (%s,'MWK-001','MWK-001',%s,%s,%s::jsonb,%s,%s,%s,%s,'rough','plotted',%s,'place_from_courses.py',now())
                ON CONFLICT (parcel_code) DO UPDATE SET geom_geojson=EXCLUDED.geom_geojson,
                centroid_lat=EXCLUDED.centroid_lat, centroid_lng=EXCLUDED.centroid_lng, area_sqm=EXCLUDED.area_sqm,
                stated_area_sqm=EXCLUDED.stated_area_sqm, accuracy_tier='rough', status='plotted', label=EXCLUDED.label,
                source_note=EXCLUDED.source_note, plotted_by=EXCLUDED.plotted_by, plotted_at=now(), updated_at=now()""",
                        (code, key, f"{key} - Lot {v['lot']}", json.dumps({"type": "Polygon", "coordinates": [lnglat]}),
                         clat, clng, area, v["stated_area"], note))
            print(f"   upserted {code}")
    if write:
        conn.commit()
    out = os.path.splitext(path)[0] + "_placed.geojson"
    json.dump({"type": "FeatureCollection", "features": feats}, open(out, "w"), indent=1)
    print("geojson:", out)
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
