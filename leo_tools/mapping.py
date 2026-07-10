"""mapping — the LandTek Mapping subsystem (Flask blueprint).

Registered in leo_tools/server.py. Serves three surfaces off the same table
(`map_parcels`, deploy_683 — the absolute WGS84 client-map layer, distinct from
the relative survey-shape `parcels` table in scripts/parcels.py):

  OPS (behind nginx basic-auth, /ops/*):
    GET  /ops/map                     — parcel list + status
    GET  /ops/map/draw?parcel=CODE    — draw/edit a rough polygon on satellite
    POST /ops/map/save                — persist geometry + tier + area
    GET  /ops/map/parcels.geojson     — all parcels (optionally ?client=CODE)
    GET  /ops/map/consensus[?title=]  — consensus console (same renderer the client sees)
    GET  /ops/map/bundle/<title>.json — consensus bundle (ops, unscoped)
    GET  /ops/map/proposals           — review client course proposals
    POST /ops/map/proposals/act       — accept (→ operator correction row) / reject

  CLIENT (token-gated, /client/*, NO basic-auth — the trust boundary is the
  opaque token, resolved to exactly one client_code, exactly like the portal):
    GET  /client/<token>/map                — premium mobile map: layer control
         (Esri default · optional Google sat/hybrid · drone-ortho overlays),
         "Locate me", boundary-evidence sheet (per-course consensus + source stack),
         one-tap correction proposals, offline shell
    GET  /client/<token>/parcels.geojson
    GET  /client/<token>/bundle/<title>.json — consensus bundle, client-scoped
    POST /client/<token>/propose            — flag a course (→ pending ops review; A6)
    GET  /client/<token>/manifest.json · /client/<token>/sw.js — PWA shell

Geometry is GeoJSON in JSONB; no PostGIS. Area/centroid come from geo_math.py.
Point-in-polygon + distance-to-boundary + device GPS run in the browser (A10:
location is ephemeral + client-side; nothing is ever posted or stored).

Basemaps: Esri World Imagery is the keyless FREE default (never break it). Google
satellite/hybrid appear as optional reference layers only when GOOGLE_MAPS_KEY is
set (official Map Tiles API session flow) — visual reference ONLY, never a
GeometrySource. The Google-Earth history deep-link ships dark behind
MAPPING_EARTH_LINK (A11 names Earth/Maps links in its exposure ban).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.request

import re

import psycopg2
from flask import Blueprint, Response, abort, jsonify, request

from ops_dashboard import PG_DSN
import geo_math

# Reuse the client-portal token resolver — one token scheme, one trust boundary.
from client_access import _resolve_token  # opaque token -> client_code or None

# The consensus engine (scripts/geometry_consensus.py) is the single source of the
# course-level truth model; the map surfaces RENDER its bundle, never re-derive it.
_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
import geometry_consensus as GC

bp = Blueprint("mapping", __name__)


def _cfg_js(cfg: dict) -> str:
    """JSON for embedding inside a <script> block: escape </ so a value can never
    close the script tag (script-context XSS)."""
    return json.dumps(cfg).replace("</", "<\\/")

# --- Tile sources ------------------------------------------------------------
# Esri World Imagery is the FREE, keyless default and must always work (never break
# this path). Google layers are OPTIONAL reference basemaps via the official Map
# Tiles API session flow — they exist only when GOOGLE_MAPS_KEY is configured, and
# they are VISUAL REFERENCE ONLY (never a GeometrySource, never an accuracy tier).
TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
TILE_ATTRIB = "Imagery &copy; Esri, Maxar, Earthstar Geographics"
GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_KEY", "")
# A11 names "Earth/Maps link" in its exposure ban; the historical-imagery deep-link
# therefore ships DARK until the operator flips this (capability built, switch held).
EARTH_LINK = os.getenv("MAPPING_EARTH_LINK", "off").lower() in ("on", "1", "true")
_GSESS = {}       # mapType -> (tile_url_template, expiry_epoch)
_GSESS_FAIL = {}  # mapType -> last_failure_epoch (negative cache, 300s)


def _google_tile_template(map_type):
    """Leaflet tile URL template for Google satellite/hybrid via the official Map Tiles
    API (createSession → session-scoped tile URLs). Returns None when no key is set or
    the mint fails — the map silently stays Esri-only."""
    if not GOOGLE_MAPS_KEY:
        return None
    cached = _GSESS.get(map_type)
    if cached and cached[1] > time.time() + 120:
        return cached[0]
    if time.time() - _GSESS_FAIL.get(map_type, 0) < 300:
        return None   # minted recently and failed — don't stall every request retrying
    body = {"mapType": "satellite", "language": "en-US", "region": "PH"}
    if map_type == "hybrid":
        body["layerTypes"] = ["layerRoadmap"]
    try:
        req = urllib.request.Request(
            "https://tile.googleapis.com/v1/createSession?key=" + GOOGLE_MAPS_KEY,
            data=json.dumps(body).encode(),
            headers={"content-type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=8) as r:
            out = json.loads(r.read())
        sess = out["session"]
        expiry = int(out.get("expiry", time.time() + 3600))
        tpl = ("https://tile.googleapis.com/v1/2dtiles/{z}/{x}/{y}?session="
               + sess + "&key=" + GOOGLE_MAPS_KEY)
        _GSESS[map_type] = (tpl, expiry)
        return tpl
    except Exception:
        _GSESS_FAIL[map_type] = time.time()
        return None


def _client_titles(cur, client_code):
    """Titles whose course assertions belong to this client (A5/A9: scope resolved via
    _client_of on the matter, exactly the V6 isolation semantics)."""
    cur.execute("SELECT DISTINCT title_no FROM parcel_courses "
                "WHERE _client_of(matter_code) = %s ORDER BY 1", (client_code,))
    return [r[0] for r in cur.fetchall()]


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
        "<p><a href='/ops/map/consensus'>consensus console</a> · "
        "<a href='/ops/map/proposals'>client proposals</a></p>"
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
        "SELECT centroid_lat, centroid_lng FROM map_parcels_client "
        "WHERE client_code=%s AND centroid_lat IS NOT NULL LIMIT 1", (client_code,))
    row = cur.fetchone()
    lat = row[0] if row else 14.10
    lng = row[1] if row else 122.86
    cur.execute("SELECT parcel_code, label, ortho_tiles_url FROM map_parcels_client "
                "WHERE client_code=%s AND ortho_tiles_url IS NOT NULL", (client_code,))
    orthos = [{"label": (r[1] or r[0]) + " — drone ortho", "url": r[2]} for r in cur.fetchall()]
    titles = _client_titles(cur, client_code)
    cur.close(); conn.close()
    cfg = {
        "token": token, "lat": lat, "lng": lng,
        "tiles": {"esri": TILE_URL, "esri_attrib": TILE_ATTRIB,
                  "gsat": _google_tile_template("satellite"),
                  "ghyb": _google_tile_template("hybrid")},
        "orthos": orthos,
        "titles": titles,           # titles with boundary-evidence bundles, client-scoped
        "earth": EARTH_LINK,
        "can_propose": True,
    }
    html = (_CLIENT_HTML
            .replace("__CFG__", _cfg_js(cfg))
            .replace("__PANEL_JS__", _PANEL_JS)
            .replace("__PANEL_CSS__", _PANEL_CSS))
    r = Response(html, mimetype="text/html")
    r.headers["Referrer-Policy"] = "no-referrer"  # never leak the token
    return r


@bp.route("/client/<token>/bundle/<path:title_no>.json")
def client_bundle(token, title_no):
    client_code = _resolve_token(token)
    if not client_code:
        abort(404)
    conn = _db(); cur = conn.cursor()
    allowed = title_no in _client_titles(cur, client_code)
    cur.close(); conn.close()
    if not allowed:
        abort(404)   # same shape as unknown token: leak nothing (A5/A9)
    return jsonify(GC.bundle(title_no, client_code=client_code))


@bp.route("/client/<token>/propose", methods=["POST"])
def client_propose(token):
    """A client flags a course they believe is wrong. This NEVER writes geometry or a
    correction (A6): it lands in parcel_course_proposals, pending, for the operator to
    review at /ops/map/proposals. client_code comes from the token — never the body.
    Deliberately accepts NO location fields (A10)."""
    client_code = _resolve_token(token)
    if not client_code:
        abort(404)
    d = request.get_json(silent=True) or {}
    title_no = (d.get("title_no") or "").strip()[:40]
    note = (d.get("note") or "").strip()
    if not title_no or not (3 <= len(note) <= 600):
        return jsonify(ok=False, error="need title_no and a note (3-600 chars)"), 400
    lot = (d.get("lot") or "A").strip()[:4]
    try:
        position = int(d["position"]) if d.get("position") not in (None, "") else None
    except (TypeError, ValueError):
        position = None
    bearing = (d.get("bearing") or "").strip()[:60] or None
    target_call = (d.get("target_call") or "").strip()[:80] or None
    try:
        dist = float(d["distance_m"]) if d.get("distance_m") not in (None, "") else None
    except (TypeError, ValueError):
        dist = None
    conn = _db(); conn.autocommit = True; cur = conn.cursor()
    if title_no not in _client_titles(cur, client_code):
        cur.close(); conn.close(); abort(404)
    cur.execute("SELECT count(*) FROM parcel_course_proposals "
                "WHERE client_code=%s AND status='pending'", (client_code,))
    if cur.fetchone()[0] >= 25:
        cur.close(); conn.close()
        return jsonify(ok=False, error="too many pending proposals — ops will review soon"), 429
    cur.execute(
        "INSERT INTO parcel_course_proposals (title_no, lot, position, note, "
        "proposed_bearing, proposed_distance_m, client_code, target_call) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (title_no, lot, position, note, bearing, dist, client_code, target_call))
    pid = cur.fetchone()[0]
    cur.close(); conn.close()
    return jsonify(ok=True, id=pid, status="pending",
                   msg="Thank you — flagged for LandTek review.")


@bp.route("/client/<token>/manifest.json")
def client_manifest(token):
    if not _resolve_token(token):
        abort(404)
    return jsonify({
        "name": "My Property — LandTek", "short_name": "My Property",
        "start_url": f"/client/{token}/map", "scope": f"/client/{token}/",
        "display": "standalone", "background_color": "#111111",
        "theme_color": "#111111", "icons": [],
    })


@bp.route("/client/<token>/sw.js")
def client_sw(token):
    if not _resolve_token(token):
        abort(404)
    # Cache name is token-hashed so a shared device can never serve one client's cached
    # parcels to another token's page (A5/A9). Caches only app-shell + this client's
    # bundle/geojson responses — no tile hoarding, no location, nothing cross-origin
    # except the CDN shell.
    cache = "ltk-map-" + hashlib.sha256(token.encode()).hexdigest()[:16]
    js = _SW_JS.replace("__CACHE__", cache).replace("__SCOPE__", f"/client/{token}/")
    r = Response(js, mimetype="application/javascript")
    r.headers["Referrer-Policy"] = "no-referrer"
    return r


# ======================================================================
#  OPS consensus console + proposal review (basic-auth gated by nginx)
# ======================================================================

@bp.route("/ops/map/bundle/<path:title_no>.json")
def ops_bundle(title_no):
    return jsonify(GC.bundle(title_no))


@bp.route("/ops/map/consensus")
def ops_consensus():
    title = (request.args.get("title") or "").strip()
    if not title:
        conn = _db(); cur = conn.cursor()
        cur.execute("SELECT title_no, count(*), count(DISTINCT source_doc_id) "
                    "FROM parcel_courses GROUP BY 1 ORDER BY 1")
        rows = cur.fetchall(); cur.close(); conn.close()
        body = ("<h1>Consensus console</h1><p>Titles with course assertions:</p><ul>"
                + "".join(f"<li><a href='/ops/map/consensus?title={t}'>{t}</a> — "
                          f"{n} courses from {d} doc(s)</li>" for t, n, d in rows)
                + "</ul><p><a href='/ops/map'>← parcels</a> · "
                  "<a href='/ops/map/proposals'>client proposals</a></p>")
        return _page("Consensus console", body)
    if not re.match(r"^[A-Za-z0-9\-_. /#]{1,40}$", title):
        abort(400)
    conn = _db(); cur = conn.cursor()
    cur.execute("SELECT 1 FROM parcel_courses WHERE title_no=%s LIMIT 1", (title,))
    known = cur.fetchone(); cur.close(); conn.close()
    if not known:
        abort(404)
    cfg = {"title": title, "bundle_url": f"/ops/map/bundle/{title}.json", "ops": True}
    html = (_OPS_CONSENSUS_HTML
            .replace("__CFG__", _cfg_js(cfg))
            .replace("__PANEL_JS__", _PANEL_JS)
            .replace("__PANEL_CSS__", _PANEL_CSS))
    return Response(html, mimetype="text/html")


@bp.route("/ops/map/proposals")
def ops_proposals():
    conn = _db(); cur = conn.cursor()
    cur.execute("SELECT id, title_no, lot, position, note, proposed_bearing, "
                "proposed_distance_m, client_code, status, created_at::date "
                "FROM parcel_course_proposals ORDER BY (status='pending') DESC, id DESC LIMIT 100")
    rows = cur.fetchall(); cur.close(); conn.close()
    import html as _html
    trs = []
    for pid, t, lot, pos, note, brg, dist, cc, status, dt in rows:
        act = ""
        if status == "pending":
            act = (f"<button onclick=\"act({pid},'accept')\">Accept</button> "
                   f"<button onclick=\"act({pid},'reject')\" style='background:#6b7280'>Reject</button>")
        # note + bearing are CLIENT-authored strings — always escape (stored-XSS guard).
        sugg = _html.escape(f"{brg or ''} {str(dist) + ' m' if dist else ''}".strip()) or "—"
        trs.append(f"<tr><td>{pid}</td><td>{_html.escape(t or '')}</td><td>{_html.escape(lot or '')}</td>"
                   f"<td>{pos or '—'}</td><td>{_html.escape((note or '')[:140])}</td><td>{sugg}</td>"
                   f"<td>{_html.escape(cc or '')}</td><td>{status}</td><td>{dt}</td><td>{act}</td></tr>")
    body = ("<h1>Client course proposals</h1>"
            "<p>Accepting a proposal WITH a structured bearing+distance writes a real "
            "<code>parcel_course_corrections</code> row (operator provenance, reason cites the "
            "proposal). Accepting one without just marks it accepted — apply via the "
            "<code>geometry_consensus.py correct</code> CLI. Reject requires a note.</p>"
            "<table border=1 cellpadding=6 cellspacing=0><tr><th>id</th><th>title</th><th>lot</th>"
            "<th>pos</th><th>note</th><th>suggestion</th><th>client</th><th>status</th>"
            "<th>date</th><th></th></tr>" + "".join(trs) + "</table>"
            "<p><a href='/ops/map/consensus'>← consensus console</a></p>"
            "<script>function act(id,action){var note=prompt(action+' note (reason):')||'';"
            "if(action==='reject'&&!note){alert('Reject needs a note');return;}"
            "fetch('/ops/map/proposals/act',{method:'POST',headers:{'Content-Type':'application/json'},"
            "body:JSON.stringify({id:id,action:action,note:note})}).then(r=>r.json())"
            ".then(j=>{alert(j.ok?('OK: '+(j.msg||action)):('Error: '+j.error));location.reload();});}"
            "</script>")
    return _page("Client course proposals", body)


@bp.route("/ops/map/proposals/act", methods=["POST"])
def ops_proposals_act():
    d = request.get_json(silent=True) or {}
    try:
        pid = int(d.get("id"))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="bad id"), 400
    action = d.get("action")
    note = (d.get("note") or "").strip()[:400]
    if action not in ("accept", "reject"):
        return jsonify(ok=False, error="action must be accept|reject"), 400
    conn = _db(); conn.autocommit = True; cur = conn.cursor()
    cur.execute("SELECT title_no, lot, position, note, proposed_bearing, proposed_distance_m, "
                "target_call FROM parcel_course_proposals WHERE id=%s AND status='pending'", (pid,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return jsonify(ok=False, error="no such pending proposal"), 404
    title_no, lot, pos, pnote, brg, dist, target_call = row
    msg, corr_id = action + "ed", None
    if action == "accept" and brg and dist and pos:
        parsed = list(GC.sg.parse_calls(f"{brg}, {float(dist):.2f} m"))
        if parsed:
            az, dm = parsed[0]
            cur.execute(
                "INSERT INTO parcel_course_corrections (title_no, lot, position, action, "
                "azimuth_deg, distance_m, raw_call, reason, created_by, expected_call) "
                "VALUES (%s,%s,%s,'replace',%s,%s,%s,%s,'jonathan',%s) "
                "ON CONFLICT (title_no, lot, position, action) DO NOTHING RETURNING id",
                (title_no, lot, pos, az, dm, brg,
                 f"approved client proposal #{pid}: {pnote[:180]}", target_call))
            got = cur.fetchone()
            if got:
                corr_id = got[0]
                msg = f"accepted — correction #{corr_id} written (lot {lot} pos {pos})"
            else:
                # A6: an operator correction already exists at this key — NEVER clobber
                # it from a proposal click; resolve deliberately via the CLI.
                cur.close(); conn.close()
                return jsonify(ok=False, error=f"a correction already exists at lot {lot} "
                               f"pos {pos} — resolve via geometry_consensus.py correct"), 409
        else:
            msg = "accepted (bearing unparseable — apply via correct CLI)"
    cur.execute("UPDATE parcel_course_proposals SET status=%s, reviewed_by='jonathan', "
                "reviewed_at=now(), review_note=%s, correction_id=%s WHERE id=%s",
                ("accepted" if action == "accept" else "rejected", note, corr_id, pid))
    cur.close(); conn.close()
    return jsonify(ok=True, msg=msg)


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


# ==============================================================================
#  v2 templates — rendered via TOKEN REPLACEMENT (__CFG__ / __PANEL_JS__ /
#  __PANEL_CSS__), NOT .format(), so the JS/CSS braces below need no escaping.
#  _PANEL_* are shared verbatim by the client map sheet and the ops console: what
#  the client sees IS what ops reviews — one renderer, one truth model.
# ==============================================================================

_PANEL_CSS = """
 .chip{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;color:#fff;white-space:nowrap}
 .chip.cor{background:#16a34a}.chip.sin{background:#d97706}.chip.op{background:#2563eb}
 #sheet{position:fixed;z-index:1200;left:0;right:0;bottom:-100%;max-height:78%;
   background:#fff;color:#111;border-radius:14px 14px 0 0;box-shadow:0 -4px 24px rgba(0,0,0,.4);
   transition:bottom .25s ease;overflow-y:auto;-webkit-overflow-scrolling:touch}
 #sheet.open{bottom:0}
 #sheet header{position:sticky;top:0;background:#fff;padding:10px 14px;border-bottom:1px solid #e5e7eb;
   display:flex;justify-content:space-between;align-items:center;z-index:5}
 #sheet h2{margin:0;font-size:16px}
 .lot{padding:10px 14px;border-bottom:6px solid #f3f4f6}
 .lotstats{font-size:12px;color:#374151;margin:6px 0}
 .aff{font-size:12px;margin:2px 0}
 .aff.ok{color:#15803d}.aff.bad{color:#b91c1c}.aff.na{color:#6b7280}
 .course{display:flex;gap:8px;align-items:center;padding:7px 2px;border-top:1px solid #f3f4f6;
   font-size:13px;cursor:pointer}
 .course .pos{color:#6b7280;width:26px;text-align:right;flex:none}
 .course.sel{background:#f0f9ff}
 .detail{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:8px 10px;
   font-size:12px;margin:4px 0 8px}
 .detail .src{margin:4px 0;padding:4px 6px;background:#fff;border-radius:6px;border:1px solid #e5e7eb}
 .flagbtn{background:#dc2626;color:#fff;border:0;border-radius:6px;padding:7px 10px;
   font-size:12px;cursor:pointer;margin-top:6px}
 .conflict{font-size:12px;color:#b91c1c;padding:4px 2px}
 svg.schem{width:100%;max-width:340px;display:block;margin:4px auto;background:#f8fafc;border-radius:8px}
 .legend{font-size:11px;color:#374151;display:flex;gap:10px;flex-wrap:wrap;margin:4px 0}
 .legend span::before{content:'\\2501 ';font-weight:bold}
 .lg-cor::before{color:#16a34a}.lg-sin::before{color:#d97706}.lg-op::before{color:#2563eb}
"""

_PANEL_JS = """
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,
  function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
var STATUS_META={corroborated:['cor','\\u2714 corroborated'],single:['sin','\\u25cb single source'],
  operator:['op','\\ud83d\\udd27 operator']};
function ringPoints(courses){
  var x=0,y=0,pts=[[0,0]];
  for(var i=0;i<courses.length;i++){var c=courses[i],r=c.azimuth*Math.PI/180;
    x+=c.distance_m*Math.sin(r); y+=c.distance_m*Math.cos(r); pts.push([x,y]);}
  return pts;
}
function schematic(lot){
  var pts=ringPoints(lot.courses);
  if(pts.length<3) return null;
  var xs=pts.map(function(p){return p[0];}),ys=pts.map(function(p){return p[1];});
  var minx=Math.min.apply(null,xs),maxx=Math.max.apply(null,xs);
  var miny=Math.min.apply(null,ys),maxy=Math.max.apply(null,ys);
  var w=(maxx-minx)||1,h=(maxy-miny)||1,S=300,pad=16,sc=Math.min((S-2*pad)/w,(S-2*pad)/h);
  function X(x){return pad+(x-minx)*sc;} function Y(y){return S-pad-(y-miny)*sc;} // north up
  var NS='http://www.w3.org/2000/svg';
  var svg=document.createElementNS(NS,'svg');
  svg.setAttribute('viewBox','0 0 '+S+' '+S); svg.setAttribute('class','schem');
  var colors={corroborated:'#16a34a',single:'#d97706',operator:'#2563eb'};
  var conflictPos={};(lot.conflicts||[]).forEach(function(c){conflictPos[c.pos]=1;});
  lot.courses.forEach(function(c,i){
    var l=document.createElementNS(NS,'line');
    l.setAttribute('x1',X(pts[i][0]));l.setAttribute('y1',Y(pts[i][1]));
    l.setAttribute('x2',X(pts[i+1][0]));l.setAttribute('y2',Y(pts[i+1][1]));
    l.setAttribute('stroke',colors[c.status]||'#6b7280');
    l.setAttribute('stroke-width',conflictPos[c.pos]?5:3);
    l.setAttribute('stroke-linecap','round'); l.style.cursor='pointer';
    l.addEventListener('click',function(){selectCourse(lot,c.pos);});
    svg.appendChild(l);
    if(conflictPos[c.pos]){
      var m=document.createElementNS(NS,'circle');
      m.setAttribute('cx',X(pts[i][0]));m.setAttribute('cy',Y(pts[i][1]));
      m.setAttribute('r',6);m.setAttribute('fill','none');
      m.setAttribute('stroke','#dc2626');m.setAttribute('stroke-width',2);
      svg.appendChild(m);
    }
  });
  var cap=document.createElementNS(NS,'text');
  cap.setAttribute('x',S/2);cap.setAttribute('y',S-3);cap.setAttribute('text-anchor','middle');
  cap.setAttribute('font-size','10');cap.setAttribute('fill','#6b7280');
  cap.textContent='to scale \\u00b7 north up \\u00b7 \\u2248'+Math.round(Math.max(w,h))+' m across';
  svg.appendChild(cap);
  return svg;
}
function selectCourse(lot,pos){
  var el=document.getElementById('lot-'+(lot._pfx||'')+lot.lot+'-c-'+pos);
  if(!el) return;
  var sel=document.querySelectorAll('.course.sel');
  for(var i=0;i<sel.length;i++) sel[i].classList.remove('sel');
  el.classList.add('sel'); el.scrollIntoView({block:'center',behavior:'smooth'});
  var det=el.nextElementSibling;
  if(det&&det.classList.contains('detail')) det.style.display='block';
}
function renderLot(b,lot,root,propose){
  var div=document.createElement('div'); div.className='lot';
  var closure=(lot.closure_m==null)?'\\u2014':lot.closure_m+' m';
  var area=(lot.computed_ha==null)?'\\u2014':lot.computed_ha+' ha';
  div.innerHTML='<h3 style="margin:4px 0">Lot '+esc(lot.lot)
    +' <span style="font-weight:normal;font-size:12px;color:#6b7280">'
    +lot.courses.length+' courses \\u00b7 '+lot.docs.length+' source doc(s)</span></h3>'
    +'<div class="lotstats">computed area '+area+' \\u00b7 ring closure '+closure
    +(lot.corrections_applied?' \\u00b7 '+lot.corrections_applied+' operator correction(s)':'')+'</div>'
    +'<div class="legend"><span class="lg-cor">corroborated</span>'
    +'<span class="lg-sin">single source</span><span class="lg-op">operator</span>'
    +'<span style="color:#dc2626">\\u25ef conflict vertex</span></div>';
  var svg=schematic(lot); if(svg) div.appendChild(svg);
  (lot.affirmations||[]).forEach(function(a){
    var p=document.createElement('div');
    p.className='aff '+(a.ok===true?'ok':(a.ok===false?'bad':'na'));
    p.textContent=(a.ok===true?'\\u2705 ':(a.ok===false?'\\u274c ':'\\u2014 '))+a.name+': '+a.value;
    div.appendChild(p);
  });
  (lot.conflicts||[]).forEach(function(c){
    var p=document.createElement('div');p.className='conflict';
    p.textContent='\\u2716 conflict at #'+c.pos+': backbone '+c.backbone_call+' vs '+c.src+' '+c.src_call;
    div.appendChild(p);
  });
  lot.courses.forEach(function(c){
    var row=document.createElement('div'); row.className='course';
    row.id='lot-'+(lot._pfx||'')+lot.lot+'-c-'+c.pos;
    var meta=STATUS_META[c.status]||['sin',c.status];
    row.innerHTML='<span class="pos">'+c.pos+'</span><span style="flex:1">'+esc(c.call)+'</span>'
      +'<span class="chip '+meta[0]+'">'+meta[1]
      +(c.status==='corroborated'?' \\u00d7'+c.docs.length:'')+'</span>';
    var det=document.createElement('div'); det.className='detail'; det.style.display='none';
    var inner='';
    var rawKeys=Object.keys(c.raws||{});
    if(rawKeys.length){
      inner+='<b>Source stack</b> \\u2014 what each document says:';
      rawKeys.forEach(function(d){inner+='<div class="src"><b>Doc '+esc(d)+':</b> \\u201c'
        +esc(c.raws[d])+'\\u201d</div>';});
    } else { inner+='<i>No verbatim excerpt on file for this course.</i>'; }
    det.innerHTML=inner;
    if(propose){
      var btn=document.createElement('button'); btn.className='flagbtn';
      btn.textContent='\\u2691 Propose a correction for this course';
      btn.addEventListener('click',function(ev){ev.stopPropagation();
        propose(b.title_no,lot.lot,c.pos,c.call);});
      det.appendChild(btn);
    }
    row.addEventListener('click',function(){
      det.style.display=(det.style.display==='none')?'block':'none';});
    div.appendChild(row); div.appendChild(det);
  });
  root.appendChild(div);
}
function renderBundle(b,root,propose){
  var wrap=document.createElement('div');
  var reg=b.register_area_sqm?(b.register_area_sqm/10000).toFixed(4)+' ha':'\\u2014';
  wrap.innerHTML='<div style="padding:10px 14px"><h2 style="margin:0">'+esc(b.title_no)+'</h2>'
    +'<div class="lotstats">registered area: '+reg+'</div>'
    +(b.corroboration||[]).map(function(l){return '<div class="aff na">'+esc(l)+'</div>';}).join('')
    +'</div>';
  root.appendChild(wrap);
  if(!b.ok||!b.lots.length){
    var p=document.createElement('div');p.className='lot';
    p.textContent='No boundary evidence extracted yet for this title.';
    root.appendChild(p); return;
  }
  b.lots.forEach(function(l){l._pfx=String(b.title_no||'').replace(/[^A-Za-z0-9]/g,'')+'-';renderLot(b,l,root,propose);});
}
"""

# --- CLIENT map v2 (premium: layers, evidence sheet, proposals, offline shell) ---
_CLIENT_HTML = """<!doctype html><html><head><meta charset=utf-8>
<title>My property</title>
<meta name=viewport content="width=device-width,initial-scale=1,maximum-scale=1">
<link rel=stylesheet href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel=manifest id=mf>
<style>
 html,body{margin:0;height:100%;font-family:system-ui,sans-serif}
 #map{position:absolute;top:0;bottom:0;left:0;right:0}
 #banner{position:absolute;z-index:1000;top:0;left:0;right:0;background:#b45309;color:#fff;
   font-size:13px;padding:7px 12px;text-align:center;display:none}
 .fab{position:absolute;z-index:1000;border:0;border-radius:24px;padding:12px 16px;font-size:14px;
   color:#fff;box-shadow:0 2px 8px rgba(0,0,0,.3);cursor:pointer;text-decoration:none}
 #locate{bottom:22px;right:14px;background:#2563eb}
 #evbtn{bottom:22px;left:14px;background:#111827}
 #earth{bottom:74px;right:14px;background:#0f766e;display:none}
 #readout{position:absolute;z-index:1000;bottom:74px;left:14px;right:130px;
   background:rgba(17,17,17,.85);color:#fff;font-size:13px;padding:9px 12px;border-radius:10px;display:none}
__PANEL_CSS__
</style></head><body>
<div id=banner></div>
<div id=readout></div>
<button id=locate class=fab onclick=locate()>&#128205; Locate me</button>
<button id=evbtn class=fab onclick=toggleSheet()>&#129517; Boundary evidence</button>
<a id=earth class=fab target=_blank rel=noreferrer>&#127757; History</a>
<div id=map></div>
<div id=sheet><header><h2>Boundary evidence</h2>
 <button onclick=toggleSheet() style="border:0;background:none;font-size:20px;cursor:pointer">&#10005;</button></header>
 <div id=sheetbody></div></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
var CFG=__CFG__;
__PANEL_JS__
document.getElementById('mf').href='/client/'+CFG.token+'/manifest.json';
var esri=L.tileLayer(CFG.tiles.esri,{maxZoom:21,attribution:CFG.tiles.esri_attrib});
var bases={'Satellite (Esri)':esri};
if(CFG.tiles.gsat) bases['Satellite (Google)']=L.tileLayer(CFG.tiles.gsat,{maxZoom:21,attribution:'&copy; Google'});
if(CFG.tiles.ghyb) bases['Hybrid (Google)']=L.tileLayer(CFG.tiles.ghyb,{maxZoom:21,attribution:'&copy; Google'});
var map=L.map('map',{layers:[esri]}).setView([CFG.lat,CFG.lng],17);
var overlays={};
CFG.orthos.forEach(function(o){overlays[o.label]=L.tileLayer(o.url,{maxZoom:22,opacity:.95});});
var approximate=false, RINGS=[];
var parcelLayer=L.geoJSON(null,{style:function(){return {color:'#facc15',weight:3,fillOpacity:0.12};},
  onEachFeature:function(f,lyr){var p=f.properties;
    if(p.approximate) approximate=true;
    var area=p.area_sqm?Math.round(p.area_sqm).toLocaleString()+' m\\u00b2':'';
    lyr.bindPopup('<b>'+esc(p.label||'')+'</b><br>'+area
      +'<br>accuracy: '+esc(p.accuracy_tier||'unset')+(p.approximate?' <i>(approximate)</i>':''));
    var g=f.geometry, ring=(g.type==='Polygon')?g.coordinates[0]:null;
    if(ring) RINGS.push(ring.map(function(c){return [c[1],c[0]];}));
  }});
overlays['My parcels']=parcelLayer; parcelLayer.addTo(map);
L.control.layers(bases,overlays,{position:'topright'}).addTo(map);
fetch('/client/'+CFG.token+'/parcels.geojson').then(function(r){return r.json();}).then(function(fc){
  if(fc.features&&fc.features.length){parcelLayer.addData(fc);
    try{map.fitBounds(parcelLayer.getBounds(),{maxZoom:19,padding:[30,30]});}catch(e){}
    if(approximate){var b=document.getElementById('banner');b.style.display='block';
      b.textContent='APPROXIMATE location \\u2014 not a survey. Precise boundaries follow survey/drone confirmation.';}
    if(CFG.earth){var c=parcelLayer.getBounds().getCenter();
      var a=document.getElementById('earth');a.style.display='block';
      a.href='https://earth.google.com/web/@'+c.lat.toFixed(6)+','+c.lng.toFixed(6)+',0a,400d,35y,0h,0t,0r';
      a.title='Opens Google Earth \\u2014 use the clock icon for historical imagery';}
  }});
var sheetLoaded=false;
function toggleSheet(){
  var s=document.getElementById('sheet'); s.classList.toggle('open');
  if(!sheetLoaded){sheetLoaded=true;loadEvidence();}
}
function loadEvidence(){
  var body=document.getElementById('sheetbody'); body.innerHTML='';
  if(!CFG.titles.length){body.innerHTML='<div class=lot>No boundary evidence extracted yet \\u2014 LandTek is processing your documents.</div>';return;}
  CFG.titles.forEach(function(t){
    fetch('/client/'+CFG.token+'/bundle/'+encodeURIComponent(t)+'.json')
      .then(function(r){return r.json();})
      .then(function(b){renderBundle(b,body,propose);})
      .catch(function(){var d=document.createElement('div');d.className='lot';
        d.textContent='Could not load '+t+' (offline?)';body.appendChild(d);});
  });
}
function propose(title,lot,pos,call){
  var note=prompt('What do you believe is wrong with course #'+pos+' ('+call+')?\\n'
    +'Your note goes to LandTek for review \\u2014 nothing changes until an operator verifies it.');
  if(!note||note.trim().length<3) return;
  fetch('/client/'+CFG.token+'/propose',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({title_no:title,lot:lot,position:pos,note:note.trim(),target_call:call})})
   .then(function(r){return r.json();})
   .then(function(j){alert(j.ok?j.msg:('Error: '+j.error));})
   .catch(function(){alert('Could not send \\u2014 check connection.');});
}
var meMarker=null,meAccuracy=null;
function locate(){
  if(!navigator.geolocation){alert('Location not available on this device');return;}
  navigator.geolocation.getCurrentPosition(function(pos){
    var lat=pos.coords.latitude,lng=pos.coords.longitude,acc=pos.coords.accuracy;
    if(meMarker)map.removeLayer(meMarker);
    if(meAccuracy)map.removeLayer(meAccuracy);
    meMarker=L.circleMarker([lat,lng],{radius:8,color:'#fff',weight:2,fillColor:'#2563eb',fillOpacity:1}).addTo(map);
    meAccuracy=L.circle([lat,lng],{radius:acc,color:'#2563eb',weight:1,fillOpacity:0.08}).addTo(map);
    map.setView([lat,lng],19); report(lat,lng,acc);
  },function(err){alert('Could not get your location: '+err.message);},
  {enableHighAccuracy:true,timeout:15000,maximumAge:0});
}
function report(lat,lng,acc){
  var inside=false,minEdge=Infinity;
  for(var i=0;i<RINGS.length;i++){
    if(pointInRing(lat,lng,RINGS[i])) inside=true;
    minEdge=Math.min(minEdge,distToRing(lat,lng,RINGS[i]));
  }
  var el=document.getElementById('readout'); el.style.display='block';
  if(!RINGS.length){el.textContent='Your parcel boundary is not published yet.';return;}
  var d=Math.round(minEdge);
  el.innerHTML=(inside?'\\u2705 You are <b>inside</b> your property (~'+d+' m from the nearest edge).'
    :'\\u2197\\ufe0f You are <b>outside</b> \\u2014 nearest boundary ~'+d+' m away.')
   +'<br><span style="opacity:.7">GPS accuracy \\u00b1'+Math.round(acc)+' m'
   +(approximate?' \\u00b7 boundary is approximate':'')+'</span>';
}
function pointInRing(lat,lng,ring){var inside=false;
  for(var i=0,j=ring.length-1;i<ring.length;j=i++){
    var yi=ring[i][0],xi=ring[i][1],yj=ring[j][0],xj=ring[j][1];
    if(((yi>lat)!=(yj>lat))&&(lng<(xj-xi)*(lat-yi)/(yj-yi)+xi)) inside=!inside;}
  return inside;}
function distToRing(lat,lng,ring){var R=6378137,la=lat*Math.PI/180,cos=Math.cos(la);
  var px=lng*Math.PI/180*R*cos,py=lat*Math.PI/180*R,best=Infinity;
  for(var i=0,j=ring.length-1;i<ring.length;j=i++){
    var ax=ring[i][1]*Math.PI/180*R*cos,ay=ring[i][0]*Math.PI/180*R;
    var bx=ring[j][1]*Math.PI/180*R*cos,by=ring[j][0]*Math.PI/180*R;
    best=Math.min(best,segDist(px,py,ax,ay,bx,by));}
  return best;}
function segDist(px,py,ax,ay,bx,by){var dx=bx-ax,dy=by-ay,l2=dx*dx+dy*dy;
  var t=l2?((px-ax)*dx+(py-ay)*dy)/l2:0;t=Math.max(0,Math.min(1,t));
  return Math.hypot(px-(ax+t*dx),py-(ay+t*dy));}
if('serviceWorker' in navigator){
  navigator.serviceWorker.register('/client/'+CFG.token+'/sw.js',
    {scope:'/client/'+CFG.token+'/'}).catch(function(){});
}
</script></body></html>"""

# --- OPS consensus console (same renderer as the client sheet) ----------------
_OPS_CONSENSUS_HTML = """<!doctype html><html><head><meta charset=utf-8>
<title>Consensus console</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
 body{margin:0;font-family:system-ui,sans-serif;background:#fff;color:#111}
 #bar{padding:10px 14px;background:#111;color:#fff;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
 #bar a{color:#93c5fd;text-decoration:none;font-size:13px}
__PANEL_CSS__
 #sheet{position:static;max-height:none;box-shadow:none;border-radius:0}
 #sheetbody{max-width:780px;margin:0 auto}
</style></head><body>
<div id=bar><b id=t></b>
 <a href="/ops/map/consensus">all titles</a>
 <a href="/ops/map/proposals">proposals</a>
 <a href="/ops/map">parcels</a></div>
<div id=sheet class=open><div id=sheetbody></div></div>
<script>
var CFG=__CFG__;
__PANEL_JS__
document.getElementById('t').textContent=CFG.title;
fetch(CFG.bundle_url).then(function(r){return r.json();})
  .then(function(b){renderBundle(b,document.getElementById('sheetbody'),null);});
</script></body></html>"""

# --- Token-scoped service worker (offline shell; caches ONLY this client's data) --
_SW_JS = """
var CACHE='__CACHE__';
var SCOPE='__SCOPE__';
self.addEventListener('install',function(e){self.skipWaiting();});
self.addEventListener('activate',function(e){
  e.waitUntil(caches.keys().then(function(keys){
    return Promise.all(keys.filter(function(k){return k.indexOf('ltk-map-')===0&&k!==CACHE;})
      .map(function(k){return caches.delete(k);}));
  }).then(function(){return self.clients.claim();}));
});
self.addEventListener('fetch',function(e){
  if(e.request.method!=='GET') return;
  var url=e.request.url;
  // this client's data + page: network-first, cached fallback (offline last-viewed parcel)
  if(url.indexOf(SCOPE)>=0&&(url.indexOf('/bundle/')>=0||url.indexOf('parcels.geojson')>=0
      ||url.indexOf('/map')>=0)){
    e.respondWith(fetch(e.request).then(function(r){
      var cp=r.clone(); caches.open(CACHE).then(function(c){c.put(e.request,cp);}); return r;
    }).catch(function(){return caches.match(e.request);}));
    return;
  }
  // CDN app shell (leaflet): cache-first
  if(url.indexOf('unpkg.com')>=0){
    e.respondWith(caches.match(e.request).then(function(hit){
      return hit||fetch(e.request).then(function(r){
        var cp=r.clone(); caches.open(CACHE).then(function(c){c.put(e.request,cp);}); return r;
      });
    }));
  }
  // everything else (map tiles, google) passes through — never hoarded
});
"""
