#!/usr/bin/env python3
"""plan_table_extract.py — frontier-vision GATED extraction of a survey plan's lot tables.

A subdivision plan prints the metes-and-bounds of every lot as small tables
(`LOT 2-A   A=8,706 SQ M` + rows of LINES / BEARINGS / DISTANCES). This tool renders the
plan in high-res tiles, has a vision model read every lot table, then — crucially — WRITES
NOTHING it cannot prove: each lot's courses are run through survey_geometry and kept only if
the ring CLOSES and the computed area matches the plan's own stated area. Handwritten-scan OCR
is error-prone (a human misreads ~40%); the closure+area gate makes it safe, because a misread
simply fails to close/match and is HELD, never stored. Nothing is ever fabricated.

Verified lots -> `parcels` (relative survey shape, provenance inferred_corroborated) keyed by
the plan lot designation (or the known title), plus a `map_parcels` row (awaiting_plot —
absolute placement/anchoring is a separate operator step via /ops/map/georef).

  python3 plan_table_extract.py --doc 287 --plan PSD-12802 --matter MWK-001         # dry-run
  python3 plan_table_extract.py --doc 287 --plan PSD-12802 --matter MWK-001 --write  # persist
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import survey_geometry as sg
import parcels as P
import reocr_gemini as G   # key×model ladder + Drive-fetch
import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
CLOSE_M = 1.0        # ring must close at least this well
AREA_TOL = 0.03      # computed area within 3% of the plan's stated area
# lots whose derivative title is already known (keeps them keyed to the real title)
KNOWN_TITLES = {"2-A": "T-32911"}

PROMPT = (
    "You are reading the metes-and-bounds COURSE TABLES printed on a Philippine subdivision "
    "survey plan. Each lot appears as a small table headed 'LOT <id>   A = <area> SQ M' followed "
    "by rows of three columns: LINES (e.g. '1  2'), BEARINGS (e.g. \"N. 76 deg 12' W\" or "
    "\"N 76° 12' W\"), and DISTANCES in meters (e.g. '70.45 M'). Read EVERY lot table you can see. "
    "Return STRICT JSON only, no prose: "
    "{\"lots\":[{\"lot\":\"2-A\",\"area_sqm\":8706,\"courses\":["
    "{\"from\":\"1\",\"to\":\"2\",\"bearing\":\"N. 76 deg 12' W\",\"distance_m\":70.45}]}]}. "
    "Copy each bearing and distance EXACTLY as written (quadrant letters N/S + E/W, degrees, "
    "minutes). Minutes are 0-59; never emit a minute value above 59. If a value is illegible use "
    "null. Do NOT invent or 'fix' values."
)


def _page(doc_id):
    import fitz
    c = psycopg2.connect(DSN); cur = c.cursor()
    cur.execute("SELECT file_path, drive_file_id FROM documents WHERE id=%s", (doc_id,))
    fp, drv = cur.fetchone(); cur.close(); c.close()
    path = fp if (fp and os.path.exists(fp or "")) else G._drive_fetch(drv)
    return fitz.open(path)[0]


def _tiles(pg):
    """High-res tiles covering the table block (top-centre-right of the sheet), with overlap so
    no lot table is split across a seam without also appearing whole in a neighbour."""
    import fitz
    W, H = pg.rect.width, pg.rect.height
    xs = [(0.34, 0.51), (0.48, 0.63), (0.60, 0.75)]
    ys = [(0.02, 0.31), (0.28, 0.57)]
    out = []
    for i, (x0, x1) in enumerate(xs):
        for j, (y0, y1) in enumerate(ys):
            clip = fitz.Rect(W * x0, H * y0, W * x1, H * y1)
            pix = pg.get_pixmap(matrix=fitz.Matrix(10, 10), clip=clip)
            out.append((f"c{i}r{j}", base64.b64encode(pix.tobytes("png")).decode()))
    return out


def _vision_json(png_b64):
    """Return (parsed_json, backend) — Gemini ladder first (best on handwriting), local
    Ollama vision as the creditless fallback. None on total failure."""
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": "image/png", "data": png_b64}},
                                    {"text": PROMPT}]}],
            "generationConfig": {"temperature": 0, "response_mime_type": "application/json"}}
    for key, model in G._ladder():
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                         headers={"content-type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=150) as r:
                out = json.loads(r.read())
            txt = out["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(txt), f"gemini:{model}"
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                continue
        except Exception:
            continue
    # creditless fallback: local Ollama vision
    try:
        import reocr_local as L
        url = L.OLLAMA_URL + "/api/generate"
        body2 = {"model": L.MODEL, "prompt": PROMPT, "images": [png_b64],
                 "stream": False, "format": "json", "options": {"temperature": 0, "num_predict": 4096}}
        req = urllib.request.Request(url, data=json.dumps(body2).encode(),
                                     headers={"content-type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=300) as r:
            resp = json.loads(r.read()).get("response", "")
        return json.loads(resp), f"local:{L.MODEL}"
    except Exception:
        return None, "none"


def _calls_text(courses):
    out = []
    for cse in courses or []:
        b = (cse.get("bearing") or "").strip()
        d = cse.get("distance_m")
        if b and d not in (None, ""):
            out.append(f"{b}, {d} m")
    return "\n".join(out)


def extract(doc_id, plan, matter, write=False):
    pg = _page(doc_id)
    tiles = _tiles(pg)
    lots = {}        # lot_id -> {area, courses} (first non-empty read wins)
    backends = set()
    for name, b64 in tiles:
        data, backend = _vision_json(b64)
        backends.add(backend)
        for lot in (data or {}).get("lots", []):
            lid = re.sub(r"[^0-9A-Za-z-]", "", str(lot.get("lot", "")).upper()).lstrip("LOT")
            if not lid or not lot.get("courses"):
                continue
            if lid not in lots or len(lot["courses"]) > len(lots[lid]["courses"]):
                lots[lid] = {"area": lot.get("area_sqm"), "courses": lot["courses"]}
    print(f"vision backends: {sorted(backends)} · lots read: {len(lots)}")

    conn = psycopg2.connect(DSN); conn.autocommit = True; cur = conn.cursor()
    verified = held = 0
    print(f"\n{'lot':<8}{'stated':>9}{'computed':>10}{'clos_m':>8}  verdict")
    print("-" * 52)
    for lid in sorted(lots):
        L = lots[lid]
        calls = _calls_text(L["courses"])
        a = sg.analyze(calls)
        stated = L["area"]
        ga = a.get("area_sqm") or 0.0
        clos = a.get("closure_error_m")
        ok = bool(a.get("ok") and stated and clos is not None and clos <= CLOSE_M
                  and abs(ga - stated) / stated <= AREA_TOL)
        st = f"{stated:,.0f}" if stated else "—"
        print(f"{lid:<8}{st:>9}{ga:>10,.1f}{(clos if clos is not None else float('nan')):>8.2f}"
              f"  {'✅ VERIFIED' if ok else 'held'}")
        if ok:
            verified += 1
            if write:
                title_no = KNOWN_TITLES.get(lid, f"{plan} Lot {lid}")
                pc = "MWK-" + re.sub(r"[^0-9A-Za-z]+", "-", title_no).strip("-")
                cur.execute("DELETE FROM parcels WHERE title_no=%s", (title_no,))
                res = P.upsert_parcel(matter, title_no, calls, source_doc_id=doc_id,
                                      stated_ha=(stated / 10000.0))
                if res.get("parcel_id"):
                    cur.execute("UPDATE parcels SET provenance_level='inferred_corroborated' "
                                "WHERE id=%s", (res["parcel_id"],))
                    cur.execute(
                        "INSERT INTO map_parcels (parcel_code,client_code,matter_code,title_no,"
                        "label,stated_area_sqm,status) VALUES (%s,%s,%s,%s,%s,%s,'awaiting_plot') "
                        "ON CONFLICT (parcel_code) DO UPDATE SET stated_area_sqm=EXCLUDED.stated_area_sqm",
                        (pc, matter, matter, title_no, f"Lot {lid} ({title_no})", stated))
        else:
            held += 1
    cur.close(); conn.close()
    print(f"\n{verified} verified, {held} held (of {len(lots)} read)."
          + (f"  Stored verified to parcels + map_parcels (awaiting_plot)." if write else
             "  (dry-run — add --write to persist verified lots.)"))


def main():
    ap = argparse.ArgumentParser(description="Frontier-vision gated extraction of plan lot tables")
    ap.add_argument("--doc", type=int, required=True)
    ap.add_argument("--plan", default="PLAN")
    ap.add_argument("--matter", default="MWK-001")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    extract(a.doc, a.plan, a.matter, write=a.write)


if __name__ == "__main__":
    main()
