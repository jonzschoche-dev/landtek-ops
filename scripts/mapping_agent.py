#!/usr/bin/env python3
"""mapping_agent — the reasoning layer over the `parcels` geometry spine.

Beyond "pretty map", the mapping agent earns its keep by cross-checking plotted
geometry against the paper record and against neighboring parcels:

  1. AREA CHECK — plotted area vs. the title's stated area (parcels.stated_area_sqm).
     A large deviation means the rough plot is wrong OR the title's area is off
     (a real fraud/encroachment signal on this matter). Writes parcels.area_flag.

  2. OVERLAP CHECK — do two parcels' polygons intersect? A cross-OWNER overlap is
     an encroachment / double-titling signal (exactly the T-4497 attack surface).
     Uses shapely for an exact test when available; degrades to a bounding-box
     pre-filter (flagged 'possible', human to confirm) when it is not.

  3. Read-only by default. `--write` persists area_flag. It NEVER edits geometry
     (a human draws that) and NEVER files/sends anything — same discipline as the
     rest of the stack.

Usage:
    python3 mapping_agent.py audit                 # report, all parcels
    python3 mapping_agent.py audit --client MWK-001
    python3 mapping_agent.py audit --write         # persist area_flag
    python3 mapping_agent.py overlaps              # cross-owner overlap report

Provenance: this is an INFERENCE layer. Its flags are leads to verify against the
survey, not asserted facts — consistent with Principle 9.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import psycopg2

# geo_math lives with the leo_tools blueprints; make it importable from scripts/.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "leo_tools"))
import geo_math  # noqa: E402

PG_DSN = os.getenv("LEO_TOOLS_PG_DSN",
                   "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

DEVIATION_FLAG_PCT = 15.0  # |plotted - stated| / stated above this -> flagged


def _db():
    return psycopg2.connect(PG_DSN)


def _load(client=None):
    q = ("SELECT parcel_code, client_code, label, geom_geojson, accuracy_tier, "
         "area_sqm, stated_area_sqm FROM parcels WHERE geom_geojson IS NOT NULL")
    args = []
    if client:
        q += " AND client_code=%s"; args.append(client)
    conn = _db(); cur = conn.cursor(); cur.execute(q, args)
    rows = cur.fetchall(); cur.close(); conn.close()
    out = []
    for pc, cc, label, geom, tier, area, stated in rows:
        g = geom if isinstance(geom, dict) else (json.loads(geom) if geom else None)
        out.append(dict(parcel_code=pc, client_code=cc, label=label, geom=g,
                        tier=tier, area=area, stated=stated))
    return out


def audit(client=None, write=False):
    parcels = _load(client)
    if not parcels:
        print("No plotted parcels" + (f" for {client}" if client else "") + ".")
        return
    updates = []
    print(f"{'parcel':<16}{'tier':<8}{'plotted m²':>12}{'title m²':>12}{'Δ':>8}  flag")
    print("-" * 70)
    for p in parcels:
        # Recompute area from geometry so the check is independent of stored value.
        area = round(geo_math.polygon_area_sqm(p["geom"]), 1) if p["geom"] else None
        stated = p["stated"]
        flag = None
        dev_s = ""
        if area and stated:
            dev = abs(area - stated) / stated * 100.0
            dev_s = f"{dev:.0f}%"
            flag = "ok" if dev <= DEVIATION_FLAG_PCT else f"deviation:{dev:.0f}%"
        elif area and not stated:
            flag = "no_title_area"
        a_s = f"{area:,.0f}" if area else "—"
        s_s = f"{stated:,.0f}" if stated else "—"
        print(f"{p['parcel_code']:<16}{(p['tier'] or '?'):<8}{a_s:>12}{s_s:>12}{dev_s:>8}  {flag or ''}")
        if flag:
            updates.append((flag, p["parcel_code"]))
    if write and updates:
        conn = _db(); conn.autocommit = True; cur = conn.cursor()
        for flag, pc in updates:
            cur.execute("UPDATE parcels SET area_flag=%s, updated_at=now() "
                        "WHERE parcel_code=%s", (flag, pc))
        cur.close(); conn.close()
        print(f"\nWrote area_flag on {len(updates)} parcel(s).")
    elif write:
        print("\nNothing to write.")


def overlaps():
    parcels = [p for p in _load() if p["geom"]]
    try:
        from shapely.geometry import shape  # optional exact test
        exact = True
    except Exception:
        exact = False
        print("(shapely not installed — using bounding-box pre-filter only; "
              "overlaps are 'possible', confirm manually)\n")

    def geom_of(p):
        g = p["geom"]; return g.get("geometry", g)

    found = 0
    for i in range(len(parcels)):
        for j in range(i + 1, len(parcels)):
            a, b = parcels[i], parcels[j]
            if not geo_math.bbox_overlap(a["geom"], b["geom"]):
                continue
            cross_owner = a["client_code"] != b["client_code"]
            if exact:
                try:
                    pa, pb = shape(geom_of(a)), shape(geom_of(b))
                    if not pa.intersects(pb):
                        continue
                    inter = pa.intersection(pb).area  # in deg² — relative only
                    kind = "OVERLAP"
                except Exception:
                    kind = "possible-overlap"
            else:
                kind = "possible-overlap(bbox)"
            sev = "CROSS-OWNER" if cross_owner else "same-owner"
            found += 1
            print(f"[{sev}] {kind}: {a['parcel_code']} ({a['client_code']}) "
                  f"<> {b['parcel_code']} ({b['client_code']})")
    if not found:
        print("No overlapping parcels detected.")
    else:
        print(f"\n{found} overlap(s). Cross-owner overlaps are encroachment / "
              "double-titling LEADS — verify against the survey + title chain.")


def main():
    ap = argparse.ArgumentParser(description="LandTek mapping agent")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("audit", help="area plotted-vs-title check")
    a.add_argument("--client")
    a.add_argument("--write", action="store_true")
    sub.add_parser("overlaps", help="cross-parcel overlap / encroachment check")
    args = ap.parse_args()
    if args.cmd == "audit":
        audit(client=args.client, write=args.write)
    elif args.cmd == "overlaps":
        overlaps()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
