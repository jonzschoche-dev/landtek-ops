#!/usr/bin/env python3
"""Google Earth KMZ for the LandTek Camarines Norte tie point master map.

All placemark coordinates are WGS84, transformed from the published PRS92
geographic values. Using the raw published lat/lon would place every monument
roughly 215 m from its true position on Google Earth imagery.
"""
import json, zipfile, html, os
from collections import defaultdict

OUT = "build"
feats = [f["properties"] for f in json.load(open(f"{OUT}/tiepoints_wgs84.geojson"))["features"]]

STYLE = {
    "BLLM":  ("ff2727d6", "http://maps.google.com/mapfiles/kml/shapes/triangle.png",   1.1),
    "BLBM":  ("ff0e7fff", "http://maps.google.com/mapfiles/kml/shapes/square.png",     0.9),
    "BBM":   ("ffb4771f", "http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png", 0.8),
    "MBM":   ("ffbd6794", "http://maps.google.com/mapfiles/kml/shapes/donut.png",      0.9),
    "PRS92": ("ff20a02c", "http://maps.google.com/mapfiles/kml/shapes/star.png",       1.2),
    "TRIG":  ("ff4b568c", "http://maps.google.com/mapfiles/kml/shapes/polygon.png",    0.9),
    "PBM":   ("ff22bdbc", "http://maps.google.com/mapfiles/kml/shapes/triangle.png",   0.9),
    "BDRY":  ("ff949cc4", "http://maps.google.com/mapfiles/kml/shapes/placemark_square.png", 0.8),
    "FZM":   ("ffcfbe17", "http://maps.google.com/mapfiles/kml/shapes/open-diamond.png", 1.0),
    "PPM":   ("ffc277e3", "http://maps.google.com/mapfiles/kml/shapes/target.png",     1.0),
    "P":     ("ff7f7f7f", "http://maps.google.com/mapfiles/kml/shapes/shaded_dot.png", 0.5),
}
ORDER = ["BLLM", "BLBM", "BBM", "MBM", "PBM", "BDRY", "PRS92", "TRIG", "FZM", "PPM", "P"]
LABEL = {
    "BLLM": "BLLM - Bureau of Lands Location Monument",
    "BLBM": "BLBM - Bureau of Lands Barrio Monument",
    "BBM": "BBM - Barrio Boundary Monument",
    "MBM": "MBM - Municipal Boundary Monument",
    "PRS92": "PRS92 geodetic control point",
    "TRIG": "Triangulation station",
    "PBM": "PBM - Provincial Boundary Monument",
    "BDRY": "Bdry. Mon. - inter-municipal / provincial boundary monument",
    "FZM": "FZM - Forest Zone Monument",
    "PPM": "PPM - US Army 29th Engineer survey monument",
    "P": "P - numbered cadastral point (Cad survey)",
}
# The 243 cadastral P points swamp the view at province scale; collapse them by default.
COLLAPSED = {"P"}

e = html.escape


def styles():
    out = []
    for code, (color, icon, scale) in STYLE.items():
        for suffix, sc, labsc in (("", scale, 0.75), ("_hl", scale * 1.25, 0.9)):
            out.append(f"""  <Style id="s_{code}{suffix}">
    <IconStyle><color>{color}</color><scale>{sc:.2f}</scale>
      <Icon><href>{icon}</href></Icon></IconStyle>
    <LabelStyle><color>ffffffff</color><scale>{labsc}</scale></LabelStyle>
    <BalloonStyle><text><![CDATA[$[description]]]></text></BalloonStyle>
  </Style>""")
        out.append(f"""  <StyleMap id="m_{code}">
    <Pair><key>normal</key><styleUrl>#s_{code}</styleUrl></Pair>
    <Pair><key>highlight</key><styleUrl>#s_{code}_hl</styleUrl></Pair>
  </StyleMap>""")
    return "\n".join(out)


def balloon(p):
    rows = [
        ("Monument type", p["mon_type_label"]),
        ("LGU", f'{p["lgu"] or p["municipality"]}, {p["province"]}'),
        ("As published", p["source_locality"]),
        ("Survey project", p["survey_project"] or "&mdash;"),
        ("Barrio", p["barrio"] or "&mdash;"),
        ("Variant", p["variant"] or "&mdash;"),
    ]
    coords = [
        ("PRS92 geographic", f'{p["prs92_lat"]:.8f} N, {p["prs92_lon"]:.8f} E'),
        ("WGS84 (this pin)", f'{p["wgs84_lat"]:.8f} N, {p["wgs84_lon"]:.8f} E'),
        (f'PTM Zone {p["ptm_zone"]} easting', f'{p["ptm_east"]:,.3f} m'),
        (f'PTM Zone {p["ptm_zone"]} northing', f'{p["ptm_north"]:,.3f} m'),
    ]

    def tbl(items):
        return "".join(
            f'<tr><td style="padding:2px 10px 2px 0;color:#555;white-space:nowrap">{k}</td>'
            f'<td style="padding:2px 0;font-weight:600">{v}</td></tr>' for k, v in items)

    return f"""<![CDATA[<div style="font-family:Helvetica,Arial,sans-serif;font-size:12px;max-width:380px">
<div style="font-size:13px;font-weight:700;margin-bottom:6px">{e(p["pointref"])}</div>
<table>{tbl(rows)}</table>
<div style="margin:8px 0 4px;font-weight:700;border-top:1px solid #ddd;padding-top:6px">Coordinates</div>
<table>{tbl(coords)}</table>
<div style="margin-top:8px;font-size:10px;color:#777;border-top:1px solid #ddd;padding-top:6px">
Source: {e(p["source"])} &middot; retrieved {p["retrieved"]} &middot; Geoportal id {p["gp_id"]}<br/>
{e(p["legal_status"])}. Verify against a DENR-LMB certified monument description before use in any survey or filing.
</div></div>]]>"""


def placemark(p):
    name = f'{p["mon_type"]} {p["mon_no"]}'.strip()
    if p["variant"]:
        name += f' ({p["variant"]})'
    name += f' — {p["lgu"] or p["municipality"]}'
    return f"""      <Placemark>
        <name>{e(name)}</name>
        <styleUrl>#m_{p["mon_type"]}</styleUrl>
        <description>{balloon(p)}</description>
        <ExtendedData>
          <Data name="pointref"><value>{e(p["pointref"])}</value></Data>
          <Data name="ptm_east"><value>{p["ptm_east"]}</value></Data>
          <Data name="ptm_north"><value>{p["ptm_north"]}</value></Data>
          <Data name="prs92_lat"><value>{p["prs92_lat"]}</value></Data>
          <Data name="prs92_lon"><value>{p["prs92_lon"]}</value></Data>
        </ExtendedData>
        <Point><coordinates>{p["wgs84_lon"]:.8f},{p["wgs84_lat"]:.8f},0</coordinates></Point>
      </Placemark>"""


groups = defaultdict(list)
for p in feats:
    groups[p["mon_type"]].append(p)


def sortkey(p):
    try:
        return (p["lgu"], 0, int(p["mon_no"]))
    except ValueError:
        return (p["lgu"], 1, p["mon_no"])


folders = []
for code in ORDER:
    items = sorted(groups.get(code, []), key=sortkey)
    if not items:
        continue
    by_mun = defaultdict(list)
    for p in items:
        by_mun[p["lgu"] or "(locality unresolved)"].append(p)
    sub = "\n".join(
        f"""      <Folder>
        <name>{e(m)} ({len(v)})</name>
{chr(10).join(placemark(p) for p in v)}
      </Folder>""" for m, v in sorted(by_mun.items()))
    vis = "\n      <visibility>0</visibility>" if code in COLLAPSED else ""
    folders.append(f"""    <Folder>
      <name>{e(LABEL[code])} ({len(items)})</name>
      <open>0</open>{vis}
{sub}
    </Folder>""")

lons = [p["wgs84_lon"] for p in feats]
lats = [p["wgs84_lat"] for p in feats]

DOC_DESC = f"""<![CDATA[<div style="font-family:Helvetica,Arial,sans-serif;font-size:12px;max-width:420px">
<b>LandTek Mapping Division</b><br/>Survey tie point master map &mdash; Camarines Norte.<br/><br/>
<b>{len(feats)} monuments</b> across all 12 municipalities of Camarines Norte,
from the DENR-LMB tie point table served by the Geoportal Lot Plotter, retrieved 21 September 2026.<br/><br/>
The <i>numbered cadastral points (P)</i> folder is switched off by default &mdash; 243 Labo cadastre
points otherwise bury everything else at province scale. Tick it when you zoom into Labo.<br/><br/>
<b>Datum handling.</b> The source publishes latitude and longitude on <b>PRS92 (EPSG:4683)</b>, not WGS84 &mdash;
confirmed because those values reproduce the published PTM Zone 4 grid coordinates to under 5 mm.
Every pin here has been transformed to WGS84 so it lands correctly on Google Earth imagery;
the original PRS92 values are kept in each balloon. Plotting the raw published lat/lon would
put each monument about <b>215 m</b> off.<br/><br/>
<b>Status.</b> Reference only. Not a certified monument description. Verify against DENR-LMB
or the Regional Land Management Services before relying on any position in a survey or a filing.
</div>]]>"""

KML = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>LandTek — Camarines Norte Tie Points</name>
  <description>{DOC_DESC}</description>
  <open>1</open>
{styles()}
  <LookAt>
    <longitude>{sum(lons)/len(lons):.6f}</longitude>
    <latitude>{sum(lats)/len(lats):.6f}</latitude>
    <altitude>0</altitude><heading>0</heading><tilt>0</tilt>
    <range>32000</range>
    <altitudeMode>relativeToGround</altitudeMode>
  </LookAt>
{chr(10).join(folders)}
</Document>
</kml>
"""

open(f"{OUT}/cn_tiepoints_master.kml", "w").write(KML)
with zipfile.ZipFile(f"{OUT}/cn_tiepoints_master.kmz", "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("doc.kml", KML)

import xml.dom.minidom
xml.dom.minidom.parse(f"{OUT}/cn_tiepoints_master.kml")
print(f"KML/KMZ written: {len(feats)} placemarks in {len(folders)} type folders; XML valid")
