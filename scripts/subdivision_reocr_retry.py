#!/usr/bin/env python3
"""subdivision_reocr_retry.py — unlock the flagged Psd-221861 lots (2-G, 2-M, 2-X) once the
Gemini free-tier quota resets.

The 1975 plan (doc 287) hand-lettering blurs 9/4, 3/7 and 1/7 on these three lots' tables, so
my in-context read couldn't close them. This runs on a timer; when Gemini answers (not 429), it:

  1. renders each still-flagged lot's table crop from doc 287,
  2. asks Gemini for a strict-JSON metes-and-bounds transcription,
  3. validates the ring against the SAME truth-gate (closure <= 1.5 m, printed area match),
  4. only on pass: records the recovered courses (subdivision_recovered_lots), ingests the
     parcel, and re-runs the shared-edge assembly so the lot — and any orphan lots it now
     bridges to the 2-A anchor — snap onto the map.

Degrades gracefully: on 429 (quota still out) it logs and exits 0 so the next tick retries.
NEVER writes a lot that doesn't close — a garbled read is logged for review, not mapped.
"""
from __future__ import annotations
import base64, json, os, re, sys, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subdivision_geometry as SG
import reocr_gemini as RG   # for _drive_fetch + key ladder

DOC = 287
GEMINI = os.environ.get("GEMINI_API_KEY", "")
GEMINI2 = os.environ.get("GEMINI_API_KEY_FALLBACK", "")
MODELS = ("gemini-2.5-flash", "gemini-2.0-flash")

# still-flagged lots: stated area + the fractional table crop(s) on doc 287
TARGETS = {
    "2-G": {"area": 4148,   "boxes": [(0.470, 0.567, 0.205, 0.320)]},
    "2-M": {"area": 1895,   "boxes": [(0.558, 0.690, 0.148, 0.258)]},
    "2-X": {"area": 108918, "boxes": [(0.558, 0.690, 0.250, 0.362), (0.626, 0.762, 0.030, 0.362)]},
}
PROMPT = ("This is a metes-and-bounds course table for ONE lot from a 1975 Philippine subdivision "
          "plan. Transcribe EVERY course row as strict JSON only: "
          "{\"courses\":[{\"line\":\"1-2\",\"bearing\":\"N 77 35 W\",\"dist\":22.00}]}. "
          "bearing = <N|S> <deg> <min> <E|W>. Copy digits EXACTLY; do not round or infer. "
          "If a digit is illegible use null. Output only JSON.")


class Quota(Exception):
    pass


def _crop_b64(pg, box):
    import fitz
    W, H = pg.rect.width, pg.rect.height
    a, b, ya, yb = box
    pix = pg.get_pixmap(matrix=fitz.Matrix(16, 16), clip=fitz.Rect(a*W, ya*H, b*W, yb*H))
    return base64.b64encode(pix.tobytes("png")).decode()


def _gemini(b64):
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": "image/png", "data": b64}},
            {"text": PROMPT}]}], "generationConfig": {"temperature": 0, "response_mime_type": "application/json"}}
    transient = False   # 429 (quota) or 5xx (overloaded) — both mean "retry next tick"
    for key in (k for k in (GEMINI, GEMINI2) if k):
        for model in MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                         headers={"content-type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    out = json.loads(r.read())
                return json.loads(out["candidates"][0]["content"]["parts"][0]["text"])
            except urllib.error.HTTPError as e:
                if e.code == 429 or 500 <= e.code < 600:
                    transient = True; continue
                raise
    if transient:
        raise Quota("all gemini key/model combos returned 429/5xx")
    raise RuntimeError("gemini call failed")


_BRG = re.compile(r"([NnSs])\D*?(\d{1,3})\D+?(\d{1,2})\D*?([EeWw])")

def _parse(courses):
    out = []
    for c in courses:
        m = _BRG.search(c.get("bearing") or "")
        d = c.get("dist")
        if not m or d is None:
            return None
        out.append((m.group(1).upper(), int(m.group(2)), int(m.group(3)), m.group(4).upper(), float(d)))
    return out


def run():
    import psycopg2
    conn = psycopg2.connect(SG.DSN); conn.autocommit = True; cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS subdivision_recovered_lots(
        lot text PRIMARY KEY, stated_area numeric, courses_json jsonb, closure_m numeric,
        area_sqm numeric, source text, recovered_at timestamptz DEFAULT now())""")
    cur.execute("SELECT lot FROM subdivision_recovered_lots")
    done = {r[0] for r in cur.fetchall()}
    todo = [k for k in TARGETS if k not in done]
    if not todo:
        print("all flagged lots already recovered — nothing to do."); return
    import fitz
    cur.execute("SELECT drive_file_id FROM documents WHERE id=%s", (DOC,))
    pg = fitz.open(RG._drive_fetch(cur.fetchone()[0]))[0]

    unlocked = []
    for lot in todo:
        spec = TARGETS[lot]
        try:
            merged = {}
            for box in spec["boxes"]:
                data = _gemini(_crop_b64(pg, box))
                for c in data.get("courses", []):
                    if c.get("line"):
                        merged[c["line"]] = c
            courses = _parse([merged[k] for k in sorted(merged, key=lambda s: int(s.split("-")[0]))])
        except Quota:
            print("gemini quota still exhausted (429) — will retry next tick."); return
        except Exception as e:
            print(f"{lot}: gemini/parse error: {str(e)[:120]}"); continue
        if not courses:
            print(f"{lot}: read had illegible cells — kept flagged for review."); continue
        clo, area, pts = SG.ring(courses)
        off = abs(area - spec["area"]) / spec["area"] * 100
        if clo <= SG.CLOSE_GATE and off <= 3:
            cur.execute("""INSERT INTO subdivision_recovered_lots
                (lot, stated_area, courses_json, closure_m, area_sqm, source)
                VALUES (%s,%s,%s,%s,%s,'gemini-reocr doc287') ON CONFLICT (lot) DO NOTHING""",
                (lot, spec["area"], json.dumps(courses), round(clo, 3), round(area, 1)))
            unlocked.append(f"{lot} (closure {clo:.2f} m, area {area:.0f}/{spec['area']})")
            print(f"UNLOCKED {lot}: closure {clo:.3f} m, area {area:.1f} vs {spec['area']} ({off:.2f}%)")
        else:
            print(f"{lot}: re-OCR ring still won't close (closure {clo:.1f} m, area off {off:.1f}%) — kept flagged.")

    cur.close(); conn.close()
    if unlocked:
        # ingest verified parcels + re-run shared-edge assembly to snap them onto the map
        os.system(f"python3 {os.path.join(os.path.dirname(os.path.abspath(__file__)),'subdivision_geometry.py')} --ingest")
        os.system(f"python3 {os.path.join(os.path.dirname(os.path.abspath(__file__)),'subdivision_assemble.py')} --write")
        print("re-assembled map after unlocking: " + "; ".join(unlocked))


if __name__ == "__main__":
    run()
