#!/usr/bin/env python3
"""survey_vision_extract.py — pull metes-and-bounds courses off a survey-plan / TCT SCAN
using Gemini vision (FREE tier — NOT the depleted Anthropic account).

The corpus text layer doesn't carry the bearing/distance calls (they live in the plan
IMAGE), so this is the input pipeline that feeds survey_geometry → parcels. Renders the
doc (PDF first page or image) → base64 → Gemini → strict JSON of the courses + stated area.

  python3 survey_vision_extract.py --doc <id>
  python3 survey_vision_extract.py --doc <id> --ingest --matter Paracale-001 --title T-3897 --stated-ha 23.0935
"""
import base64
import json
import os
import sys
import urllib.request
import urllib.error

import psycopg2

sys.path.insert(0, "/root/landtek/scripts")
import survey_geometry as sg
try:
    import parcels as P
except Exception:
    P = None

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash")
PROMPT = (
    "You are reading a Philippine land survey plan / Torrens technical description. "
    "Extract EVERY metes-and-bounds course (bearing + distance). Return STRICT JSON only, "
    "no prose: {\"calls\":[{\"from\":\"1\",\"to\":\"2\",\"bearing\":\"N. 86 deg 23' E.\","
    "\"distance_m\":269.35}], \"stated_area_sqm\": <number or null>}. "
    "Copy the bearing text exactly as written (deg/min, N/S + E/W)."
)


def _is_pdf(p):
    try:
        with open(p, "rb") as f:
            return f.read(5) == b"%PDF-"
    except Exception:
        return False


def _doc_image_b64(path, page=0):
    if path.lower().endswith(".pdf") or _is_pdf(path):
        import fitz
        d = fitz.open(path)
        idx = min(max(page, 0), d.page_count - 1)
        pix = d[idx].get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x for legibility
        return base64.b64encode(pix.tobytes("png")).decode(), "image/png"
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode(), "image/jpeg"


def extract(doc_id, page=0):
    if not GEMINI_KEY:
        return {"error": "no GEMINI_API_KEY"}
    c = psycopg2.connect(DSN); cur = c.cursor()
    cur.execute("SELECT file_path FROM documents WHERE id=%s", (doc_id,))
    r = cur.fetchone(); cur.close(); c.close()
    if not r or not r[0]:
        return {"error": "no file_path"}
    b64, mime = _doc_image_b64(r[0], page)
    body = {
        "contents": [{"parts": [{"inline_data": {"mime_type": mime, "data": b64}}, {"text": PROMPT}]}],
        "generationConfig": {"temperature": 0, "response_mime_type": "application/json"},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_KEY}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            out = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"gemini http_{e.code}: {e.read().decode('utf-8', 'replace')[:200]}"}
    except Exception as e:
        return {"error": f"call_failed: {type(e).__name__}: {str(e)[:160]}"}
    try:
        txt = out["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(txt)
    except Exception as e:
        return {"error": f"parse: {e}", "raw": str(out)[:300]}


def calls_to_text(calls):
    return "\n".join(
        f"{c.get('from','')}-{c.get('to','')} {c.get('bearing','')}, {c.get('distance_m','')} m"
        for c in calls)


if __name__ == "__main__":
    a = sys.argv
    if "--doc" not in a:
        print(__doc__); sys.exit(0)
    did = int(a[a.index("--doc") + 1])
    page = int(a[a.index("--page") + 1]) if "--page" in a else 0
    data = extract(did, page)
    if data.get("error"):
        print(json.dumps(data, indent=2)); sys.exit(1)
    calls = data.get("calls", [])
    text = calls_to_text(calls)
    geo = sg.analyze(text)
    print(json.dumps({"doc": did, "n_calls": len(calls),
                      "geo": {k: geo.get(k) for k in ("calls", "area_ha", "closure_error_m")},
                      "stated_area_sqm": data.get("stated_area_sqm")}, indent=2))
    if "--ingest" in a and P and geo.get("ok"):
        matter = a[a.index("--matter") + 1] if "--matter" in a else None
        title = a[a.index("--title") + 1] if "--title" in a else None
        if "--stated-ha" in a:
            stated = float(a[a.index("--stated-ha") + 1])
        else:
            stated = (data.get("stated_area_sqm") or 0) / 10000 or None
        res = P.upsert_parcel(matter, title, text, source_doc_id=did, stated_ha=stated)
        print("ingested parcel id:", res.get("parcel_id"), "match:", res.get("area_matches"))
