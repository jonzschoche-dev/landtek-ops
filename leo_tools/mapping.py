"""mapping — the LandTek Mapping subsystem (Flask blueprint).

Registered in leo_tools/server.py. Serves three surfaces off the same table
(`map_parcels`, deploy_683 — the absolute WGS84 client-map layer, distinct from
the relative survey-shape `parcels` table in scripts/parcels.py):

  OPS (behind nginx basic-auth, /ops/*):
    GET  /ops/map                     — parcel list + status
    GET  /ops/map/draw?parcel=CODE    — draw/edit a rough polygon on satellite
    POST /ops/map/save                — persist geometry + tier + area
    GET  /ops/map/parcels.geojson     — all parcels (optionally ?client=CODE)

  CLIENT (token-gated, /client/*, NO basic-auth — the trust boundary is the
  opaque token, resolved to exactly one client_code, exactly like the portal):
    GET  /client/<token>/map          — mobile map: their parcels + "Locate me"
    GET  /client/<token>/parcels.geojson

Geometry is GeoJSON in JSONB; no PostGIS. Area/centroid come from geo_math.py.
Point-in-polygon + distance-to-boundary + device GPS run in the browser.

Tile source is Esri World Imagery (no API key, ToS-clean satellite). To switch
to Google's tiles later, set TILE_URL/TILE_ATTRIB below — one line.
"""
from __future__ import annotations

import json

import psycopg2
from flask import Blueprint, abort, jsonify, request

from ops_dashboard import PG_DSN
import geo_math

# Reuse the client-portal token resolver — one token scheme, one trust boundary.
from client_access import _resolve_token  # opaque token -> client_code or None

bp = Blueprint("mapping", __name__)

# --- Tile source (swap here to change basemap everywhere) --------------------
TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
TILE_ATTRIB = "Imagery &copy; Esri, Maxar, Earthstar Geographics"


def _db():
    return psycopg2.connect(PG_DSN)


# ======================================================================
#  OPS surface (basic-auth gated by nginx /ops location)
# ======================================================================

@bp.route("/ops/map")
def ops_map_index():
    conn = _db(); cur = conn.cursor()
    cur.execute(
        "SELECT parcel_code, client_code, label, accuracy_tier, area_sqm, "
        "stated_area_sqm, area_flag, status FROM map_parcels ORDER BY client_code, parcel_code"
    )
    rows = cur.fetchall(); cur.close(); conn.close()
    trs = []
    for pc, cc, label, tier, area, stated, flag, status in rows:
        area_s = f"{area:,.0f}" if area else "—"
        stated_s = f"{stated:,.0f}" if stated else "—"
        tier_s = tier or "<i>unset</i>"
        flag_s = flag or ""
        trs.append(
            f"<tr><td><a href='/ops/map/draw?parcel={pc}'>{pc}</a></td>"
            f"<td>{cc}</td><td>{label or ''}</td><td>{tier_s}</td>"
            f"<td style='text-align:right'>{area_s}</td>"
            f"<td style='text-align:right'>{stated_s}</td>"
            f"<td>{flag_s}</td><td>{status}</td></tr>"
        )
    body = (
        "<h1>Mapping — parcels</h1>"
        "<p>Click a parcel to draw/edit its boundary. Tier <b>rough</b> = "
        "hand-placed, shows an APPROXIMATE banner to the client.</p>"
        "<table border=1 cellpadding=6 cellspacing=0>"
        "<tr><th>parcel</th><th>client</th><th>label</th><th>tier</th>"
        "<th>plotted m²</th><th>title m²</th><th>flag</th><th>status</th></tr>"
        + "".join(trs) + "</table>"
    )
    return _page("Mapping — parcels", body)


@bp.route("/ops/map/draw")
def ops_map_draw():
    parcel = (request.args.get("parcel") or "").strip()
    if not parcel:
        abort(400)
    conn = _db(); cur = conn.cursor()
    cur.execute(
        "SELECT parcel_code, client_code, label, geom_geojson, accuracy_tier, "
        "centroid_lat, centroid_lng, source_note FROM map_parcels WHERE parcel_code=%s",
        (parcel,),
    )
    row = cur.fetchone(); cur.close(); conn.close()
    if not row:
        abort(404)
    pc, cc, label, geom, tier, clat, clng, note = row
    geom_json = json.dumps(geom) if geom else "null"
    # Center on existing centroid, else on Camarines Norte (the active AO).
    lat = clat if clat is not None else 14.10
    lng = clng if clng is not None else 122.86
    return _DRAW_HTML.format(
        parcel=pc, client=cc, label=(label or pc), geom=geom_json,
        tier=(tier or "rough"), lat=lat, lng=lng,
        note=(note or ""), tile_url=TILE_URL, tile_attrib=TILE_ATTRIB,
    )


@bp.route("/ops/map/save", methods=["POST"])
def ops_map_save():
    data = request.get_json(silent=True) or {}
    parcel = (data.get("parcel_code") or "").strip()
    geom = data.get("geom_geojson")
    tier = (data.get("accuracy_tier") or "rough").strip()
    note = (data.get("source_note") or "").strip()
    plotted_by = (data.get("plotted_by") or "ops").strip()
    if not parcel or tier not in ("rough", "survey", "ortho"):
        return jsonify(ok=False, error="bad parcel or tier"), 400

    if geom is None:
        # Clear the geometry (un-plot).
        area = None; clat = clng = None; status = "awaiting_plot"
    else:
        try:
            area = round(geo_math.polygon_area_sqm(geom), 1)
            clat, clng = geo_math.polygon_centroid(geom)
        except Exception as e:  # degrade, don't crash
            return jsonify(ok=False, error=f"geometry error: {e}"), 400
        if not area:
            return jsonify(ok=False, error="polygon has no area"), 400
        status = "plotted"

    conn = _db(); conn.autocommit = True; cur = conn.cursor()
    cur.execute(
        "UPDATE map_parcels SET geom_geojson=%s, accuracy_tier=%s, area_sqm=%s, "
        "centroid_lat=%s, centroid_lng=%s, source_note=%s, plotted_by=%s, "
        "plotted_at=now(), updated_at=now(), status=%s WHERE parcel_code=%s",
        (json.dumps(geom) if geom is not None else None, tier if geom is not None else None,
         area, clat, clng, note, plotted_by, status, parcel),
    )
    n = cur.rowcount; cur.close(); conn.close()
    if not n:
        return jsonify(ok=False, error="no such parcel"), 404
    return jsonify(ok=True, parcel_code=parcel, area_sqm=area,
                   centroid=[clat, clng], status=status)


@bp.route("/ops/map/parcels.geojson")
def ops_parcels_geojson():
    client = (request.args.get("client") or "").strip()
    q = ("SELECT parcel_code, client_code, label, geom_geojson, accuracy_tier, "
         "area_sqm, stated_area_sqm FROM map_parcels WHERE geom_geojson IS NOT NULL")
    args = []
    if client:
        q += " AND client_code=%s"; args.append(client)
    conn = _db(); cur = conn.cursor(); cur.execute(q, args)
    rows = cur.fetchall(); cur.close(); conn.close()
    return jsonify(_features(rows))


# ======================================================================
#  CLIENT surface (token-gated; NO basic-auth; one token -> one client)
# ======================================================================

@bp.route("/client/<token>/parcels.geojson")
def client_parcels_geojson(token):
    client_code = _resolve_token(token)
    if not client_code:
        abort(404)
    conn = _db(); cur = conn.cursor()
    # map_parcels_client already excludes un-plotted rows and exposes `approximate`.
    cur.execute(
        "SELECT parcel_code, client_code, label, geom_geojson, accuracy_tier, "
        "area_sqm, stated_area_sqm FROM map_parcels_client WHERE client_code=%s",
        (client_code,),
    )
    rows = cur.fetchall(); cur.close(); conn.close()
    return jsonify(_features(rows))


@bp.route("/client/<token>/map")
def client_map(token):
    client_code = _resolve_token(token)
    if not client_code:
        abort(404)
    conn = _db(); cur = conn.cursor()
    cur.execute(
        "SELECT centroid_lat, centroid_lng, "
        "bool_or(accuracy_tier IS DISTINCT FROM 'ortho') "
        "FROM map_parcels_client WHERE client_code=%s "
        "GROUP BY centroid_lat, centroid_lng LIMIT 1",
        (client_code,),
    )
    row = cur.fetchone(); cur.close(); conn.close()
    lat = row[0] if row and row[0] is not None else 14.10
    lng = row[1] if row and row[1] is not None else 122.86
    resp = _CLIENT_HTML.format(
        token=token, lat=lat, lng=lng,
        tile_url=TILE_URL, tile_attrib=TILE_ATTRIB,
    )
    from flask import Response
    r = Response(resp, mimetype="text/html")
    r.headers["Referrer-Policy"] = "no-referrer"  # never leak the token
    return r


# ----------------------------------------------------------------------
#  helpers
# ----------------------------------------------------------------------

def _features(rows):
    feats = []
    for pc, cc, label, geom, tier, area, stated in rows:
        g = geom if isinstance(geom, dict) else (json.loads(geom) if geom else None)
        if not g:
            continue
        geometry = g.get("geometry", g)
        feats.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "parcel_code": pc, "label": label or pc,
                "accuracy_tier": tier,
                "approximate": (tier != "ortho"),
                "area_sqm": area, "stated_area_sqm": stated,
            },
        })
    return {"type": "FeatureCollection", "features": feats}


def _page(title, body):
    return (
        "<!doctype html><html><head><meta charset=utf-8>"
        f"<title>{title}</title><meta name=viewport content='width=device-width,initial-scale=1'>"
        "<style>body{font-family:system-ui,sans-serif;margin:24px;color:#1a1a1a}"
        "table{border-collapse:collapse;font-size:14px}th{background:#f0f0f0}"
        "a{color:#0645ad}h1{font-size:20px}</style></head><body>" + body + "</body></html>"
    )


# --- OPS draw tool (Leaflet + Leaflet-Geoman, no API key) --------------------
_DRAW_HTML = """<!doctype html><html><head><meta charset=utf-8>
<title>Draw {parcel}</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<link rel=stylesheet href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel=stylesheet href="https://unpkg.com/@geoman-io/leaflet-geoman-free@2.15.0/dist/leaflet-geoman.css">
<style>
 body{{margin:0;font-family:system-ui,sans-serif}}
 #bar{{padding:10px 14px;background:#111;color:#fff;display:flex;gap:12px;align-items:center;flex-wrap:wrap}}
 #map{{height:calc(100vh - 116px)}}
 select,input,button{{font-size:14px;padding:6px}}
 button{{background:#2563eb;color:#fff;border:0;border-radius:6px;cursor:pointer}}
 #status{{padding:8px 14px;font-size:13px;background:#f5f5f5}}
 .muted{{color:#9ca3af}}
</style></head><body>
<div id=bar>
 <b>{label}</b> <span class=muted>({parcel} · {client})</span>
 <label>tier
  <select id=tier>
   <option value=rough>rough (approximate)</option>
   <option value=survey>survey</option>
   <option value=ortho>ortho</option>
  </select></label>
 <input id=note placeholder="source note" value="{note}" size=30>
 <button onclick=save()>Save boundary</button>
 <button onclick=clearGeom() style="background:#6b7280">Un-plot</button>
</div>
<div id=status>Draw the parcel polygon, then Save. Existing geometry (if any) is loaded for editing.</div>
<div id=map></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/@geoman-io/leaflet-geoman-free@2.15.0/dist/leaflet-geoman.min.js"></script>
<script>
const PARCEL={parcel!r}, EXISTING={geom};
document.getElementById('tier').value={tier!r};
const map=L.map('map').setView([{lat},{lng}],17);
L.tileLayer("{tile_url}",{{maxZoom:21,attribution:"{tile_attrib}"}}).addTo(map);
let layer=null;
function setLayer(l){{ if(layer) map.removeLayer(layer); layer=l; }}
if(EXISTING){{
  const gj=EXISTING.geometry||EXISTING;
  const gl=L.geoJSON(gj).addTo(map); setLayer(gl);
  try{{map.fitBounds(gl.getBounds(),{{maxZoom:19}});}}catch(e){{}}
}}
map.pm.addControls({{position:'topleft',drawPolygon:true,editMode:true,
  dragMode:false,cutPolygon:false,removalMode:true,drawMarker:false,
  drawPolyline:false,drawRectangle:false,drawCircle:false,drawCircleMarker:false,drawText:false}});
map.on('pm:create',e=>{{ setLayer(e.layer); }});
function currentGeoJSON(){{
  if(layer&&layer.toGeoJSON){{
    const g=layer.toGeoJSON();
    if(g.type==='FeatureCollection') return g.features[0].geometry;
    return g.geometry||g;
  }}
  return null;
}}
function save(){{
  const geom=currentGeoJSON();
  if(!geom){{alert('Draw a polygon first');return;}}
  fetch('/ops/map/save',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{parcel_code:PARCEL,geom_geojson:geom,
      accuracy_tier:document.getElementById('tier').value,
      source_note:document.getElementById('note').value}})}})
   .then(r=>r.json()).then(j=>{{
     document.getElementById('status').textContent = j.ok
       ? ('Saved. Plotted area '+Math.round(j.area_sqm).toLocaleString()+' m² · centroid '+j.centroid.map(x=>x.toFixed(5)).join(', '))
       : ('Error: '+j.error);
   }});
}}
function clearGeom(){{
  if(!confirm('Remove this parcel\\'s boundary?'))return;
  fetch('/ops/map/save',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{parcel_code:PARCEL,geom_geojson:null}})}})
   .then(r=>r.json()).then(j=>{{document.getElementById('status').textContent=j.ok?'Un-plotted.':'Error: '+j.error;
     if(layer)map.removeLayer(layer);layer=null;}});
}}
</script></body></html>"""


# --- CLIENT map (mobile; parcels + "Locate me" blue dot) ---------------------
_CLIENT_HTML = """<!doctype html><html><head><meta charset=utf-8>
<title>My property</title>
<meta name=viewport content="width=device-width,initial-scale=1,maximum-scale=1">
<link rel=stylesheet href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
 html,body{{margin:0;height:100%;font-family:system-ui,sans-serif}}
 #map{{position:absolute;top:0;bottom:0;left:0;right:0}}
 #banner{{position:absolute;z-index:1000;top:0;left:0;right:0;background:#b45309;
   color:#fff;font-size:13px;padding:7px 12px;text-align:center;display:none}}
 #locate{{position:absolute;z-index:1000;bottom:22px;right:14px;background:#2563eb;
   color:#fff;border:0;border-radius:28px;padding:14px 18px;font-size:15px;
   box-shadow:0 2px 8px rgba(0,0,0,.3);cursor:pointer}}
 #readout{{position:absolute;z-index:1000;bottom:22px;left:14px;right:120px;
   background:rgba(17,17,17,.82);color:#fff;font-size:13px;padding:9px 12px;
   border-radius:10px;display:none}}
</style></head><body>
<div id=banner></div>
<div id=readout></div>
<button id=locate onclick=locate()>📍 Locate me</button>
<div id=map></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const TOKEN={token!r};
const map=L.map('map',{{zoomControl:true}}).setView([{lat},{lng}],17);
L.tileLayer("{tile_url}",{{maxZoom:21,attribution:"{tile_attrib}"}}).addTo(map);
let RINGS=[];               // [[ [lat,lng],... ], ...] one per parcel, for point-in-polygon
let approximate=false;
fetch('/client/'+TOKEN+'/parcels.geojson').then(r=>r.json()).then(fc=>{{
  if(!fc.features||!fc.features.length){{
    document.getElementById('readout').style.display='block';
    document.getElementById('readout').textContent='Your parcel boundary is not published yet.';
    return;
  }}
  const gl=L.geoJSON(fc,{{style:f=>({{color:'#facc15',weight:3,fillOpacity:0.12}}),
    onEachFeature:(f,lyr)=>{{
      const p=f.properties;
      if(p.approximate) approximate=true;
      const area=p.area_sqm?Math.round(p.area_sqm).toLocaleString()+' m²':'';
      lyr.bindPopup('<b>'+(p.label||'')+'</b><br>'+area+(p.approximate?'<br><i>approximate</i>':''));
      // collect exterior ring as [lat,lng] for on-device inside/outside test
      const g=f.geometry; const ring=(g.type==='Polygon')?g.coordinates[0]:null;
      if(ring) RINGS.push(ring.map(c=>[c[1],c[0]]));
    }}}}).addTo(map);
  try{{map.fitBounds(gl.getBounds(),{{maxZoom:19,padding:[30,30]}});}}catch(e){{}}
  if(approximate){{
    const b=document.getElementById('banner');
    b.style.display='block';
    b.textContent='APPROXIMATE location — not a survey. Precise boundaries follow the drone survey.';
  }}
}});

let meMarker=null,meAccuracy=null;
function locate(){{
  if(!navigator.geolocation){{alert('Location not available on this device');return;}}
  navigator.geolocation.getCurrentPosition(pos=>{{
    const lat=pos.coords.latitude,lng=pos.coords.longitude,acc=pos.coords.accuracy;
    if(meMarker)map.removeLayer(meMarker);
    if(meAccuracy)map.removeLayer(meAccuracy);
    meMarker=L.circleMarker([lat,lng],{{radius:8,color:'#fff',weight:2,fillColor:'#2563eb',fillOpacity:1}}).addTo(map);
    meAccuracy=L.circle([lat,lng],{{radius:acc,color:'#2563eb',weight:1,fillOpacity:0.08}}).addTo(map);
    map.setView([lat,lng],19);
    report(lat,lng,acc);
  }},err=>{{alert('Could not get your location: '+err.message);}},
  {{enableHighAccuracy:true,timeout:15000,maximumAge:0}});
}}
function report(lat,lng,acc){{
  let inside=false,minEdge=Infinity;
  for(const ring of RINGS){{
    if(pointInRing(lat,lng,ring)) inside=true;
    minEdge=Math.min(minEdge,distToRing(lat,lng,ring));
  }}
  const el=document.getElementById('readout');
  el.style.display='block';
  const d=Math.round(minEdge);
  el.innerHTML = (inside
      ? '✅ You are <b>inside</b> your property (~'+d+' m from the nearest edge).'
      : '↗️ You are <b>outside</b> — nearest boundary ~'+d+' m away.')
    + '<br><span style="opacity:.7">GPS accuracy ±'+Math.round(acc)+' m'
    + (approximate?' · boundary is approximate':'')+'</span>';
}}
// ray-casting point-in-polygon on [lat,lng] ring
function pointInRing(lat,lng,ring){{
  let inside=false;
  for(let i=0,j=ring.length-1;i<ring.length;j=i++){{
    const yi=ring[i][0],xi=ring[i][1],yj=ring[j][0],xj=ring[j][1];
    if(((yi>lat)!=(yj>lat))&&(lng<(xj-xi)*(lat-yi)/(yj-yi)+xi)) inside=!inside;
  }}
  return inside;
}}
// approx meters from point to ring edges (local equirectangular)
function distToRing(lat,lng,ring){{
  const R=6378137, la=lat*Math.PI/180, cos=Math.cos(la);
  const px=lng*Math.PI/180*R*cos, py=lat*Math.PI/180*R;
  let best=Infinity;
  for(let i=0,j=ring.length-1;i<ring.length;j=i++){{
    const ax=ring[i][1]*Math.PI/180*R*cos, ay=ring[i][0]*Math.PI/180*R;
    const bx=ring[j][1]*Math.PI/180*R*cos, by=ring[j][0]*Math.PI/180*R;
    best=Math.min(best,segDist(px,py,ax,ay,bx,by));
  }}
  return best;
}}
function segDist(px,py,ax,ay,bx,by){{
  const dx=bx-ax,dy=by-ay, l2=dx*dx+dy*dy;
  let t=l2?((px-ax)*dx+(py-ay)*dy)/l2:0; t=Math.max(0,Math.min(1,t));
  const cx=ax+t*dx,cy=ay+t*dy;
  return Math.hypot(px-cx,py-cy);
}}
</script></body></html>"""
