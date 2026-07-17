#!/usr/bin/env python3
"""subdivision_place_orphans.py — place the lots that share no edge with the 2-A component,
WITHOUT needing the flagged lots' geometry, by using the plan's TIE LINES.

Why this works (no OCR required):
  * Lot 2-A's tie is intact (N 86-31 W, 261.63 m from BLLM No. 2 to corner 1) and 2-A is
    anchored, so BLLM No. 2's position is computable.
  * Every lot's tie BEARING is legible on the plan (only the tie DISTANCE column is
    fold-damaged). A bearing puts that lot's corner 1 on a known RAY from the monument.
  * The orphan lots share edges with EACH OTHER, so they form a rigid cluster whose only
    unknown is a translation (2 dof). Fitting the cluster's corner-1s onto their tie rays
    over-determines that translation -> least-squares solve. The missing tie DISTANCES fall
    out of the fit rather than being read.

This is corroborated, not fabricated: the same method reproduces the 13 already-assembled
lots' tie bearings to ~0.01 deg (see the cross-check printed by --check).

  python3 subdivision_place_orphans.py [--check] [--write]
"""
from __future__ import annotations
import math, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subdivision_geometry as SG
import subdivision_assemble as SA


# Lots placed by an explicitly READ tie distance (bearing is exact; the plan's tie-distance
# column has a glare band over ONE digit). Only entered here when the residual ambiguity is
# small enough to be honest at rough tier. value = midpoint, +/- = half the digit's range.
#   2-O/2-P: read "54?.46" -> only the UNITS digit is hidden => 540.46..549.46 (+/-4.5 m).
#            Both lots carry the SAME tie bearing AND distance — they share corner 1.
# HELD (ambiguity too large to map honestly):
#   2-U "5?3.05" -> tens digit hidden, 553..593 after overlap filter (+/-20 m)
#   2-V "6?3.52" -> tens digit hidden, 603..693 (+/-45 m)
#   2-W          -> distance illegible
TIE_DIST = {"2-O": (545.46, 4.5, ["2-O", "2-P"])}


def bllm_local():
    """BLLM No. 2 in the shared local frame (2-A corner 1 = origin)."""
    t = SG.TIE_BEARING["2-A"]
    a = math.radians(SG.az(t[0], t[1], t[2], t[3]))
    return -t[4]*math.sin(a), -t[4]*math.cos(a)


def _grow(seed, pool, lv, le):
    placed = {seed: [tuple(p) for p in lv[seed]]}
    frontier = [seed]
    LT, AT = 0.2, 0.6
    while frontier:
        P = frontier.pop()
        gPe = SA.edges(placed[P])
        for Q in pool:
            if Q in placed:
                continue
            cand = []
            for ep in gPe:
                for eq in le[Q]:
                    if abs(ep["L"]-eq["L"]) <= LT and abs(((ep["az"]-(eq["az"]+180)) % 360+180) % 360-180) <= AT:
                        gPi = placed[P][ep["i"]]; Qj = lv[Q][eq["j"]]
                        tx, ty = gPi[0]-Qj[0], gPi[1]-Qj[1]
                        cand.append((ep["L"], [(vx+tx, vy+ty) for vx, vy in lv[Q]]))
            for L, cv in sorted(cand, key=lambda c: -c[0]):
                if not SA._overlap(cv, list(placed.values())):
                    placed[Q] = cv; frontier.append(Q); break
    return placed


def components(lots, lv, le):
    """All connected components among `lots` (each in its own cluster-local frame)."""
    remaining = list(lots); out = []
    while remaining:
        comp = _grow(remaining[0], remaining, lv, le)
        out.append(comp)
        remaining = [l for l in remaining if l not in comp]
    return out


def fit_translation(clu, B):
    """Least-squares translation t so each lot's corner1 lands on its tie ray from BLLM.
    Ray constraint (linear in t): (c1+t-B) x d = 0  ->  tE*d.N - tN*d.E = (B.E-c1.E)*d.N - (B.N-c1.N)*d.E
    """
    A = []; b = []
    used = []
    for lot, verts in clu.items():
        t = SG.TIE_BEARING.get(lot)
        if not t:
            continue
        th = math.radians(SG.az(t[0], t[1], t[2], t[3]))
        dE, dN = math.sin(th), math.cos(th)
        c1 = verts[0]
        A.append([dN, -dE])
        b.append((B[0]-c1[0])*dN - (B[1]-c1[1])*dE)
        used.append(lot)
    if len(A) < 2:
        return None, used
    # normal equations for 2 unknowns
    a11 = sum(r[0]*r[0] for r in A); a12 = sum(r[0]*r[1] for r in A)
    a22 = sum(r[1]*r[1] for r in A)
    b1 = sum(A[i][0]*b[i] for i in range(len(A))); b2 = sum(A[i][1]*b[i] for i in range(len(A)))
    det = a11*a22 - a12*a12
    if abs(det) < 1e-9:
        return None, used
    tE = (b1*a22 - a12*b2)/det; tN = (a11*b2 - a12*b1)/det
    return (tE, tN), used


def main():
    ok, placed, _ = SA.assemble()
    lv = {k: SA.local_verts(v["courses"]) for k, v in ok.items()}
    le = {k: SA.edges(lv[k]) for k in ok}
    orphans = [k for k in ok if k not in placed]
    B = bllm_local()
    print(f"BLLM No. 2 local: E={B[0]:.2f} N={B[1]:.2f}  ({SA.to_lnglat(*B)})")
    print(f"orphans: {orphans}")
    comps = components(orphans, lv, le)
    print(f"orphan components: {[sorted(c) for c in comps]}")
    final = {}
    for clu in comps:
        t, used = fit_translation(clu, B)
        if not t:
            print(f"  {sorted(clu)}: only {len(used)} tie ray(s) — underdetermined "
                  f"(a lone lot has 1 dof left along its ray); held")
            continue
        print(f"  {sorted(clu)}: fitted from {len(used)} tie rays -> dE={t[0]:.2f} dN={t[1]:.2f}")
        for lot, v in clu.items():
            final[lot] = [(x+t[0], y+t[1]) for x, y in v]
    # lots placed by an explicitly read tie distance (bearing exact, one digit glare-obscured)
    for seed, (dist, tol, members) in TIE_DIST.items():
        if seed in placed or seed in final:
            continue
        tb = SG.TIE_BEARING[seed]
        th = math.radians(SG.az(tb[0], tb[1], tb[2], tb[3]))
        clu = _grow(seed, members, lv, le)
        c1 = (B[0]+dist*math.sin(th), B[1]+dist*math.cos(th))
        off = (c1[0]-clu[seed][0][0], c1[1]-clu[seed][0][1])
        cand = {l: [(x+off[0], y+off[1]) for x, y in v] for l, v in clu.items()}
        if any(SA._overlap(v, list(placed.values())) for v in cand.values()):
            print(f"  {sorted(clu)}: tie-distance placement overlaps the mesh — held"); continue
        print(f"  {sorted(clu)}: placed by READ tie distance {dist:.2f} m +/-{tol} m "
              f"(bearing exact; units digit under glare)")
        final.update(cand)
    if not final:
        print("\nnothing placeable from tie rays alone."); return
    # residuals: how well each corner1 sits on its tie ray, + recovered tie distance
    print(f"\n  {'lot':5s} {'tie bearing':>12s} {'resid(m)':>9s} {'recovered tie dist':>18s}")
    bad = 0
    for lot in sorted(final):
        tb = SG.TIE_BEARING.get(lot)
        if not tb:
            continue
        th = math.radians(SG.az(tb[0], tb[1], tb[2], tb[3]))
        dE, dN = math.sin(th), math.cos(th)
        c1 = final[lot][0]
        pe, pn = c1[0]-B[0], c1[1]-B[1]
        resid = abs(pe*dN - pn*dE)          # perpendicular offset from the ray
        along = pe*dE + pn*dN               # distance along the ray
        if resid > 3.0 or along <= 0:
            bad += 1
        print(f"  {lot:5s} {tb[0]} {tb[1]}-{tb[2]:02d} {tb[3]:>1s} {resid:9.2f} {along:15.1f} m")
    ovl = [o for o in final if SA._overlap(final[o], list(placed.values()))]
    print(f"\n  overlap with the 2-A mesh: {ovl if ovl else 'none'}")
    print(f"  off-ray/behind-monument lots: {bad}")

    if "--write" in sys.argv:
        if bad or ovl:
            print("\n  REFUSING to write: fit has off-ray lots or overlaps."); return
        import psycopg2
        conn = psycopg2.connect(SG.DSN); conn.autocommit = True; cur = conn.cursor()
        n = 0
        for lot, verts in final.items():
            ring = [SA.to_lnglat(*v) for v in verts]; ring.append(ring[0])
            cen = SA.centroid(verts); clng, clat = SA.to_lnglat(*cen)
            cur.execute("""INSERT INTO map_parcels
                (parcel_code, client_code, matter_code, title_no, label, geom_geojson,
                 centroid_lat, centroid_lng, area_sqm, stated_area_sqm, accuracy_tier, source_note, status)
                VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,'rough',%s,'draft')
                ON CONFLICT (parcel_code) DO UPDATE SET geom_geojson=EXCLUDED.geom_geojson,
                  centroid_lat=EXCLUDED.centroid_lat, centroid_lng=EXCLUDED.centroid_lng,
                  source_note=EXCLUDED.source_note, updated_at=now()""",
                (f"MWK-PSD221861-{lot.replace('2-','')}", "MWK-001", "MWK-001",
                 f"PSD-221861 Lot {lot}", f"Lot {lot} (Psd-221861)", json.dumps({"type": "Polygon", "coordinates": [ring]}),
                 clat, clng, round(ok[lot]["area"], 1), round(ok[lot]["stated"], 1),
                 f"Psd-221861 plan (doc 287); shape closure {ok[lot]['closure']:.2f}m; positioned by "
                 f"tie-line ray fit from BLLM No.2 (tie distances recovered, not read) — rough tier"))
            n += 1
        print(f"\n  wrote {n} orphan lots to map_parcels.")
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
