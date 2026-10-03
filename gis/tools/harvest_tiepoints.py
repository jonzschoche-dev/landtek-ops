#!/usr/bin/env python3
"""LandTek Mapping Division - DENR-LMB tie point harvester.

Pulls survey tie points (BLLM / BLBM / BBM / MBM / PRS92 GCP / triangulation
stations) from the DENR/NAMRIA Geoportal Lot Plotter backend and writes a
normalised CSV ready for the master-map build.

    python3 harvest_tiepoints.py "CAMARINES NORTE" PARACALE MERCEDES
    python3 harvest_tiepoints.py "CAMARINES NORTE"            # all municipalities
    python3 harvest_tiepoints.py --list-provinces

Notes
-----
* The endpoints are session-gated. Hitting /lp/getlocations cold returns
  {"error":"Unauthorized"}; you must first GET the Lot Plotter page to pick up
  the connect.sid cookie. That is what requests.Session() below does, and it is
  why the dropdowns look "broken" when the page is opened without JavaScript.
* Published lat/lon are PRS92 GEOGRAPHIC (EPSG:4683), NOT WGS84. Verified by
  reprojecting to EPSG:3124 and reproducing the published PTM Zone 4 grid
  coordinates to under 5 mm. Transform to EPSG:4326 before overlaying on
  satellite imagery or the points sit ~217 m to the southeast.
* Output is reference material only - not a certified monument description.
"""
from __future__ import annotations

import csv
import sys
import time
from typing import Iterable

import requests

BASE = "https://geoportal.gov.ph"
APP = f"{BASE}/gpapps/lotplotter/"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
PAUSE = 0.15  # be polite to a government server


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": APP,
    })
    s.get(APP, timeout=30).raise_for_status()  # seeds connect.sid
    return s


def get(s: requests.Session, path: str):
    r = s.get(f"{BASE}{path}", timeout=30)
    r.raise_for_status()
    return r.json()


def provinces(s) -> list[str]:
    return [p["province"] for p in get(s, "/lp/getlocations") if p.get("province")]


def municipalities(s, province: str) -> list[str]:
    return [m["municipality"] for m in
            get(s, f"/lp/getMunicipality/{requests.utils.quote(province)}")
            if m.get("municipality")]


def tie_points(s, province: str, municipality: str) -> list[dict]:
    return get(s, f"/lp/gettp/{requests.utils.quote(province)}"
                  f"/{requests.utils.quote(municipality)}")


def tie_point_value(s, tp_id: int) -> dict:
    rows = get(s, f"/lp/gettpvalue/{tp_id}")
    return rows[0] if rows else {}


def harvest(province: str, munis: Iterable[str] | None, out: str) -> int:
    s = session()
    munis = list(munis) if munis else municipalities(s, province)
    rows, missing = [], 0
    for mun in munis:
        tps = tie_points(s, province, mun)
        print(f"{province} / {mun}: {len(tps)} tie points", file=sys.stderr)
        for tp in tps:
            v = tie_point_value(s, tp["id"])
            if not v.get("lat"):
                missing += 1
            rows.append({
                "province": province,
                "municipality": mun,
                "pointref": tp["pointref"],
                "id": tp["id"],
                "lat": v.get("lat", ""),          # PRS92 geographic
                "lon": v.get("lon", ""),          # PRS92 geographic
                "ptm_zone": (v.get("zone") or "").strip(),
                "ptm_x": v.get("ptmx", ""),
                "ptm_y": v.get("ptmy", ""),
            })
            time.sleep(PAUSE)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {out} ({missing} without coordinates)", file=sys.stderr)
    return len(rows)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        raise SystemExit(0)
    if args[0] == "--list-provinces":
        for p in provinces(session()):
            print(p)
        raise SystemExit(0)
    prov, munis = args[0].upper(), [a.upper() for a in args[1:]]
    slug = prov.lower().replace(" ", "_")
    harvest(prov, munis or None, f"tiepoints_{slug}.csv")
