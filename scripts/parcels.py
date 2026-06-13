#!/usr/bin/env python3
"""parcels.py — store + query parcel geometry (geospatial pillar, creditless).

Builds on survey_geometry: given a parcel's metes-and-bounds call text, compute the
polygon + area and persist it in `parcels`. Geometry is stored as local-meter WKT for now
— this is PostGIS-READY: `geom_wkt` becomes a real PostGIS geometry column once we have a
tie point for absolute georeferencing (the spatial-DB upgrade). Until then, spatial ops
(area via shoelace, point-in-polygon via ray casting) are pure Python, so nothing depends
on PostGIS yet — the efficient choice while parcels are still relative shapes.

  upsert_parcel(matter, title_no, calls_text, source_doc_id, stated_ha) -> analysis + parcel_id
  point_in_parcel(parcel_id, x, y) -> bool   (foundation for photo-vs-titled-boundary)
  list_parcels() -> rows
"""
from __future__ import annotations
import os
import re
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
import survey_geometry as sg

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def ensure(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS parcels (
        id serial PRIMARY KEY,
        matter_code text, title_no text, source_doc_id int,
        area_sqm numeric, area_ha numeric, closure_error_m numeric, calls int,
        geom_wkt text,                      -- local-meter polygon; PostGIS-ready
        stated_ha numeric, area_matches bool,
        provenance_level text DEFAULT 'inferred_strong',
        created_at timestamptz DEFAULT now())""")


def upsert_parcel(matter_code, title_no, calls_text, source_doc_id=None, stated_ha=None):
    a = sg.cross_check(calls_text, stated_ha) if stated_ha else sg.analyze(calls_text)
    if not a.get("ok"):
        return a
    c = _conn(); cur = c.cursor(); ensure(cur)
    cur.execute("""INSERT INTO parcels
        (matter_code, title_no, source_doc_id, area_sqm, area_ha, closure_error_m, calls,
         geom_wkt, stated_ha, area_matches)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (matter_code, title_no, source_doc_id, a["area_sqm"], a["area_ha"], a["closure_error_m"],
         a["calls"], a["wkt_local"], stated_ha, a.get("area_matches")))
    a["parcel_id"] = cur.fetchone()[0]
    cur.close(); c.close()
    return a


def wkt_points(wkt):
    m = re.search(r"\(\((.*)\)\)", wkt or "")
    if not m:
        return []
    out = []
    for p in m.group(1).split(","):
        xy = p.strip().split()
        if len(xy) == 2:
            out.append((float(xy[0]), float(xy[1])))
    return out


def point_in_parcel(parcel_id, x, y):
    c = _conn(); cur = c.cursor()
    cur.execute("SELECT geom_wkt FROM parcels WHERE id=%s", (parcel_id,))
    r = cur.fetchone(); cur.close(); c.close()
    if not r:
        return None
    pts = wkt_points(r[0])
    inside = False
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]; x2, y2 = pts[i + 1]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1):
            inside = not inside
    return inside


def list_parcels():
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor); ensure(cur)
    cur.execute("""SELECT id, matter_code, title_no, area_ha, stated_ha, area_matches,
                          closure_error_m, calls, source_doc_id
                     FROM parcels ORDER BY id""")
    rows = cur.fetchall(); cur.close(); c.close()
    return rows


if __name__ == "__main__":
    import json
    print(json.dumps(list_parcels(), indent=2, default=str))
