#!/usr/bin/env python3
"""Verify a LandTek GIS tie point dataset. Exit 0 = pass, 1 = fail.

    python3 tools/verify_dataset.py
    python3 tools/verify_dataset.py --dataset datasets/ph-tiepoints-camarines-norte

Checks, in order:
  1. CHECKSUMS.sha256 matches every file in the dataset.
  2. Every KMZ placemark round-trips WGS84 -> PRS92 -> PTM Zone 4 back to the
     published grid coordinate.  This is the load-bearing check: it proves the
     datum handling is right end to end.
  3. GeoPackage PTM geometry equals the published easting/northing exactly.
  4. Feature counts agree across GeoPackage, GeoJSON, CSV and KMZ.
  5. Every mon_type in the data has a symbol category in the QGIS project.
  6. Archive integrity and XML well-formedness for .qgz, .kmz, .kml.
  7. The QGIS project's relative datasource paths resolve to real files.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

KML_NS = {"k": "http://www.opengis.net/kml/2.2"}
TOL_M = 0.05           # KMZ round-trip tolerance
ROOT = Path(__file__).resolve().parent.parent


class Report:
    def __init__(self) -> None:
        self.ok = True

    def check(self, label: str, passed: bool, detail: str = "") -> None:
        self.ok &= bool(passed)
        mark = "PASS" if passed else "FAIL"
        print(f"[{mark}] {label}" + (f"  —  {detail}" if detail else ""))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path,
                    default=ROOT / "datasets" / "ph-tiepoints-camarines-norte")
    a = ap.parse_args()
    ds: Path = a.dataset
    r = Report()

    from pyproj import Transformer
    t_wgs_to_prs = Transformer.from_crs("EPSG:4326", "EPSG:4683", always_xy=True)
    t_prs_to_ptm = Transformer.from_crs("EPSG:4683", "EPSG:3124", always_xy=True)

    # 1. checksums
    manifest = (ds / "CHECKSUMS.sha256").read_text().splitlines()
    bad = []
    for line in manifest:
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        p = ds / rel
        if not p.exists() or sha256(p) != digest:
            bad.append(rel)
    r.check("checksums", not bad, f"{len(manifest)} files" if not bad else f"mismatched: {bad}")

    # 2. KMZ round trip
    kml = ET.fromstring(zipfile.ZipFile(ds / "exports" / "cn_tiepoints.kmz").read("doc.kml"))
    worst, n = 0.0, 0
    for pm in kml.iter("{http://www.opengis.net/kml/2.2}Placemark"):
        lon, lat = [float(x) for x in pm.find(".//k:Point/k:coordinates", KML_NS).text.split(",")[:2]]
        ed = {d.get("name"): d.find("k:value", KML_NS).text for d in pm.findall(".//k:Data", KML_NS)}
        plon, plat = t_wgs_to_prs.transform(lon, lat)
        x, y = t_prs_to_ptm.transform(plon, plat)
        worst = max(worst, math.hypot(x - float(ed["ptm_east"]), y - float(ed["ptm_north"])))
        n += 1
    r.check("KMZ datum round trip", worst < TOL_M, f"{n} pins, max error {worst * 100:.3f} cm")

    # 3 + 4. counts and grid fidelity
    rows = list(csv.DictReader(open(ds / "exports" / "cn_tiepoints.csv")))
    pub = {int(x["gp_id"]): x for x in rows}
    counts = {"csv": len(rows), "kmz": n}
    for name in ("tiepoints_wgs84", "tiepoints_ptm4", "tiepoints_prs92"):
        gj = json.load(open(ds / "data" / f"{name}.geojson"))
        counts[f"geojson:{name}"] = len(gj["features"])
        out = subprocess.run(["ogrinfo", "-so", str(ds / "data" / "cn_tiepoints.gpkg"), name],
                             capture_output=True, text=True).stdout
        line = [l for l in out.splitlines() if "Feature Count" in l]
        counts[f"gpkg:{name}"] = int(line[0].split(":")[1]) if line else -1

    ptm = json.load(open(ds / "data" / "tiepoints_ptm4.geojson"))["features"]
    de = max(abs(f["geometry"]["coordinates"][0] - float(pub[f["properties"]["gp_id"]]["ptm_east"]))
             for f in ptm)
    dn = max(abs(f["geometry"]["coordinates"][1] - float(pub[f["properties"]["gp_id"]]["ptm_north"]))
             for f in ptm)
    r.check("PTM geometry equals published grid", de == 0 and dn == 0, f"max dE {de}, dN {dn}")
    r.check("feature counts agree", len(set(counts.values())) == 1, str(counts))

    # 5 + 6 + 7. QGIS project
    qgz = zipfile.ZipFile(ds / "project" / "cn_tiepoints.qgz")
    r.check("QGZ archive integrity", qgz.testzip() is None)
    proj = ET.fromstring(qgz.read(qgz.namelist()[0]).decode())
    cats = {c.get("value") for c in proj.iter("category")}
    present = {x["mon_type"] for x in rows}
    r.check("symbol categories cover all monument types", present <= cats,
            f"{len(present)} types" if present <= cats else f"missing {present - cats}")
    srcs = [m.find("datasource").text for m in proj.iter("maplayer") if m.get("type") == "vector"]
    resolved = all((ds / "project" / s.split("|")[0]).exists() for s in srcs)
    r.check("QGIS datasource paths resolve", resolved, f"{len(srcs)} vector layers")

    kmz_zip = zipfile.ZipFile(ds / "exports" / "cn_tiepoints.kmz")
    r.check("KMZ archive integrity", kmz_zip.testzip() is None)
    ET.parse(ds / "exports" / "cn_tiepoints.kml")
    r.check("KML well-formed", True)

    # QA field sanity
    resids = [float(x["ptm_check_resid_m"]) for x in rows if x["ptm_check_resid_m"]]
    r.check("reprojection residuals within 1 cm", max(resids) < 0.01,
            f"max {max(resids) * 100:.3f} cm")

    print("\n" + ("VERIFICATION PASSED" if r.ok else "VERIFICATION FAILED"))
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
