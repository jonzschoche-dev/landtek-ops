"""Boundary QA: test every tie point against the municipal polygon of the LGU it is labelled with.

Writes lgu_check.csv (gp_id, lgu, in_lgu, dist_to_own_m, ...) consumed by the atlas scripts.
Polygons are geoBoundaries PHL ADM3 (NAMRIA / PSA / OCHA 2020) — administrative, not cadastral.
"""
import os

import geopandas as gpd

from atlas_common import CRS, DS, HERE, INPUTS

adm = gpd.read_file(os.path.join(INPUTS, "region_adm3.gpkg"))[["shapeName", "geometry"]].to_crs(CRS)
pts = gpd.read_file(os.path.join(DS, "data", "tiepoints_wgs84.geojson")).to_crs(CRS)

j = gpd.sjoin(pts, adm, how="left", predicate="within").rename(columns={"shapeName": "in_lgu"})
own = adm.set_index("shapeName")


def dist(r):
    if not r["lgu"] or r["lgu"] not in own.index:
        return None
    return r.geometry.distance(own.loc[r["lgu"]].geometry)


j["dist_to_own_m"] = j.apply(dist, axis=1)
j = j[~j.index.duplicated(keep="first")]
j.drop(columns=["geometry", "index_right"], errors="ignore").to_csv(os.path.join(INPUTS, "lgu_check.csv"), index=False)
inside = (j["in_lgu"] == j["lgu"]).sum()
print(f"{inside} of {len(j)} inside their labelled LGU; {j['in_lgu'].isna().sum()} outside every polygon")
