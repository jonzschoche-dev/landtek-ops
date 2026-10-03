#!/usr/bin/env python3
"""LandTek Mapping Division - Camarines Norte tie point master dataset builder.

Source: DENR-LMB tie point table exposed by the DENR/NAMRIA Geoportal Lot Plotter
        (https://geoportal.gov.ph/gpapps/lotplotter/) endpoints /lp/gettp and /lp/gettpvalue.

Datum note (critical):
    The published lat/lon are PRS92 GEOGRAPHIC (EPSG:4683), NOT WGS84.
    Verified: EPSG:4683 -> EPSG:3124 reproduces the published PTM Zone 4 grid
    coordinates to 0.00 m. Plotting the raw lat/lon on WGS84 satellite imagery
    puts the monument roughly 215 m off.
"""
import csv, json, re, os, sys
from pyproj import Transformer

SRC = "cn_tiepoints_all.csv"
OUT = "build"
os.makedirs(OUT, exist_ok=True)

# PRS92 geographic -> PRS92 / Philippines zone IV (PTM)  [no datum shift]
T_PTM = Transformer.from_crs("EPSG:4683", "EPSG:3124", always_xy=True)
# PRS92 geographic -> WGS84 geographic  [datum shift, for imagery overlay]
T_WGS = Transformer.from_crs("EPSG:4683", "EPSG:4326", always_xy=True)

TYPES = [
    (r"^BLLM\b",   "BLLM",          "Bureau of Lands Location Monument"),
    (r"^BLBM\b",   "BLBM",          "Bureau of Lands Barrio Monument"),
    (r"^BBM\b",    "BBM",           "Barrio Boundary Monument"),
    (r"^MBM\b",    "MBM",           "Municipal Boundary Monument"),
    (r"^PBM\b",    "PBM",           "Provincial Boundary Monument"),
    (r"^Bdry\.?\s*Mon\.?", "BDRY",  "Boundary monument (inter-municipal / provincial)"),
    (r"^FZM\b",    "FZM",           "Forest Zone Monument"),
    (r"^PPM\b",    "PPM",           "PPM - US Army 29th Engineer survey monument"),
    (r"^CMN\b.*PRS\s*92", "PRS92",  "PRS92 geodetic control point"),
    (r"^Triangulation Station", "TRIG", "Triangulation station"),
    (r"^P\s*\d",   "P",             "Numbered cadastral point (Cad survey)"),
]

# Canonical LGU + PSGC (PSA, as of 31 July 2025). The source table spells some
# municipalities two ways and carries one locality that is not an LGU at all.
LGU = {
    "BASUD":                     ("Basud",            "0501601000"),
    "CAPALONGA":                 ("Capalonga",        "0501602000"),
    "DAET":                      ("Daet",             "0501603000"),
    "SAN LORENZO RUIZ (IMELDA)": ("San Lorenzo Ruiz", "0501604000"),
    "IMELDA":                    ("San Lorenzo Ruiz", "0501604000"),
    "JOSE PANGANIBAN":           ("Jose Panganiban",  "0501605000"),
    "LABO":                      ("Labo",             "0501606000"),
    "MERCEDES":                  ("Mercedes",         "0501607000"),
    "PARACALE":                  ("Paracale",         "0501608000"),
    "SAN VICENTE":               ("San Vicente",      "0501609000"),
    "SANTA ELENA":               ("Santa Elena",      "0501610000"),
    "STA. ELENA":                ("Santa Elena",      "0501610000"),
    "TALISAY":                   ("Talisay",          "0501611000"),
    "VINZONS":                   ("Vinzons",          "0501612000"),
    # Not a Camarines Norte municipality. Source anomaly, left unresolved on purpose.
    "BAGONG SILANG":             ("",                 ""),
}


def classify(ref):
    for pat, code, label in TYPES:
        if re.match(pat, ref, re.I):
            return code, label
    return "OTHER", "Unclassified monument"

def mon_no(ref, code):
    if code == "PRS92":
        m = re.match(r"^(CMN\s*\d+)", ref, re.I)
        return re.sub(r"\s+", " ", m.group(1)) if m else ""
    if code == "TRIG":
        m = re.match(r"^Triangulation Station\s+([^,]+?)(?:,|$)", ref)
        return m.group(1).strip() if m else ""
    if code == "PPM":
        m = re.match(r"^PPM\s+([0-9A-Z ]+?)(?:,|$)", ref)
        return m.group(1).strip() if m else ""
    if code == "P":
        m = re.match(r"^P\s*([0-9]+)", ref)
        return m.group(1) if m else ""
    if code == "BDRY":
        m = re.match(r"^Bdry\.?\s*Mon\.?\s*(?:No\.\s*)?([^,]+?)(?:,|$)", ref)
        return m.group(1).strip() if m else ""
    m = re.match(r"^[A-Z]+\s+No\.\s*([0-9]+)", ref, re.I)
    return m.group(1) if m else ""

def project(ref):
    m = re.search(r"\b(Pls|Cadm|Cad)\s*([0-9]+)(?:\s*[- ]\s*([A-Z])\b)?", ref, re.I)
    if not m:
        return ""
    base = f"{m.group(1).title()}-{m.group(2)}"
    return f"{base}-{m.group(3).upper()}" if m.group(3) else base

def barrio(ref):
    m = re.search(r"Bo\.\s*of\s*([A-Za-zñÑ' .-]+?)\s*(?:,|$)", ref)
    return m.group(1).strip() if m else ""

def variant(ref):
    m = re.search(r"\(([^)]*(?:Relocated|New|N\.Pos)[^)]*)\)\s*(?:\(([^)]+)\))?", ref)
    if not m:
        return ""
    return " ".join(p for p in m.groups() if p)

rows_in = list(csv.DictReader(open(SRC)))
feats, skipped = [], []
for i, r in enumerate(rows_in, 1):
    if not r["lat"] or not r["lon"]:
        skipped.append(r)
        continue
    lat, lon = float(r["lat"]), float(r["lon"])
    code, label = classify(r["pointref"])
    px, py = T_PTM.transform(lon, lat)
    wlon, wlat = T_WGS.transform(lon, lat)
    pub_x = float(r["ptm_x"]) if r["ptm_x"] else None
    pub_y = float(r["ptm_y"]) if r["ptm_y"] else None
    resid = round(((px - pub_x) ** 2 + (py - pub_y) ** 2) ** 0.5, 3) if pub_x else None
    lgu, psgc = LGU.get(r["municipality"].strip().upper(), (r["municipality"].title(), ""))
    feats.append({
        "gp_id": int(r["id"]),
        "pointref": r["pointref"],
        "lgu": lgu,
        "psgc_code": psgc,
        "source_locality": r["municipality"],
        "municipality": r["municipality"].title(),
        "province": "Camarines Norte",
        "province_psgc": "0501600000",
        "mon_type": code,
        "mon_type_label": label,
        "mon_no": mon_no(r["pointref"], code),
        "survey_project": project(r["pointref"]),
        "barrio": barrio(r["pointref"]),
        "variant": variant(r["pointref"]),
        "prs92_lat": round(lat, 8),
        "prs92_lon": round(lon, 8),
        "wgs84_lat": round(wlat, 8),
        "wgs84_lon": round(wlon, 8),
        "ptm_zone": int(r["ptm_zone"]) if r["ptm_zone"] else 4,
        "ptm_east": pub_x,
        "ptm_north": pub_y,
        "ptm_check_resid_m": resid,
        "source": "DENR-LMB via Geoportal Lot Plotter",
        "retrieved": "2026-09-21",
        "dataset_version": "1.0.0",
        "legal_status": "Reference only - not a certified monument description",
    })

def fc(coord_keys, crs_urn):
    return {
        "type": "FeatureCollection",
        "name": "cn_tiepoints",
        "crs": {"type": "name", "properties": {"name": crs_urn}},
        "features": [
            {"type": "Feature",
             "geometry": {"type": "Point", "coordinates": [f[coord_keys[0]], f[coord_keys[1]]]},
             "properties": f}
            for f in feats
        ],
    }

json.dump(fc(("wgs84_lon", "wgs84_lat"), "urn:ogc:def:crs:OGC:1.3:CRS84"),
          open(f"{OUT}/tiepoints_wgs84.geojson", "w"), indent=1)
json.dump(fc(("prs92_lon", "prs92_lat"), "urn:ogc:def:crs:EPSG::4683"),
          open(f"{OUT}/tiepoints_prs92.geojson", "w"), indent=1)
json.dump(fc(("ptm_east", "ptm_north"), "urn:ogc:def:crs:EPSG::3124"),
          open(f"{OUT}/tiepoints_ptm4.geojson", "w"), indent=1)

with open(f"{OUT}/cn_tiepoints_master.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(feats[0].keys()))
    w.writeheader(); w.writerows(feats)

resids = [f["ptm_check_resid_m"] for f in feats if f["ptm_check_resid_m"] is not None]
print(f"features={len(feats)} skipped_no_coords={len(skipped)}")
print(f"PTM reprojection residual: max={max(resids):.3f} m  mean={sum(resids)/len(resids):.4f} m")
from collections import Counter
print("by type:", dict(Counter(f["mon_type"] for f in feats)))
print("by municipality:", dict(Counter(f["municipality"] for f in feats)))
print("skipped:", [s["pointref"] for s in skipped])
