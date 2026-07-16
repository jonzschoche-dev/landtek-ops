"""geo_math — dependency-free planar geometry for the LandTek mapping layer.

No PostGIS, no shapely required (shapely is used opportunistically by the audit
agent for polygon-polygon overlap; everything here is pure Python + math so the
save path and area sanity-check work on a bare interpreter).

Coordinate convention matches GeoJSON: a ring is a list of [lng, lat] pairs,
degrees, WGS84. Areas/distances are computed on a LOCAL TANGENT PLANE anchored
at the ring's mean latitude — accurate to a fraction of a percent at parcel
scale (hundreds of meters), which is all the "does the plot match the title
area" check needs. It is NOT a geodesic-grade computation and must not be sold
as survey accuracy — that is what the orthomosaic tier is for.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple

_R = 6_378_137.0  # WGS84 equatorial radius, meters


def local_ring_to_geojson(pts, anchor_lat, anchor_lng, origin=None):
    """Georeference a LOCAL-METER ring (x=East, y=North; the parcels `geom_wkt` convention)
    to an absolute WGS84 GeoJSON Polygon, by translating `origin` (default the first vertex,
    i.e. corner 1) onto (anchor_lat, anchor_lng).

    Survey bearings are TRUE north, so the ring's orientation is already absolute — this is a
    PURE TRANSLATION, no rotation. Inverse of `_to_local_m`, using the same `_R`, so a ring
    round-trips through polygon_area_sqm essentially unchanged. `pts` = [(x_east, y_north), …].
    """
    if not pts:
        return None
    ox, oy = origin if origin is not None else pts[0]
    cos0 = math.cos(math.radians(anchor_lat)) or 1e-9
    coords = []
    for x, y in pts:
        dlng = math.degrees((x - ox) / (_R * cos0))
        dlat = math.degrees((y - oy) / _R)
        coords.append([round(anchor_lng + dlng, 8), round(anchor_lat + dlat, 8)])
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return {"type": "Polygon", "coordinates": [coords]}


def _ring(geojson: dict) -> List[Sequence[float]]:
    """Exterior ring ([lng,lat] pairs) of a GeoJSON Polygon or Feature."""
    if not geojson:
        return []
    g = geojson.get("geometry", geojson)
    if g.get("type") == "Polygon":
        rings = g.get("coordinates") or []
        return rings[0] if rings else []
    if g.get("type") == "Feature":
        return _ring(g)
    return []


def _to_local_m(ring: Sequence[Sequence[float]]) -> List[Tuple[float, float]]:
    """Project [lng,lat] degrees to local meters (x=east, y=north) about the
    ring's mean latitude. Equirectangular / local-tangent-plane approximation."""
    if not ring:
        return []
    lat0 = sum(p[1] for p in ring) / len(ring)
    cos0 = math.cos(math.radians(lat0))
    out = []
    for lng, lat in ring:
        x = math.radians(lng) * _R * cos0
        y = math.radians(lat) * _R
        out.append((x, y))
    return out


def polygon_area_sqm(geojson: dict) -> float:
    """Planar area of the exterior ring, in square meters (always positive)."""
    pts = _to_local_m(_ring(geojson))
    if len(pts) < 3:
        return 0.0
    # Close the ring if the last point isn't the first.
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    s = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def polygon_centroid(geojson: dict) -> Tuple[float, float] | Tuple[None, None]:
    """Area-weighted centroid as (lat, lng). Falls back to vertex mean for
    degenerate rings."""
    ring = _ring(geojson)
    if len(ring) < 3:
        if ring:
            return (ring[0][1], ring[0][0])
        return (None, None)
    pts = _to_local_m(ring)
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
        ring = list(ring) + [ring[0]]
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if a == 0:
        lat = sum(p[1] for p in ring) / len(ring)
        lng = sum(p[0] for p in ring) / len(ring)
        return (lat, lng)
    a *= 0.5
    cx /= (6 * a)
    cy /= (6 * a)
    # Invert the local projection back to degrees at the ring's mean latitude.
    lat0 = sum(p[1] for p in ring) / len(ring)
    cos0 = math.cos(math.radians(lat0))
    lng = math.degrees(cx / (_R * cos0)) if cos0 else 0.0
    lat = math.degrees(cy / _R)
    return (lat, lng)


def bbox(geojson: dict) -> Tuple[float, float, float, float] | None:
    """(min_lng, min_lat, max_lng, max_lat) of the exterior ring."""
    ring = _ring(geojson)
    if not ring:
        return None
    lngs = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return (min(lngs), min(lats), max(lngs), max(lats))


def bbox_overlap(a: dict, b: dict) -> bool:
    """Cheap bounding-box overlap test — a necessary (not sufficient) condition
    for two polygons to intersect. The audit agent uses this as a pre-filter
    before the (optional) exact shapely test."""
    ba, bb = bbox(a), bbox(b)
    if not ba or not bb:
        return False
    return not (ba[2] < bb[0] or bb[2] < ba[0] or ba[3] < bb[1] or bb[3] < ba[1])
