#!/usr/bin/env python3
"""Generate a QGIS project (.qgz) for the LandTek Camarines Norte tie point master map."""
import os, json, zipfile, uuid, html
from pyproj import CRS

OUT = "build"
GPKG = "../data/cn_tiepoints.gpkg"

feats = json.load(open(f"{OUT}/tiepoints_wgs84.geojson"))["features"]
lons = [f["geometry"]["coordinates"][0] for f in feats]
lats = [f["geometry"]["coordinates"][1] for f in feats]

# Project CRS: WebMercator so XYZ basemaps render without reprojection artefacts
def merc(lon, lat):
    import math
    R = 6378137.0
    x = R * math.radians(lon)
    y = R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y

xs, ys = zip(*[merc(a, b) for a, b in zip(lons, lats)])
pad = 3000
XMIN, XMAX, YMIN, YMAX = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad

CATS = [
    ("BLLM",  "#d62728", "triangle",       4.2, "BLLM - Bureau of Lands Location Monument"),
    ("BLBM",  "#ff7f0e", "square",         3.6, "BLBM - Bureau of Lands Barrio Monument"),
    ("BBM",   "#1f77b4", "circle",         2.8, "BBM - Barrio Boundary Monument"),
    ("MBM",   "#9467bd", "diamond",        3.2, "MBM - Municipal Boundary Monument"),
    ("PRS92", "#2ca02c", "star",           4.6, "PRS92 geodetic control point"),
    ("TRIG",  "#8c564b", "pentagon",       3.6, "Triangulation station"),
    ("PBM",   "#bcbd22", "equilateral_triangle", 3.6, "PBM - Provincial Boundary Monument"),
    ("BDRY",  "#c49c94", "rectangle",      3.2, "Bdry. Mon. - inter-municipal / provincial"),
    ("FZM",   "#17becf", "hexagon",        3.4, "FZM - Forest Zone Monument"),
    ("PPM",   "#e377c2", "cross_fill",     3.4, "PPM - US Army 29th Engineer survey monument"),
    ("P",     "#7f7f7f", "circle",         1.7, "P - numbered cadastral point (Cad survey)"),
]


ELL = {4326: "EPSG:7030", 3857: "EPSG:7030", 3124: "EPSG:7008", 4683: "EPSG:7008"}


def ellipsoid_acronym(crs):
    code = crs.to_epsg()
    return ELL.get(code, "EPSG:7030")


def srs_block(epsg, srsid):
    crs = CRS.from_epsg(epsg)
    return f"""<spatialrefsys nativeFormat="Wkt">
      <wkt>{html.escape(crs.to_wkt())}</wkt>
      <proj4>{html.escape(crs.to_proj4())}</proj4>
      <srsid>{srsid}</srsid>
      <srid>{epsg}</srid>
      <authid>EPSG:{epsg}</authid>
      <description>{html.escape(crs.name)}</description>
      <projectionacronym>{crs.coordinate_operation.method_name if crs.coordinate_operation else 'longlat'}</projectionacronym>
      <ellipsoidacronym>{ellipsoid_acronym(crs)}</ellipsoidacronym>
      <geographicflag>{'true' if crs.is_geographic else 'false'}</geographicflag>
    </spatialrefsys>"""


def marker_symbol(idx, color, shape, size):
    return f"""<symbol frame_rate="10" is_animated="0" force_rhr="0" alpha="1" clip_to_extent="1" type="marker" name="{idx}">
        <data_defined_properties><Option type="Map">
          <Option type="QString" value="" name="name"/><Option name="properties"/>
          <Option type="QString" value="collection" name="type"/>
        </Option></data_defined_properties>
        <layer enabled="1" class="SimpleMarker" locked="0" pass="0" id="{{{uuid.uuid4()}}}">
          <Option type="Map">
            <Option type="QString" value="0" name="angle"/>
            <Option type="QString" value="square" name="cap_style"/>
            <Option type="QString" value="{hex_to_rgb(color)}" name="color"/>
            <Option type="QString" value="1" name="horizontal_anchor_point"/>
            <Option type="QString" value="bevel" name="joinstyle"/>
            <Option type="QString" value="{shape}" name="name"/>
            <Option type="QString" value="0,0" name="offset"/>
            <Option type="QString" value="3x:0,0,0,0,0,0" name="offset_map_unit_scale"/>
            <Option type="QString" value="MM" name="offset_unit"/>
            <Option type="QString" value="35,35,35,255,rgb:0.13725490196078433,0.13725490196078433,0.13725490196078433,1" name="outline_color"/>
            <Option type="QString" value="solid" name="outline_style"/>
            <Option type="QString" value="0.3" name="outline_width"/>
            <Option type="QString" value="3x:0,0,0,0,0,0" name="outline_width_map_unit_scale"/>
            <Option type="QString" value="MM" name="outline_width_unit"/>
            <Option type="QString" value="diameter" name="scale_method"/>
            <Option type="QString" value="{size}" name="size"/>
            <Option type="QString" value="3x:0,0,0,0,0,0" name="size_map_unit_scale"/>
            <Option type="QString" value="MM" name="size_unit"/>
            <Option type="QString" value="1" name="vertical_anchor_point"/>
          </Option>
          <data_defined_properties><Option type="Map">
            <Option type="QString" value="" name="name"/><Option name="properties"/>
            <Option type="QString" value="collection" name="type"/>
          </Option></data_defined_properties>
        </layer>
      </symbol>"""


def hex_to_rgb(h):
    h = h.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r},{g},{b},255,rgb:{r/255:.6f},{g/255:.6f},{b/255:.6f},1"


LAYER_ID = "cn_tiepoints_wgs84_main"
PRS_ID = "cn_tiepoints_ptm4_grid"
OSM_ID = "basemap_osm"
SAT_ID = "basemap_esri_sat"

categories = "\n".join(
    f'        <category symbol="{i}" type="string" value="{c}" uuid="{{{uuid.uuid4()}}}" label="{html.escape(lbl)}" render="true"/>'
    for i, (c, _, _, _, lbl) in enumerate(CATS)
)
symbols = "\n".join(marker_symbol(i, col, sh, sz) for i, (_, col, sh, sz, _) in enumerate(CATS))

LABELING = """<labeling type="simple">
      <settings calloutType="simple">
        <text-style fontFamily="Helvetica" fontSize="8" fontWeight="75" textColor="20,20,20,255"
          fontItalic="0" isExpression="1" fontUnderline="0" textOpacity="1" multilineHeight="1"
          fieldName="if(&quot;mon_type&quot; = 'P', '', concat(&quot;mon_type&quot;, ' ', &quot;mon_no&quot;))" fontSizeUnit="Point" blendMode="0" fontStrikeout="0" namedStyle="Bold">
          <text-buffer bufferDraw="1" bufferSize="0.9" bufferColor="255,255,255,255" bufferOpacity="1"
            bufferSizeUnits="MM" bufferJoinStyle="128" bufferNoFill="0"/>
          <text-mask maskEnabled="0"/>
          <background shapeDraw="0"/>
          <shadow shadowDraw="0"/>
        </text-style>
        <text-format placeDirectionSymbol="0" multilineAlign="3" wrapChar="" autoWrapLength="0"/>
        <placement placement="6" dist="1.5" distUnits="MM" quadOffset="4" offsetType="0" priority="5" xOffset="0" yOffset="0"/>
        <rendering scaleMin="1" scaleMax="60000" scaleVisibility="1" drawLabels="1" obstacle="1"
          labelPerPart="0" displayAll="0" upsidedownLabels="0" fontLimitPixelSize="0" mergeLines="0"/>
        <dd_properties><Option type="Map"><Option type="QString" value="" name="name"/>
          <Option name="properties"/><Option type="QString" value="collection" name="type"/></Option></dd_properties>
      </settings>
    </labeling>"""

FIELD_ALIASES = [
    ("gp_id", "Geoportal record id"),
    ("pointref", "Point reference (as published)"),
    ("lgu", "LGU (canonical)"),
    ("psgc_code", "PSGC code"),
    ("source_locality", "Locality (as published)"),
    ("municipality", "Municipality"),
    ("province", "Province"),
    ("province_psgc", "Province PSGC"),
    ("mon_type", "Monument type"),
    ("mon_type_label", "Monument type - full"),
    ("mon_no", "Monument no."),
    ("survey_project", "Survey project"),
    ("barrio", "Barrio / Bo."),
    ("variant", "Relocation variant"),
    ("prs92_lat", "PRS92 latitude"),
    ("prs92_lon", "PRS92 longitude"),
    ("wgs84_lat", "WGS84 latitude"),
    ("wgs84_lon", "WGS84 longitude"),
    ("ptm_zone", "PTM zone"),
    ("ptm_east", "PTM easting (m)"),
    ("ptm_north", "PTM northing (m)"),
    ("ptm_check_resid_m", "Reprojection residual (m)"),
    ("source", "Source"),
    ("retrieved", "Retrieved"),
    ("dataset_version", "Dataset version"),
    ("legal_status", "Legal status"),
]
aliases = "\n".join(
    f'      <alias field="{f}" index="{i}" name="{html.escape(a)}"/>' for i, (f, a) in enumerate(FIELD_ALIASES)
)

MAPTIP = (
    "&lt;b&gt;[% \"pointref\" %]&lt;/b&gt;&lt;br/&gt;"
    "[% \"mon_type_label\" %] &amp;middot; [% \"municipality\" %]&lt;br/&gt;"
    "&lt;hr/&gt;PRS92: [% format_number(\"prs92_lat\",8) %], [% format_number(\"prs92_lon\",8) %]&lt;br/&gt;"
    "WGS84: [% format_number(\"wgs84_lat\",8) %], [% format_number(\"wgs84_lon\",8) %]&lt;br/&gt;"
    "PTM Z[% \"ptm_zone\" %]: E [% format_number(\"ptm_east\",3) %] / N [% format_number(\"ptm_north\",3) %]"
)


def vector_layer(lid, name, table, epsg, srsid, renderer_on=True, visible=True):
    return f"""<maplayer geometry="Point" type="vector" hasScaleBasedVisibilityFlag="0" refreshOnNotifyMessage=""
      simplifyDrawingHints="0" maxScale="0" minScale="100000000" simplifyLocal="1" simplifyMaxScale="1"
      readOnly="0" simplifyAlgorithm="0" simplifyDrawingTol="1" labelsEnabled="{1 if renderer_on else 0}"
      styleCategories="AllStyleCategories" autoRefreshMode="Disabled" wkbType="Point">
      <id>{lid}</id>
      <datasource>{GPKG}|layername={table}</datasource>
      <layername>{html.escape(name)}</layername>
      <srs>{srs_block(epsg, srsid)}</srs>
      <provider encoding="UTF-8">ogr</provider>
      <renderer-v2 forceraster="0" type="categorizedSymbol" enableorderby="0" symbollevels="0"
        referencescale="-1" attr="mon_type">
        <categories>
{categories}
        </categories>
        <symbols>
{symbols}
        </symbols>
      </renderer-v2>
      {LABELING if renderer_on else ''}
      <customproperties><Option type="Map">
        <Option type="QString" value="{MAPTIP.replace(chr(34), '&quot;')}" name="mapTip"/>
      </Option></customproperties>
      <mapTip>{MAPTIP}</mapTip>
      <fieldConfiguration/>
      <aliases>
{aliases}
      </aliases>
      <previewExpression>"pointref"</previewExpression>
      <layerGeometryType>0</layerGeometryType>
    </maplayer>"""


def xyz_layer(lid, name, url, attrib, zmax=19):
    ds = (f"crs=EPSG:3857&amp;format=image/png&amp;type=xyz&amp;url={html.escape(url)}"
          f"&amp;zmax={zmax}&amp;zmin=0&amp;http-header:referer=")
    return f"""<maplayer type="raster" hasScaleBasedVisibilityFlag="0" maxScale="0" minScale="1e+08"
      styleCategories="AllStyleCategories" autoRefreshMode="Disabled" refreshOnNotifyMessage="">
      <id>{lid}</id>
      <datasource>{ds}</datasource>
      <layername>{html.escape(name)}</layername>
      <srs>{srs_block(3857, 3857)}</srs>
      <provider>wms</provider>
      <noData/>
      <pipe>
        <provider><resampling enabled="false" maxOversampling="2" zoomedInResamplingMethod="nearestNeighbour"
          zoomedOutResamplingMethod="nearestNeighbour"/></provider>
        <rasterrenderer opacity="1" alphaBand="-1" type="singlebandcolordata" band="1" nodataColor=""/>
        <brightnesscontrast brightness="0" gamma="1" contrast="0"/>
        <huesaturation saturation="0" grayscaleMode="0" colorizeOn="0" colorizeStrength="100"/>
      </pipe>
      <abstract>{html.escape(attrib)}</abstract>
    </maplayer>"""


layers_xml = "\n".join([
    vector_layer(LAYER_ID, "Tie points (WGS84)", "tiepoints_wgs84", 4326, 3452),
    vector_layer(PRS_ID, "Tie points (PRS92 / PTM Zone 4 grid)", "tiepoints_ptm4", 3124, 3124, renderer_on=False),
    xyz_layer(SAT_ID, "Esri World Imagery",
              "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/%7Bz%7D/%7By%7D/%7Bx%7D",
              "Esri, Maxar, Earthstar Geographics", zmax=19),
    xyz_layer(OSM_ID, "OpenStreetMap",
              "https://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png",
              "(C) OpenStreetMap contributors", zmax=19),
])

tree = f"""<layer-tree-group>
    <customproperties><Option/></customproperties>
    <layer-tree-layer id="{LAYER_ID}" name="Tie points (WGS84)" source="{GPKG}|layername=tiepoints_wgs84"
      providerKey="ogr" checked="Qt::Checked" expanded="1" legend_split_behavior="0" patch_size="-1,-1">
      <customproperties><Option/></customproperties></layer-tree-layer>
    <layer-tree-layer id="{PRS_ID}" name="Tie points (PRS92 / PTM Zone 4 grid)" source="{GPKG}|layername=tiepoints_ptm4"
      providerKey="ogr" checked="Qt::Unchecked" expanded="0" legend_split_behavior="0" patch_size="-1,-1">
      <customproperties><Option/></customproperties></layer-tree-layer>
    <layer-tree-layer id="{SAT_ID}" name="Esri World Imagery" source="" providerKey="wms"
      checked="Qt::Checked" expanded="0" legend_split_behavior="0" patch_size="-1,-1">
      <customproperties><Option/></customproperties></layer-tree-layer>
    <layer-tree-layer id="{OSM_ID}" name="OpenStreetMap" source="" providerKey="wms"
      checked="Qt::Unchecked" expanded="0" legend_split_behavior="0" patch_size="-1,-1">
      <customproperties><Option/></customproperties></layer-tree-layer>
    <custom-order enabled="0">
      <item>{LAYER_ID}</item><item>{PRS_ID}</item><item>{SAT_ID}</item><item>{OSM_ID}</item>
    </custom-order>
  </layer-tree-group>"""

QGS = f"""<?xml version="1.0" encoding="UTF-8"?>
<qgis projectname="LandTek - Camarines Norte Tie Point Master Map" version="3.34.0-Prizren" saveDateTime="2026-09-21T00:00:00">
  <homePath path=""/>
  <title>LandTek - Camarines Norte Tie Point Master Map</title>
  <transaction mode="Disabled"/>
  <projectFlags set=""/>
  <projectCrs>{srs_block(3857, 3857)}</projectCrs>
  {tree}
  <snapping-settings unit="1" mode="2" tolerance="12" type="1" enabled="0" intersection-snapping="0"
    self-snapping="0" scaleDependencyMode="0" minScale="0" maxScale="0">
    <individual-layer-settings/>
  </snapping-settings>
  <relations/>
  <polymorphicRelations/>
  <mapcanvas name="theMapCanvas" annotationsVisible="1">
    <units>meters</units>
    <extent>
      <xmin>{XMIN:.4f}</xmin><ymin>{YMIN:.4f}</ymin><xmax>{XMAX:.4f}</xmax><ymax>{YMAX:.4f}</ymax>
    </extent>
    <rotation>0</rotation>
    <destinationsrs>{srs_block(3857, 3857)}</destinationsrs>
    <rendermaptile>0</rendermaptile>
  </mapcanvas>
  <projectModels/>
  <legend updateDrawingOrder="true"/>
  <mapViewDocks/>
  <projectlayers>
{layers_xml}
  </projectlayers>
  <layerorder>
    <layer id="{LAYER_ID}"/><layer id="{PRS_ID}"/><layer id="{SAT_ID}"/><layer id="{OSM_ID}"/>
  </layerorder>
  <properties>
    <Gui>
      <CanvasColor type="int">255</CanvasColor>
      <SelectionColorBluePart type="int">0</SelectionColorBluePart>
      <SelectionColorGreenPart type="int">255</SelectionColorGreenPart>
      <SelectionColorRedPart type="int">255</SelectionColorRedPart>
    </Gui>
    <Measure><Ellipsoid type="QString">EPSG:7008</Ellipsoid></Measure>
    <PositionPrecision>
      <Automatic type="bool">false</Automatic>
      <DecimalPlaces type="int">3</DecimalPlaces>
    </PositionPrecision>
    <SpatialRefSys><ProjectionsEnabled type="int">1</ProjectionsEnabled></SpatialRefSys>
  </properties>
  <visibility-presets/>
  <transformContext/>
  <projectMetadata>
    <identifier>landtek-cn-tiepoints</identifier>
    <title>LandTek - Camarines Norte Tie Point Master Map</title>
    <abstract>DENR-LMB survey tie points for Paracale and Mercedes, Camarines Norte, retrieved from the Geoportal Lot Plotter service. Published coordinates are PRS92 geographic (EPSG:4683); a WGS84 layer is provided for imagery overlay. Reference only - not a certified monument description.</abstract>
    <author>LandTek Mapping Division</author>
    <creation>2026-09-21T00:00:00</creation>
    <crs>{srs_block(3857, 3857)}</crs>
  </projectMetadata>
</qgis>
"""

os.makedirs(OUT, exist_ok=True)
qgs_path = f"{OUT}/cn_tiepoints_master.qgs"
open(qgs_path, "w").write(QGS)

# validate well-formedness
import xml.dom.minidom
xml.dom.minidom.parse(qgs_path)

with zipfile.ZipFile(f"{OUT}/cn_tiepoints_master.qgz", "w", zipfile.ZIP_DEFLATED) as z:
    z.write(qgs_path, "cn_tiepoints_master.qgs")
os.remove(qgs_path)
print("qgz written, XML valid")
